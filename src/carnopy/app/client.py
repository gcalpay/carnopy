from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from PySide6.QtCore import QObject, QProcess, Signal

from carnopy.app.plot_staging import (
    PlotStagingLease,
    cleanup_plot_staging,
    create_plot_staging,
)
from carnopy.app.protocol import (
    PROTOCOL_VERSION,
    ErrorCategory,
    RequestType,
    WorkerErrorPayload,
    WorkerEvent,
    WorkerRequest,
    parse_event,
)


class WorkerClient(QObject):
    """Run one short-lived Carnopy worker request without blocking the Qt event loop."""

    event_received = Signal(object)
    request_succeeded = Signal(object)
    request_failed = Signal(object)
    request_finished = Signal(object)
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
        self._capabilities: dict[str, dict[str, Any]] = {}
        self._plot_staging_lease: PlotStagingLease | None = None

    @property
    def is_busy(self) -> bool:
        return self._process is not None

    @property
    def request_id(self) -> UUID | None:
        return self._request_id

    @property
    def request_type(self) -> RequestType | None:
        return self._request_type

    def cached_capabilities(self, model: str) -> dict[str, Any] | None:
        return self._capabilities.get(model)

    def shutdown(self) -> None:
        """Stop a short-lived worker when its owning window is closing."""
        process = self._process
        if process is None:
            return
        successful = self._terminal_event is not None and self._terminal_event.type == "result"
        process.blockSignals(True)
        process.kill()
        process.waitForFinished(1_000)
        self._cleanup_plot_staging(successful=successful)
        self._reset_process()

    def request_cancel(self) -> bool:
        process = self._process
        request_id = self._request_id
        if process is None or request_id is None or self._terminal_seen:
            return False
        request = WorkerRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id=request_id,
            type="cancel",
            payload={},
        )
        process.write((request.model_dump_json() + "\n").encode("utf-8"))
        return True

    def force_stop(self) -> bool:
        if self._process is None or self._terminal_seen:
            return False
        self._force_stopped = True
        self._process.kill()
        return True

    def start_request(
        self,
        request_type: RequestType,
        payload: Mapping[str, object] | None = None,
    ) -> UUID:
        if self.is_busy:
            raise RuntimeError("a Carnopy worker request is already active")

        request_payload = dict(payload or {})
        lease = None
        if request_type == "render_plot":
            workspace_path = request_payload.get("workspace_path")
            if not isinstance(workspace_path, (str, Path)):
                raise ValueError("render_plot requires workspace_path")
            lease = create_plot_staging(Path(workspace_path))
            request_payload["staging"] = lease.worker_payload()

        request_id = uuid4()
        request = WorkerRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id=request_id,
            type=request_type,
            payload=request_payload,
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
        self._plot_staging_lease = lease
        self.busy_changed.emit(True)
        process.start(sys.executable, ["-m", "carnopy.app.worker"])
        return request_id

    def _write_request(self, request: WorkerRequest) -> None:
        process = self._process
        if process is None:
            return
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
        failure = _client_error("protocol", code, message)
        if self._process is None:
            self.request_failed.emit(failure)
            return
        self._client_failure = failure
        self._process.kill()

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if self._terminal_seen:
            return
        process = self._process
        message = process.errorString() if process is not None else str(error)
        if error == QProcess.ProcessError.FailedToStart:
            self._terminal_seen = True
            failure = _client_error("process", "failed_to_start", message)
            cleanup_error = self._cleanup_plot_staging(successful=False)
            envelope = self._terminal_envelope(
                terminal=None,
                stderr="".join(self._stderr_parts),
                exit_code=None,
                exit_status="failed_to_start",
                cleanup_error=cleanup_error,
            )
            self._reset_process()
            self.request_finished.emit(envelope)
            self.request_failed.emit(failure)

    def _process_finished(
        self,
        exit_code: int,
        _exit_status: QProcess.ExitStatus,
    ) -> None:
        if self._process is None:
            return
        self._read_stdout()
        self._read_stderr()
        terminal = self._terminal_event
        failure = self._client_failure
        if self._force_stopped:
            failure = _client_error(
                "process",
                "force_stopped",
                "worker process was force-stopped",
            )
        elif terminal is None and failure is None:
            stderr = "".join(self._stderr_parts).strip()
            message = f"worker exited with code {exit_code} without a terminal event"
            if stderr:
                message += f": {stderr}"
            failure = _client_error("process", "missing_terminal_event", message)
        successful = (
            failure is None
            and terminal is not None
            and terminal.type == "result"
            and exit_code == 0
            and _exit_status == QProcess.ExitStatus.NormalExit
        )
        cleanup_error = self._cleanup_plot_staging(successful=successful)
        stderr = "".join(self._stderr_parts)
        envelope = self._terminal_envelope(
            terminal=terminal,
            stderr=stderr,
            exit_code=exit_code,
            exit_status=("normal" if _exit_status == QProcess.ExitStatus.NormalExit else "crash"),
            cleanup_error=cleanup_error,
        )
        self._reset_process()
        self.request_finished.emit(envelope)
        if failure is not None:
            self.request_failed.emit(failure)
        elif terminal is not None and terminal.type == "result":
            request_type = envelope.get("request_type")
            if request_type == "describe_capabilities":
                model = terminal.payload.get("model")
                if isinstance(model, str):
                    self._capabilities[model] = terminal.payload
            self.request_succeeded.emit(terminal.payload)
        elif terminal is not None and terminal.type == "error":
            self.request_failed.emit(terminal.payload)
        elif terminal is not None:
            self.request_failed.emit(
                _client_error(
                    "execution",
                    str(terminal.payload.get("code", "cancelled")),
                    str(terminal.payload.get("message", "worker request was cancelled")),
                )
            )

    def _terminal_envelope(
        self,
        *,
        terminal: WorkerEvent | None,
        stderr: str,
        exit_code: int | None,
        exit_status: str,
        cleanup_error: str | None,
    ) -> dict[str, object]:
        return {
            "request_id": None if self._request_id is None else str(self._request_id),
            "request_type": self._request_type,
            "terminal_event": (None if terminal is None else terminal.model_dump(mode="json")),
            "stderr": stderr,
            "exit_code": exit_code,
            "exit_status": exit_status,
            "force_stopped": self._force_stopped,
            "cleanup_error": cleanup_error,
        }

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
        self._plot_staging_lease = None
        if process is not None:
            process.deleteLater()
        self.busy_changed.emit(False)

    def _cleanup_plot_staging(self, *, successful: bool) -> str | None:
        lease, self._plot_staging_lease = self._plot_staging_lease, None
        if lease is None:
            return None
        try:
            cleanup_plot_staging(lease, successful=successful)
        except Exception as exc:  # pragma: no cover - defensive Qt process boundary
            message = f"plot staging cleanup failed: {exc}"
            self._stderr_parts.append(message + "\n")
            self.stderr_received.emit(message + "\n")
            return message
        return None


def _client_error(category: ErrorCategory, code: str, message: str) -> dict[str, object]:
    return WorkerErrorPayload(
        category=category,
        code=code,
        message=message,
    ).model_dump(exclude_none=True)
