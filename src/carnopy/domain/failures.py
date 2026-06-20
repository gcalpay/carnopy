from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

FailureLayer = Literal["state", "domain", "backend"]

T = TypeVar("T")


@dataclass(frozen=True)
class BackendResult(Generic[T]):
    value: T | None
    valid: bool
    failure_layer: FailureLayer | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    backend_error_type: str | None = None
    backend_error_message: str | None = None

    @classmethod
    def success(cls, value: T) -> BackendResult[T]:
        return cls(value=value, valid=True)

    @classmethod
    def failure(
        cls,
        *,
        layer: FailureLayer,
        code: str,
        message: str,
        error: Exception | None = None,
    ) -> BackendResult[T]:
        return cls(
            value=None,
            valid=False,
            failure_layer=layer,
            failure_code=code,
            failure_message=message,
            backend_error_type=type(error).__name__ if error is not None else None,
            backend_error_message=str(error) if error is not None else None,
        )


class CarnopyError(Exception):
    """Base class for structured Carnopy failures."""


class ConfigError(CarnopyError):
    """Configuration or normalization failed before generation."""


class BackendInitializationError(CarnopyError):
    """The configured backend could not be initialized safely."""


class OutputError(CarnopyError):
    """Run artifacts could not be finalized."""
