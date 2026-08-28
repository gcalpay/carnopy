from __future__ import annotations

from typing import Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION: Final[Literal[1]] = 1

RequestType = Literal[
    "describe_capabilities",
    "load_configuration",
    "validate_configuration",
    "load_dataset_config",
    "validate_dataset_config",
    "validate_config",
    "generate_dataset",
    "inspect_source",
    "profile_scene",
    "build_scene",
    "resolve_scene_pick",
    "preview_table",
    "render_plot",
    "load_sweep_config",
    "validate_sweep_config",
    "plan_sweep",
    "execute_sweep",
    "load_preparation_config",
    "validate_preparation_config",
    "plan_preparation",
    "execute_preparation",
    "cancel",
]
EventType = Literal["accepted", "phase", "progress", "result", "error", "cancelled"]
ErrorCategory = Literal["protocol", "config", "execution", "request", "process", "internal"]


class WorkerErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ErrorCategory
    code: str
    message: str
    details: dict[str, Any] | None = None


class WorkerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal[1]
    request_id: UUID
    type: RequestType
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal[1] = PROTOCOL_VERSION
    request_id: UUID
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)


def parse_request(line: str) -> WorkerRequest:
    return WorkerRequest.model_validate_json(line)


def parse_event(line: str) -> WorkerEvent:
    return WorkerEvent.model_validate_json(line)


def encode_event(event: WorkerEvent) -> str:
    return event.model_dump_json() + "\n"
