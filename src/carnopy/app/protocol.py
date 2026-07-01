from __future__ import annotations

from typing import Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION: Final[Literal[1]] = 1

RequestType = Literal[
    "describe_capabilities",
    "validate_config",
    "generate_dataset",
    "inspect_source",
    "preview_table",
    "render_plot",
    "cancel",
]
EventType = Literal["accepted", "phase", "progress", "result", "error", "cancelled"]


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


def encode_event(event: WorkerEvent) -> str:
    return event.model_dump_json() + "\n"
