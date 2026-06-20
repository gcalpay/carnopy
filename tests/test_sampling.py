from __future__ import annotations

import pytest
from pydantic import ValidationError

from carnopy.sampling.generate import materialize_sampler
from carnopy.sampling.models import (
    GeomspaceSampler,
    LinspaceSampler,
    LogspaceSampler,
    StepspaceSampler,
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


def test_equal_bounds_are_rejected() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        LinspaceSampler(kind="linspace", start=1, stop=1, num=2, unit="Pa")
