from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError
from PySide6.QtCore import QObject, QProcess, Signal

from carnopy.app.protocol import (
    PROTOCOL_VERSION,
    ErrorCategory,
    RequestType,
    WorkerErrorPayload,
    WorkerEvent,
    WorkerRequest,
    parse_event,
)


@dataclass(frozen=True)
class TransportOutcome:
    """One transport-level outcome emitted after the worker process exits."""

    request_id: UUID
    request_type: RequestType
    terminal_event: WorkerEvent | None
    client_failure: dict[str, object] | None
    stderr: str
    exit_code: int | None
    exit_status: str
    force_stopped: bool

    @property
    def successful(self) -> bool:
        return (
            self.client_failure is None
            and self.terminal_event is not None
            and self.terminal_event.type == "result"
            and self.exit_code == 0
            and self.exit_status == "normal"
            and not self.force_stopped
        )


class WorkerClient(QObject):
    """Transport one request through one short-lived worker process."""

    event_received = Signal(object)
    transport_finished = Signal(object)
    stderr_received = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._request_id: UUID | None = None
        self._request_type: RequestType | None = None
        self._stdout_buffer = ""
        self._stderr_parts: list[str] = []
        self._terminal_seen = False
        self._terminal_event: WorkerEvent | None = None
        self._client_failure: dict[str, object] | None = None
        self._force_stopped = False

    @property
    def is_busy(self) -> bool:
        return self._process is not None

    @property
    def request_id(self) -> UUID | None:
        return self._request_id

    @property
    def request_type(self) -> RequestType | None:
        return self._request_type

    def shutdown(self) -> None:
        """Release an idle transport during application teardown."""
        if self.is_busy:
            raise RuntimeError("cannot shut down WorkerClient while a request is active")

    def send_cancel(self, request_id: UUID) -> bool:
        process = self._process
        if (
            process is None
            or request_id != self._request_id
            or self._terminal_seen
            or self._force_stopped
        ):
            return False
        request = WorkerRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id=request_id,
            type="cancel",
            payload={},
        )
        process.write((request.model_dump_json() + "\n").encode("utf-8"))
        return True

    def force_stop(self, request_id: UUID) -> bool:
        if (
            self._process is None
            or request_id != self._request_id
            or self._terminal_seen
            or self._force_stopped
        ):
            return False
        self._force_stopped = True
        self._process.kill()
        return True

    def start_request(
        self,
        request_id: UUID,
        request_type: RequestType,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        if self.is_busy:
            raise RuntimeError("a Carnopy worker request is already active")
        if request_type == "cancel":
            raise ValueError("cancel is not a primary worker request")

        request = WorkerRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id=request_id,
            type=request_type,
            payload=dict(payload or {}),
        )
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.started.connect(lambda: self._write_request(request))
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.errorOccurred.connect(self._process_error)
        process.finished.connect(self._process_finished)

        self._process = process
        self._request_id = request_id
        self._request_type = request_type
        self._stdout_buffer = ""
        self._stderr_parts = []
        self._terminal_seen = False
        self._terminal_event = None
        self._client_failure = None
        self._force_stopped = False
        self.busy_changed.emit(True)
        process.start(sys.executable, ["-m", "carnopy.app.worker"])

    def _write_request(self, request: WorkerRequest) -> None:
        process = self._process
        if process is not None:
            process.write((request.model_dump_json() + "\n").encode("utf-8"))

    def _read_stdout(self) -> None:
        process = self._process
        if process is None:
            return
        self._stdout_buffer += bytes(process.readAllStandardOutput().data()).decode(
            "utf-8",
            errors="replace",
        )
        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            if line:
                self._handle_event_line(line)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None:
            return
        text = bytes(process.readAllStandardError().data()).decode("utf-8", errors="replace")
        if text:
            self._stderr_parts.append(text)
            self.stderr_received.emit(text)

    def _handle_event_line(self, line: str) -> None:
        try:
            event = parse_event(line)
        except ValidationError as exc:
            self._fail_protocol(f"invalid worker event: {exc}", code="invalid_event")
            return
        if event.request_id != self._request_id:
            self._fail_protocol(
                "worker event request ID does not match the active request",
                code="request_id_mismatch",
            )
            return

        self.event_received.emit(event)
        if event.type not in {"result", "error", "cancelled"} or self._terminal_seen:
            return
        self._terminal_seen = True
        self._terminal_event = event

    def _fail_protocol(self, message: str, *, code: str) -> None:
        if self._terminal_seen:
            return
        self._terminal_seen = True
        self._client_failure = _client_error("protocol", code, message)
        if self._process is not None:
            self._process.kill()

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if self._terminal_seen or error != QProcess.ProcessError.FailedToStart:
            return
        process = self._process
        message = process.errorString() if process is not None else str(error)
        self._terminal_seen = True
        self._client_failure = _client_error("process", "failed_to_start", message)
        self._finish_transport(
            exit_code=None,
            exit_status="failed_to_start",
        )

    def _process_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if self._process is None:
            return
        self._read_stdout()
        self._read_stderr()
        terminal = self._terminal_event
        if self._force_stopped:
            self._client_failure = _client_error(
                "process",
                "force_stopped",
                "worker process was force-stopped",
            )
        elif terminal is None and self._client_failure is None:
            stderr = "".join(self._stderr_parts).strip()
            message = f"worker exited with code {exit_code} without a terminal event"
            if stderr:
                message += f": {stderr}"
            self._client_failure = _client_error(
                "process",
                "missing_terminal_event",
                message,
            )
        elif (
            terminal is not None
            and terminal.type == "result"
            and (exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit)
        ):
            self._client_failure = _client_error(
                "process",
                "execution_failed",
                f"worker returned a result but exited with code {exit_code}",
            )
        self._finish_transport(
            exit_code=exit_code,
            exit_status=("normal" if exit_status == QProcess.ExitStatus.NormalExit else "crash"),
        )

    def _finish_transport(self, *, exit_code: int | None, exit_status: str) -> None:
        request_id = self._request_id
        request_type = self._request_type
        if request_id is None or request_type is None:
            return
        outcome = TransportOutcome(
            request_id=request_id,
            request_type=request_type,
            terminal_event=self._terminal_event,
            client_failure=self._client_failure,
            stderr="".join(self._stderr_parts),
            exit_code=exit_code,
            exit_status=exit_status,
            force_stopped=self._force_stopped,
        )
        self._reset_process()
        self.transport_finished.emit(outcome)

    def _reset_process(self) -> None:
        process, self._process = self._process, None
        self._request_id = None
        self._request_type = None
        self._stdout_buffer = ""
        self._stderr_parts = []
        self._terminal_seen = False
        self._terminal_event = None
        self._client_failure = None
        self._force_stopped = False
        if process is not None:
            process.deleteLater()
        self.busy_changed.emit(False)


def _client_error(category: ErrorCategory, code: str, message: str) -> dict[str, object]:
    return WorkerErrorPayload(
        category=category,
        code=code,
        message=message,
    ).model_dump(exclude_none=True)
