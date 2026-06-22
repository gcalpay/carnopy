from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DatasetFormat = Literal["csv", "parquet"]
DATASET_FORMAT_ORDER: tuple[DatasetFormat, ...] = ("csv", "parquet")


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_formats: tuple[DatasetFormat, ...] = Field(
        default=DATASET_FORMAT_ORDER,
        min_length=1,
    )

    @field_validator("dataset_formats")
    @classmethod
    def canonical_dataset_formats(
        cls,
        formats: tuple[DatasetFormat, ...],
    ) -> tuple[DatasetFormat, ...]:
        if len(set(formats)) != len(formats):
            raise ValueError("duplicate dataset formats are not allowed")
        selected = set(formats)
        return tuple(item for item in DATASET_FORMAT_ORDER if item in selected)
