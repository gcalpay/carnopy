from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from carnopy._execution import ExecutionControl
from carnopy.app.protocol import EventType, RequestType
from carnopy.domain.failures import CarnopyError, ConfigError

EmitEvent = Callable[[EventType, dict[str, Any]], None]

WORKFLOW_REQUESTS: frozenset[RequestType] = frozenset(
    {
        "load_sweep_config",
        "validate_sweep_config",
        "plan_sweep",
        "execute_sweep",
        "load_preparation_config",
        "validate_preparation_config",
        "plan_preparation",
        "execute_preparation",
    }
)


class WorkflowSourceChangedError(ValueError):
    """A saved workflow configuration or inspected source changed."""


class StalePlanError(ValueError):
    """Execution did not reproduce the expected worker plan ID."""


class LoadWorkflowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    config_path: Path


class ValidateWorkflowTextPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    yaml_text: str
    source_name: str = "<gui>"


class SavedWorkflowPayload(LoadWorkflowPayload):
    expected_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configs_root: Path


class ExecuteSweepPayload(SavedWorkflowPayload):
    expected_plan_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_root: Path


class PlanPreparationPayload(SavedWorkflowPayload):
    source_path: Path
    inspection_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    inspection_descriptor: dict[str, Any]


class ExecutePreparationPayload(PlanPreparationPayload):
    expected_plan_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_root: Path


def execute_workflow_request(
    request_type: RequestType,
    payload: dict[str, Any],
    *,
    emit: EmitEvent,
    cancellation_requested: Callable[[], bool],
) -> dict[str, Any]:
    if request_type == "load_sweep_config":
        load_sweep = LoadWorkflowPayload.model_validate(payload)
        emit("phase", {"name": "validation", "cancellable": True})
        from carnopy.config.io import load_sweep_config_file

        return _loaded_payload(load_sweep_config_file(load_sweep.config_path))
    if request_type == "validate_sweep_config":
        validate_sweep = ValidateWorkflowTextPayload.model_validate(payload)
        emit("phase", {"name": "validation", "cancellable": True})
        from carnopy.config.io import load_sweep_config_bytes

        return _validated_text_payload(
            validate_sweep.yaml_text,
            validate_sweep.source_name,
            loader=load_sweep_config_bytes,
        )
    if request_type == "plan_sweep":
        plan_sweep_payload = SavedWorkflowPayload.model_validate(payload)
        emit("phase", {"name": "planning", "cancellable": True})
        loaded = _load_expected_sweep(plan_sweep_payload)
        control = _control(emit, cancellation_requested)
        control.raise_if_cancelled()
        from carnopy.app.workflow_planning import plan_sweep

        return plan_sweep(loaded)
    if request_type == "execute_sweep":
        execute_sweep = ExecuteSweepPayload.model_validate(payload)
        loaded = _load_expected_sweep(execute_sweep)
        from carnopy.app.workflow_planning import plan_sweep_with_normalized

        current_plan, normalized = plan_sweep_with_normalized(loaded)
        _require_plan_id(current_plan, execute_sweep.expected_plan_id)
        from carnopy.sweeps.pipeline import _run_model_sweep

        return _jsonable_result(
            _run_model_sweep(
                loaded,
                normalized,
                execute_sweep.output_root,
                execution=_control(emit, cancellation_requested),
            )
        )
    if request_type == "load_preparation_config":
        load_preparation = LoadWorkflowPayload.model_validate(payload)
        emit("phase", {"name": "validation", "cancellable": True})
        from carnopy.preparation.models import load_preparation_config

        return _loaded_payload(load_preparation_config(load_preparation.config_path))
    if request_type == "validate_preparation_config":
        validate_preparation = ValidateWorkflowTextPayload.model_validate(payload)
        emit("phase", {"name": "validation", "cancellable": True})
        from carnopy.preparation.models import load_preparation_config_bytes

        return _validated_text_payload(
            validate_preparation.yaml_text,
            validate_preparation.source_name,
            loader=load_preparation_config_bytes,
        )
    if request_type == "plan_preparation":
        plan_preparation_payload = PlanPreparationPayload.model_validate(payload)
        loaded = _load_expected_preparation(plan_preparation_payload)
        _revalidate_inspection(plan_preparation_payload)
        control = _control(emit, cancellation_requested)
        control.phase("preparation_planning")
        from carnopy.app.workflow_planning import plan_preparation

        plan, _computation = plan_preparation(
            loaded,
            str(plan_preparation_payload.source_path),
            inspection_revision=plan_preparation_payload.inspection_revision,
            inspection_descriptor=plan_preparation_payload.inspection_descriptor,
            checkpoint=control.checkpoint,
            cancellation_checkpoint=control.raise_if_cancelled,
        )
        _revalidate_inspection(plan_preparation_payload)
        return plan
    if request_type == "execute_preparation":
        execute_preparation = ExecutePreparationPayload.model_validate(payload)
        loaded = _load_expected_preparation(execute_preparation)
        _revalidate_inspection(execute_preparation)
        control = _control(emit, cancellation_requested)
        control.phase("preparation_planning")
        from carnopy.app.workflow_planning import plan_preparation

        current_plan, computation = plan_preparation(
            loaded,
            str(execute_preparation.source_path),
            inspection_revision=execute_preparation.inspection_revision,
            inspection_descriptor=execute_preparation.inspection_descriptor,
            checkpoint=control.checkpoint,
            cancellation_checkpoint=control.raise_if_cancelled,
        )
        _revalidate_inspection(execute_preparation)
        _require_plan_id(current_plan, execute_preparation.expected_plan_id)
        from carnopy.preparation.pipeline import execute_preparation_computation

        return _jsonable_result(
            execute_preparation_computation(
                computation,
                output_root=execute_preparation.output_root,
                execution=control,
                source_revalidator=lambda: _revalidate_inspection(execute_preparation),
            )
        )
    raise ValueError(f"not a workflow request: {request_type}")


def _load_expected_sweep(payload: SavedWorkflowPayload) -> Any:
    raw_bytes, source_name = _expected_saved_bytes(payload)
    from carnopy.config.io import load_sweep_config_bytes

    return load_sweep_config_bytes(raw_bytes, source_name=source_name)


def _load_expected_preparation(payload: SavedWorkflowPayload) -> Any:
    raw_bytes, source_name = _expected_saved_bytes(payload)
    from carnopy.preparation.models import load_preparation_config_bytes

    return load_preparation_config_bytes(raw_bytes, source_name=source_name)


def _expected_saved_bytes(payload: SavedWorkflowPayload) -> tuple[bytes, str]:
    path = payload.config_path.expanduser().absolute()
    root = payload.configs_root.expanduser().resolve(strict=True)
    if path.is_symlink():
        raise WorkflowSourceChangedError(f"saved configuration is a symbolic link: {path}")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise WorkflowSourceChangedError(
            "workflow planning and execution require a saved configuration under "
            f"the active workspace configs directory: {path}"
        ) from exc
    raw_bytes = _stable_file_bytes(resolved)
    if hashlib.sha256(raw_bytes).hexdigest() != payload.expected_config_sha256:
        raise WorkflowSourceChangedError(
            f"saved configuration changed after its identity was recorded: {resolved}"
        )
    return raw_bytes, str(resolved)


def _stable_file_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise WorkflowSourceChangedError(f"configuration is not a regular file: {path}")
            raw_bytes = stream.read()
            after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
    except WorkflowSourceChangedError:
        raise
    except OSError as exc:
        raise WorkflowSourceChangedError(
            f"could not read saved configuration {path}: {exc}"
        ) from exc
    if _stat_identity(before) != _stat_identity(after) or _stat_identity(before) != _stat_identity(
        current
    ):
        raise WorkflowSourceChangedError(f"saved configuration changed while reading: {path}")
    return raw_bytes


def _revalidate_inspection(payload: PlanPreparationPayload) -> None:
    from carnopy.app.source_inspection import revalidate_preparation_inspection

    try:
        revalidate_preparation_inspection(
            payload.source_path,
            inspection_revision=payload.inspection_revision,
            inspection_descriptor=payload.inspection_descriptor,
        )
    except (CarnopyError, OSError) as exc:
        raise WorkflowSourceChangedError(
            "preparation source changed after inspection; refresh Inspect and plan again"
        ) from exc


def _require_plan_id(plan: dict[str, Any], expected: str) -> None:
    if plan.get("plan_id") != expected:
        raise StalePlanError("workflow plan changed; create a new plan before executing")


def _control(
    emit: EmitEvent,
    cancellation_requested: Callable[[], bool],
) -> ExecutionControl:
    return ExecutionControl(
        cancellation_requested=cancellation_requested,
        on_phase=lambda name, cancellable: emit(
            "phase", {"name": name, "cancellable": cancellable}
        ),
        on_progress=lambda completed, total: emit(
            "progress", {"completed": completed, "total": total}
        ),
        on_protected_phase=lambda name: emit(
            "phase",
            {
                "name": name,
                "cancellable": False,
                "termination_protected": True,
            },
        ),
    )


def _loaded_payload(loaded: Any) -> dict[str, Any]:
    return {
        "config": loaded.model.model_dump(mode="json", by_alias=True, exclude_none=True),
        "source_name": str(loaded.path),
        "source_sha256": hashlib.sha256(loaded.raw_bytes).hexdigest(),
    }


def _validated_text_payload(
    yaml_text: str,
    source_name: str,
    *,
    loader: Callable[..., Any],
) -> dict[str, Any]:
    raw_bytes = yaml_text.encode("utf-8")
    try:
        loaded = loader(raw_bytes, source_name=source_name)
    except ConfigError as exc:
        return {
            "valid": False,
            "source_name": source_name,
            "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "error": {
                "code": "invalid_config",
                "message": str(exc),
                "issues": _validation_issues(exc),
            },
        }
    return {"valid": True, **_loaded_payload(loaded)}


def _validation_issues(error: ConfigError) -> list[dict[str, str]]:
    cause: BaseException | None = error.__cause__
    while cause is not None and not isinstance(cause, ValidationError):
        cause = cause.__cause__
    if not isinstance(cause, ValidationError):
        return []
    return [
        {
            "path": ".".join(str(item) for item in issue["loc"]) or "$",
            "code": str(issue["type"]),
            "message": str(issue["msg"]),
        }
        for issue in cause.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        )
    ]


def _jsonable_result(value: Any) -> dict[str, Any]:
    from dataclasses import asdict, is_dataclass

    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError("workflow execution result must be a dataclass")
    return cast(dict[str, Any], _jsonable(asdict(value)))


def _jsonable(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns
