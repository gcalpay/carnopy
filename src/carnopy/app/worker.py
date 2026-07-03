from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import threading
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from carnopy._execution import ExecutionCancelled, ExecutionControl
from carnopy.app.protocol import (
    ErrorCategory,
    EventType,
    WorkerErrorPayload,
    WorkerEvent,
    WorkerRequest,
    encode_event,
    parse_request,
)
from carnopy.domain.failures import CarnopyError, ConfigError

if TYPE_CHECKING:
    from carnopy.config.io import LoadedConfig

SYSTEM_REQUEST_ID = UUID(int=0)


class SourceChangedError(ValueError):
    """The saved configuration no longer matches the GUI expectation."""


class UnsupportedRequestError(ValueError):
    """A declared protocol request has no worker implementation yet."""


class CapabilitiesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Literal["heos", "pr", "srk"] = "heos"


class ValidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    config_path: Path


class ExecutionConfigPayload(ValidatePayload):
    expected_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ValidateDatasetTextPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    yaml_text: str
    source_name: str = "<gui>"


class GeneratePayload(ExecutionConfigPayload):
    output_root: Path
    figures_root: Path = Path("figures")


class InspectPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_path: Path


class PreviewPayload(InspectPayload):
    table_id: str = Field(min_length=1)
    inspection_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)


class EventWriter:
    def __init__(self, stream: IO[str], request_id: UUID) -> None:
        self._stream = stream
        self._request_id = request_id

    def emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        event = WorkerEvent(
            request_id=self._request_id,
            type=event_type,
            payload=cast(dict[str, Any], _jsonable(payload)),
        )
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
        writer.emit(
            "error",
            _error_payload(
                "protocol",
                "cancel_not_primary",
                "cancel is not a primary request",
            ),
        )
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
        writer.emit("cancelled", {"code": "cancelled", "message": str(exc)})
        return 0
    except SourceChangedError as exc:
        writer.emit("error", _error_payload("config", "source_changed", str(exc)))
        return 1
    except ConfigError as exc:
        writer.emit("error", _config_error_payload(exc))
        return 1
    except CarnopyError as exc:
        writer.emit(
            "error",
            _error_payload("execution", "execution_failed", str(exc)),
        )
        return 1
    except UnsupportedRequestError as exc:
        writer.emit(
            "error",
            _error_payload("protocol", "unsupported_request", str(exc)),
        )
        return 2
    except (ValidationError, OSError, ValueError) as exc:
        details = _validation_details(exc) if isinstance(exc, ValidationError) else None
        writer.emit(
            "error",
            _error_payload("request", "invalid_payload", str(exc), details),
        )
        return 2
    except Exception as exc:  # pragma: no cover - defensive process boundary
        traceback.print_exc(file=stderr)
        writer.emit(
            "error",
            _error_payload(
                "internal",
                "unexpected_failure",
                f"unexpected worker failure: {type(exc).__name__}",
            ),
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
        from carnopy.app.capabilities import describe_capabilities

        capabilities = CapabilitiesPayload.model_validate(request.payload)
        return cast(dict[str, Any], describe_capabilities(capabilities.model))
    if request.type == "load_dataset_config":
        load_payload = ValidatePayload.model_validate(request.payload)
        writer.emit("phase", {"name": "validation", "cancellable": True})
        from carnopy.config.io import load_config_file

        return _validated_dataset_payload(load_config_file(load_payload.config_path))
    if request.type == "validate_dataset_config":
        text_payload = ValidateDatasetTextPayload.model_validate(request.payload)
        writer.emit("phase", {"name": "validation", "cancellable": True})
        from carnopy.config.io import load_config_bytes

        loaded = load_config_bytes(
            text_payload.yaml_text.encode("utf-8"),
            source_name=text_payload.source_name,
        )
        return _validated_dataset_payload(loaded)
    if request.type == "validate_config":
        payload = ExecutionConfigPayload.model_validate(request.payload)
        writer.emit("phase", {"name": "validation", "cancellable": True})
        loaded = _load_expected_config(payload)
        from carnopy.pipeline import validate_loaded_config

        return cast(dict[str, Any], _jsonable(validate_loaded_config(loaded).result))
    if request.type == "generate_dataset":
        payload = GeneratePayload.model_validate(request.payload)
        loaded = _load_expected_config(payload)
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
            loaded,
            payload.output_root,
            payload.figures_root,
            execution=control,
        )
        return cast(dict[str, Any], _jsonable(result))
    if request.type == "inspect_source":
        inspect_payload = InspectPayload.model_validate(request.payload)
        writer.emit("phase", {"name": "inspection", "cancellable": True})
        from carnopy.app.source_inspection import inspect_for_app

        return inspect_for_app(inspect_payload.source_path).public_payload()
    if request.type == "preview_table":
        preview_payload = PreviewPayload.model_validate(request.payload)
        writer.emit("phase", {"name": "table_preview", "cancellable": True})
        from carnopy.app.source_inspection import resolve_table
        from carnopy.app.table_preview import preview_table

        table = resolve_table(
            preview_payload.source_path,
            preview_payload.table_id,
            preview_payload.inspection_revision,
        )
        return preview_table(
            table,
            offset=preview_payload.offset,
            limit=preview_payload.limit,
        )
    raise UnsupportedRequestError(
        f"worker request type {request.type!r} is not implemented by this worker"
    )


def _load_expected_config(payload: ExecutionConfigPayload) -> LoadedConfig:
    raw_bytes = payload.config_path.read_bytes()
    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if actual_sha256 != payload.expected_config_sha256:
        raise SourceChangedError(
            f"saved configuration changed after the GUI recorded it: {payload.config_path}"
        )
    from carnopy.config.io import load_config_bytes

    return load_config_bytes(raw_bytes, source_name=str(payload.config_path))


def _validated_dataset_payload(loaded: LoadedConfig) -> dict[str, Any]:
    from carnopy.pipeline import validate_loaded_config

    validated = validate_loaded_config(loaded)
    return {
        "config": loaded.model.model_dump(mode="json", by_alias=True, exclude_none=True),
        "source_name": str(loaded.path),
        "source_sha256": hashlib.sha256(loaded.raw_bytes).hexdigest(),
        "validation": asdict(validated.result),
        "requested_fluid_canonical_names": list(
            validated.normalized.requested_fluid_canonical_names
        ),
    }


def _config_error_payload(error: ConfigError) -> dict[str, Any]:
    details: dict[str, Any] | None = None
    cause: BaseException | None = error.__cause__
    while cause is not None and not isinstance(cause, ValidationError):
        cause = cause.__cause__
    if isinstance(cause, ValidationError):
        details = _validation_details(cause)
    return _error_payload("config", "invalid_config", str(error), details)


def _validation_details(error: ValidationError) -> dict[str, Any]:
    return {
        "issues": [
            {
                "path": ".".join(str(item) for item in issue["loc"]) or "$",
                "code": str(issue["type"]),
                "message": str(issue["msg"]),
            }
            for issue in error.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )
        ]
    }


def _error_payload(
    category: ErrorCategory,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return WorkerErrorPayload(
        category=category,
        code=code,
        message=message,
        details=details,
    ).model_dump(mode="json", exclude_none=True)


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
        "error", _error_payload("protocol", "invalid_request", message)
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
