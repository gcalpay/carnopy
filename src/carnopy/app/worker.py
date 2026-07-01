from __future__ import annotations

import contextlib
import json
import sys
import threading
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import IO, Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from carnopy._execution import ExecutionCancelled, ExecutionControl
from carnopy.app.protocol import (
    EventType,
    WorkerEvent,
    WorkerRequest,
    encode_event,
    parse_request,
)
from carnopy.domain.failures import CarnopyError, ConfigError

SYSTEM_REQUEST_ID = UUID(int=0)


class CapabilitiesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Literal["heos", "pr", "srk"] = "heos"


class ValidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    config_path: Path


class GeneratePayload(ValidatePayload):
    output_root: Path
    figures_root: Path = Path("figures")


class EventWriter:
    def __init__(self, stream: IO[str], request_id: UUID) -> None:
        self._stream = stream
        self._request_id = request_id
        self._lock = threading.Lock()

    def emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        event = WorkerEvent(
            request_id=self._request_id,
            type=event_type,
            payload=cast(dict[str, Any], _jsonable(payload)),
        )
        with self._lock:
            self._stream.write(encode_event(event))
            self._stream.flush()


def main(
    stdin: IO[str] = sys.stdin,
    stdout: IO[str] = sys.stdout,
    stderr: IO[str] = sys.stderr,
) -> int:
    first_line = stdin.readline()
    if not first_line:
        return _protocol_failure(stdout, stderr, "worker request is missing")
    try:
        request = parse_request(first_line)
    except ValidationError as exc:
        return _protocol_failure(stdout, stderr, f"invalid worker request: {exc}")
    writer = EventWriter(stdout, request.request_id)
    if request.type == "cancel":
        writer.emit("error", {"category": "protocol", "message": "cancel is not a primary request"})
        return 2

    cancelled = threading.Event()
    listener = threading.Thread(
        target=_listen_for_cancellation,
        args=(stdin, stderr, request.request_id, cancelled),
        daemon=True,
        name="carnopy-worker-cancel-listener",
    )
    listener.start()
    writer.emit("accepted", {"request_type": request.type})
    try:
        with contextlib.redirect_stdout(stderr):
            result = _execute(request, writer, cancelled)
    except ExecutionCancelled as exc:
        writer.emit("cancelled", {"message": str(exc)})
        return 0
    except ConfigError as exc:
        writer.emit("error", {"category": "config", "message": str(exc)})
        return 1
    except CarnopyError as exc:
        writer.emit("error", {"category": "execution", "message": str(exc)})
        return 1
    except (ValidationError, OSError, ValueError) as exc:
        writer.emit("error", {"category": "request", "message": str(exc)})
        return 2
    except Exception as exc:  # pragma: no cover - defensive process boundary
        traceback.print_exc(file=stderr)
        writer.emit(
            "error",
            {"category": "internal", "message": f"unexpected worker failure: {type(exc).__name__}"},
        )
        return 1
    writer.emit("result", cast(dict[str, Any], _jsonable(result)))
    return 0


def _execute(
    request: WorkerRequest,
    writer: EventWriter,
    cancelled: threading.Event,
) -> dict[str, Any]:
    if request.type == "describe_capabilities":
        return _describe_capabilities(CapabilitiesPayload.model_validate(request.payload))
    if request.type == "validate_config":
        payload = ValidatePayload.model_validate(request.payload)
        writer.emit("phase", {"name": "validation", "cancellable": True})
        from carnopy.api import validate_config

        return cast(dict[str, Any], _jsonable(validate_config(payload.config_path)))
    if request.type == "generate_dataset":
        payload = GeneratePayload.model_validate(request.payload)
        from carnopy.config.io import load_config_file
        from carnopy.pipeline import run_generation

        control = ExecutionControl(
            cancellation_requested=cancelled.is_set,
            on_phase=lambda name, cancellable: writer.emit(
                "phase", {"name": name, "cancellable": cancellable}
            ),
            on_progress=lambda completed, total: writer.emit(
                "progress", {"completed": completed, "total": total}
            ),
        )
        result = run_generation(
            load_config_file(payload.config_path),
            payload.output_root,
            payload.figures_root,
            execution=control,
        )
        return cast(dict[str, Any], _jsonable(result))
    raise ValueError(f"worker request type {request.type!r} is not implemented in GUI Stage 1")


def _describe_capabilities(payload: CapabilitiesPayload) -> dict[str, Any]:
    from carnopy.backends.coolprop import CoolPropBackend
    from carnopy.backends.coolprop_models import supported_properties
    from carnopy.domain.properties import PROPERTY_REGISTRY

    backend = CoolPropBackend(model=payload.model)
    properties = [
        PROPERTY_REGISTRY[name].metadata() for name in supported_properties(payload.model)
    ]
    fluids = [
        {"name": fluid, "aliases": list(backend.aliases_for(fluid))}
        for fluid in backend.list_fluids()
    ]
    return {
        "backend": backend.name,
        "backend_version": backend.version,
        "model": backend.model,
        "fluids": fluids,
        "properties": properties,
    }


def _listen_for_cancellation(
    stream: IO[str],
    stderr: IO[str],
    request_id: UUID,
    cancelled: threading.Event,
) -> None:
    for line in stream:
        try:
            request = parse_request(line)
        except ValidationError as exc:
            stderr.write(f"ignored invalid worker control message: {exc}\n")
            stderr.flush()
            continue
        if request.type == "cancel" and request.request_id == request_id:
            cancelled.set()
            return
        stderr.write("ignored non-cancel or mismatched worker control message\n")
        stderr.flush()


def _protocol_failure(stdout: IO[str], stderr: IO[str], message: str) -> int:
    stderr.write(message + "\n")
    EventWriter(stdout, SYSTEM_REQUEST_ID).emit(
        "error", {"category": "protocol", "message": message}
    )
    return 2


def _jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    json.dumps(value)
    return value


if __name__ == "__main__":  # pragma: no cover - subprocess entry point
    raise SystemExit(main())
