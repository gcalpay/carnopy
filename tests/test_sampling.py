from __future__ import annotations

import subprocess
import sys

import pytest
from pydantic import ValidationError

from carnopy.sampling.generate import materialize_sampler
from carnopy.sampling.models import (
    ExplicitSampler,
    GeomspaceSampler,
    LinspaceSampler,
    LogspaceSampler,
    Sampler,
    StepspaceSampler,
)
from carnopy.sampling.projection import (
    linspace_spacing,
    projected_row_count,
    sampler_point_count,
)


def test_stepspace_is_inclusive_and_descending() -> None:
    ascending = StepspaceSampler(kind="stepspace", start=-30, stop=80, step=2, unit="degC")
    descending = StepspaceSampler(kind="stepspace", start=3, stop=1, step=-1, unit="bar")
    assert materialize_sampler(ascending)[-1] == 80.0
    assert materialize_sampler(descending) == [3.0, 2.0, 1.0]


def test_stepspace_rejects_unreachable_stop() -> None:
    sampler = StepspaceSampler(kind="stepspace", start=0, stop=1, step=0.3, unit="K")
    with pytest.raises(ValueError, match="not reachable"):
        materialize_sampler(sampler)


def test_bounded_samplers_support_descending_order() -> None:
    linear = LinspaceSampler(kind="linspace", start=3, stop=1, num=3, unit="bar")
    geometric = GeomspaceSampler(kind="geomspace", start=100, stop=1, num=3, unit="Pa")
    logarithmic = LogspaceSampler(kind="logspace", start_exp=2, stop_exp=0, num=3, unit="Pa")
    assert materialize_sampler(linear) == [3.0, 2.0, 1.0]
    assert materialize_sampler(geometric) == [100.0, 10.0, 1.0]
    assert materialize_sampler(logarithmic) == [100.0, 10.0, 1.0]


@pytest.mark.parametrize(
    ("sampler", "expected"),
    [
        (LinspaceSampler(kind="linspace", start=-50, stop=50, num=101, unit="degC"), 1.0),
        (
            LinspaceSampler(kind="linspace", start=50, stop=-50, num=101, unit="degC"),
            -1.0,
        ),
        (
            LinspaceSampler(kind="linspace", start=-50, stop=50, num=100, unit="degC"),
            1.01010101010101,
        ),
    ],
)
def test_linspace_spacing_is_a_lightweight_signed_projection(
    sampler: LinspaceSampler,
    expected: float,
) -> None:
    assert linspace_spacing(sampler) == expected


def test_equal_bounds_are_rejected() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        LinspaceSampler(kind="linspace", start=1, stop=1, num=2, unit="Pa")


def test_package_materializer_preserves_lazy_compatibility() -> None:
    from carnopy.sampling import materialize_sampler as package_materialize

    sampler = LinspaceSampler(kind="linspace", start=1, stop=3, num=3, unit="bar")
    assert package_materialize(sampler) == [1.0, 2.0, 3.0]


@pytest.mark.parametrize(
    "sampler",
    [
        ExplicitSampler(kind="explicit", values=[1.0, 2.0, 3.0], unit="bar"),
        LinspaceSampler(kind="linspace", start=1.0, stop=5.0, num=5, unit="bar"),
        StepspaceSampler(kind="stepspace", start=1.0, stop=5.0, step=1.0, unit="bar"),
        GeomspaceSampler(kind="geomspace", start=1.0, stop=100.0, num=5, unit="bar"),
        LogspaceSampler(
            kind="logspace",
            start_exp=0.0,
            stop_exp=2.0,
            num=5,
            base=10.0,
            unit="bar",
        ),
    ],
)
def test_lightweight_point_count_matches_production_materialization(
    sampler: Sampler,
) -> None:
    assert sampler_point_count(sampler) == len(materialize_sampler(sampler))


@pytest.mark.parametrize(
    ("mode", "fluid_count", "sampler_counts", "expected"),
    [
        ("property_table", 2, [101, 41], 8_282),
        ("saturation_table", 2, [101], 404),
        ("vapor_mass_fraction_table", 2, [101, 11], 2_222),
    ],
)
def test_projected_row_count_matches_mode_expansion(
    mode: str,
    fluid_count: int,
    sampler_counts: list[int],
    expected: int,
) -> None:
    assert projected_row_count(mode, fluid_count, sampler_counts) == expected


def test_lightweight_projection_import_does_not_import_numpy() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import carnopy.sampling.projection; assert 'numpy' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
