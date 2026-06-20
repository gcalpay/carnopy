from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SamplerBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    unit: str


class ExplicitSampler(SamplerBase):
    kind: Literal["explicit"]
    values: list[float] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def finite_values(cls, values: list[float]) -> list[float]:
        if any(not _is_finite(value) for value in values):
            raise ValueError("explicit values must be finite")
        return values


class LinspaceSampler(SamplerBase):
    kind: Literal["linspace"]
    start: float
    stop: float
    num: int = Field(ge=2)

    @model_validator(mode="after")
    def validate_bounds(self) -> LinspaceSampler:
        _validate_distinct_finite(self.start, self.stop)
        return self


class StepspaceSampler(SamplerBase):
    kind: Literal["stepspace"]
    start: float
    stop: float
    step: float

    @model_validator(mode="after")
    def validate_bounds(self) -> StepspaceSampler:
        _validate_distinct_finite(self.start, self.stop)
        if not _is_finite(self.step) or self.step == 0.0:
            raise ValueError("stepspace step must be finite and nonzero")
        if (self.stop - self.start) * self.step <= 0.0:
            raise ValueError("stepspace step direction must match its bounds")
        return self


class GeomspaceSampler(SamplerBase):
    kind: Literal["geomspace"]
    start: float
    stop: float
    num: int = Field(ge=2)

    @model_validator(mode="after")
    def validate_bounds(self) -> GeomspaceSampler:
        _validate_distinct_finite(self.start, self.stop)
        if self.start <= 0.0 or self.stop <= 0.0:
            raise ValueError("geomspace endpoints must be positive")
        return self


class LogspaceSampler(SamplerBase):
    kind: Literal["logspace"]
    start_exp: float
    stop_exp: float
    num: int = Field(ge=2)
    base: float = 10.0

    @model_validator(mode="after")
    def validate_bounds(self) -> LogspaceSampler:
        _validate_distinct_finite(self.start_exp, self.stop_exp)
        if not _is_finite(self.base) or self.base <= 1.0:
            raise ValueError("logspace base must be finite and greater than 1")
        return self


Sampler = Annotated[
    ExplicitSampler | LinspaceSampler | StepspaceSampler | GeomspaceSampler | LogspaceSampler,
    Field(discriminator="kind"),
]


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def _validate_distinct_finite(start: float, stop: float) -> None:
    if not _is_finite(start) or not _is_finite(stop):
        raise ValueError("sampler bounds must be finite")
    if start == stop:
        raise ValueError("sampler bounds must be distinct; use explicit for one value")
