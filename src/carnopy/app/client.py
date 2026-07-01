from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from PySide6.QtCore import QObject, QProcess, Signal

from carnopy.app.protocol import (
    PROTOCOL_VERSION,
    RequestType,
    WorkerEvent,
    WorkerRequest,
    parse_event,
)


class WorkerClient(QObject):
    """Run one short-lived Carnopy worker request without blocking the Qt event loop."""

    event_received = Signal(object)
    request_succeeded = Signal(object)
    request_failed = Signal(object)
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
        self._capabilities: dict[str, dict[str, Any]] = {}

    @property
    def is_busy(self) -> bool:
        return self._process is not None

    @property
    def request_id(self) -> UUID | None:
        return self._request_id

    def cached_capabilities(self, model: str) -> dict[str, Any] | None:
        return self._capabilities.get(model)

    def start_request(
        self,
        request_type: RequestType,
        payload: Mapping[str, object] | None = None,
    ) -> UUID:
        if self.is_busy:
            raise RuntimeError("a Carnopy worker request is already active")

        request_id = uuid4()
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
            self._fail_protocol(f"invalid worker event: {exc}")
            return
        if event.request_id != self._request_id:
            self._fail_protocol("worker event request ID does not match the active request")
            return

        self.event_received.emit(event)
        if event.type not in {"result", "error", "cancelled"} or self._terminal_seen:
            return
        self._terminal_seen = True
        self._terminal_event = event

    def _fail_protocol(self, message: str) -> None:
        if not self._terminal_seen:
            self._terminal_seen = True
            self.request_failed.emit({"category": "protocol", "message": message})
        if self._process is not None:
            self._process.kill()

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if self._terminal_seen:
            return
        self._terminal_seen = True
        process = self._process
        message = process.errorString() if process is not None else str(error)
        self.request_failed.emit({"category": "process", "message": message})
        if error == QProcess.ProcessError.FailedToStart:
            self._reset_process()

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
        terminal_seen = self._terminal_seen
        request_type = self._request_type
        failure: dict[str, object] | None = None
        if terminal is None and not terminal_seen:
            stderr = "".join(self._stderr_parts).strip()
            message = f"worker exited with code {exit_code} without a terminal event"
            if stderr:
                message += f": {stderr}"
            failure = {"category": "process", "message": message}
        self._reset_process()
        if failure is not None:
            self.request_failed.emit(failure)
        elif terminal is not None and terminal.type == "result":
            if request_type == "describe_capabilities":
                model = terminal.payload.get("model")
                if isinstance(model, str):
                    self._capabilities[model] = terminal.payload
            self.request_succeeded.emit(terminal.payload)
        elif terminal is not None:
            self.request_failed.emit(terminal.payload)

    def _reset_process(self) -> None:
        process, self._process = self._process, None
        self._request_id = None
        self._request_type = None
        self._stdout_buffer = ""
        self._stderr_parts = []
        self._terminal_seen = False
        self._terminal_event = None
        if process is not None:
            process.deleteLater()
        self.busy_changed.emit(False)
