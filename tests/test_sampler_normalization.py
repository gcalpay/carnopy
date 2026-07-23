from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

import pytest

import carnopy.config.normalize as normalize_module
from carnopy.config.models import CarnopyConfig
from carnopy.config.normalize import canonical_json_bytes, normalize_config
from carnopy.domain.failures import ConfigError
from carnopy.provenance import build_identity, sha256_bytes
from carnopy.sampling.canonical import canonical_sampler_key, canonicalize_sampler
from carnopy.sampling.models import (
    ExplicitSampler,
    GeomspaceSampler,
    LinspaceSampler,
    LogspaceSampler,
    Sampler,
    StepspaceSampler,
)


class NormalizationBackend:
    name = "coolprop"
    model = "heos"
    version = "8.0.0"

    def canonicalize_fluid(self, fluid: str) -> str:
        assert fluid == "Propane"
        return "n-Propane"

    def unsupported_properties(self, _properties: list[str]) -> list[str]:
        return []


SamplerFactory = Callable[[], Sampler]


PRESSURE_EQUIVALENTS: tuple[tuple[SamplerFactory, SamplerFactory], ...] = (
    (
        lambda: ExplicitSampler(kind="explicit", values=[100.0, 200.0], unit="Pa"),
        lambda: ExplicitSampler(kind="explicit", values=[1.0, 2.0], unit="hPa"),
    ),
    (
        lambda: ExplicitSampler(kind="explicit", values=[101_325.0, 202_650.0], unit="Pa"),
        lambda: ExplicitSampler(kind="explicit", values=[1.0, 2.0], unit="atm"),
    ),
    (
        lambda: ExplicitSampler(kind="explicit", values=[100_000.0, 200_000.0], unit="Pa"),
        lambda: ExplicitSampler(kind="explicit", values=[1.0, 2.0], unit="bar"),
    ),
    (
        lambda: LinspaceSampler(kind="linspace", start=100_000.0, stop=300_000.0, num=3, unit="Pa"),
        lambda: LinspaceSampler(kind="linspace", start=1.0, stop=3.0, num=3, unit="bar"),
    ),
    (
        lambda: StepspaceSampler(
            kind="stepspace",
            start=100_000.0,
            stop=300_000.0,
            step=100_000.0,
            unit="Pa",
        ),
        lambda: StepspaceSampler(kind="stepspace", start=1.0, stop=3.0, step=1.0, unit="bar"),
    ),
    (
        lambda: GeomspaceSampler(
            kind="geomspace", start=100_000.0, stop=10_000_000.0, num=3, unit="Pa"
        ),
        lambda: GeomspaceSampler(kind="geomspace", start=1.0, stop=100.0, num=3, unit="bar"),
    ),
    (
        lambda: LogspaceSampler(
            kind="logspace", start_exp=5.0, stop_exp=7.0, num=3, base=10.0, unit="Pa"
        ),
        lambda: LogspaceSampler(
            kind="logspace", start_exp=0.0, stop_exp=2.0, num=3, base=10.0, unit="bar"
        ),
    ),
)


@pytest.mark.parametrize(
    ("axis", "sampler"),
    [
        ("temperature", ExplicitSampler(kind="explicit", values=[-20, 40], unit="degC")),
        (
            "temperature",
            LinspaceSampler(kind="linspace", start=-20, stop=40, num=4, unit="degC"),
        ),
        (
            "temperature",
            StepspaceSampler(kind="stepspace", start=-20, stop=40, step=20, unit="degC"),
        ),
        (
            "temperature",
            GeomspaceSampler(kind="geomspace", start=200, stop=400, num=4, unit="K"),
        ),
        (
            "temperature",
            LogspaceSampler(kind="logspace", start_exp=2.3, stop_exp=2.6, num=4, base=10, unit="K"),
        ),
        (
            "vapor_mass_fraction",
            ExplicitSampler(kind="explicit", values=[0, 0.5, 1], unit="1"),
        ),
        (
            "vapor_mass_fraction",
            LinspaceSampler(kind="linspace", start=0, stop=1, num=5, unit="1"),
        ),
        (
            "vapor_mass_fraction",
            StepspaceSampler(kind="stepspace", start=0, stop=1, step=0.25, unit="1"),
        ),
    ],
)
def test_every_supported_axis_sampler_family_canonicalizes_deterministically(
    axis: str,
    sampler: Sampler,
) -> None:
    first = canonicalize_sampler(axis, sampler)
    second = canonicalize_sampler(axis, sampler)

    assert first == second
    assert canonical_sampler_key(axis, first) == canonical_sampler_key(axis, sampler)


@pytest.mark.parametrize(("si_factory", "declared_factory"), PRESSURE_EQUIVALENTS)
def test_equivalent_pressure_definitions_have_exact_canonical_keys(
    si_factory: SamplerFactory,
    declared_factory: SamplerFactory,
) -> None:
    si_sampler = si_factory()
    declared_sampler = declared_factory()

    assert canonical_sampler_key("pressure", si_sampler) == canonical_sampler_key(
        "pressure", declared_sampler
    )
    assert canonicalize_sampler("pressure", declared_sampler) == canonicalize_sampler(
        "pressure", declared_sampler
    )


@pytest.mark.parametrize(
    ("si_sampler", "declared_sampler"),
    [
        (
            ExplicitSampler(kind="explicit", values=[273.15, 300.0], unit="K"),
            ExplicitSampler(kind="explicit", values=[0.0, 26.85], unit="degC"),
        ),
        (
            LinspaceSampler(kind="linspace", start=273.15, stop=373.15, num=5, unit="K"),
            LinspaceSampler(kind="linspace", start=0.0, stop=100.0, num=5, unit="degC"),
        ),
        (
            StepspaceSampler(kind="stepspace", start=273.15, stop=373.15, step=25.0, unit="K"),
            StepspaceSampler(kind="stepspace", start=0.0, stop=100.0, step=25.0, unit="degC"),
        ),
    ],
)
def test_affine_temperature_definitions_have_exact_canonical_keys(
    si_sampler: Sampler,
    declared_sampler: Sampler,
) -> None:
    assert canonical_sampler_key("temperature", si_sampler) == canonical_sampler_key(
        "temperature", declared_sampler
    )


@pytest.mark.parametrize(
    ("value", "unit", "si_value"),
    [
        (1_013.25, "hPa", 101_325.0),
        (1.0, "atm", 101_325.0),
    ],
)
def test_added_pressure_units_have_exact_canonical_keys(
    value: float,
    unit: str,
    si_value: float,
) -> None:
    declared = ExplicitSampler(kind="explicit", values=[value], unit=unit)
    si_sampler = ExplicitSampler(kind="explicit", values=[si_value], unit="Pa")

    assert canonical_sampler_key("pressure", declared) == canonical_sampler_key(
        "pressure", si_sampler
    )


@pytest.mark.parametrize(("si_factory", "declared_factory"), PRESSURE_EQUIVALENTS)
def test_equal_keys_produce_identical_production_identity(
    si_factory: SamplerFactory,
    declared_factory: SamplerFactory,
) -> None:
    backend = NormalizationBackend()
    si_config = _property_config(si_factory())
    declared_config = _property_config(declared_factory())

    si_normalized = normalize_config(si_config, backend)  # type: ignore[arg-type]
    declared_normalized = normalize_config(declared_config, backend)  # type: ignore[arg-type]
    si_bytes = canonical_json_bytes(si_normalized.executable_dict())
    declared_bytes = canonical_json_bytes(declared_normalized.executable_dict())
    si_identity = build_identity(
        raw_config=b"declared in Pa\n",
        normalized_config=si_bytes,
        backend_name=backend.name,
        backend_model=backend.model,
        backend_version=backend.version,
    )
    declared_identity = build_identity(
        raw_config=b"declared in bar\n",
        normalized_config=declared_bytes,
        backend_name=backend.name,
        backend_model=backend.model,
        backend_version=backend.version,
    )

    assert si_normalized.grid == declared_normalized.grid
    assert si_bytes == declared_bytes
    assert sha256_bytes(si_bytes) == sha256_bytes(declared_bytes)
    assert si_identity.normalized_config_sha256 == declared_identity.normalized_config_sha256
    assert si_identity.spec_id == declared_identity.spec_id
    assert si_normalized.original_grid["pressure"] != declared_normalized.original_grid["pressure"]


def test_canonicalizer_rejects_unsupported_axis_sampler_combinations() -> None:
    with pytest.raises(ValueError, match="requires unit K"):
        canonicalize_sampler(
            "temperature",
            GeomspaceSampler(kind="geomspace", start=1.0, stop=100.0, num=3, unit="degC"),
        )
    with pytest.raises(ValueError, match="unsupported for vapor_mass_fraction"):
        canonicalize_sampler(
            "vapor_mass_fraction",
            LogspaceSampler(kind="logspace", start_exp=-2.0, stop_exp=0.0, num=3, unit="1"),
        )


def test_lightweight_sampler_import_does_not_import_numpy() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import carnopy.sampling.canonical; assert 'numpy' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_row_limit_is_rejected_before_sampler_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = CarnopyConfig.model_validate(
        {
            "schema_version": 2,
            "document_type": "dataset",
            "backend": {"name": "coolprop", "model": "heos"},
            "mode": "property_table",
            "fluids": ["Propane"],
            "grid": {
                "temperature": {
                    "kind": "linspace",
                    "start": 280.0,
                    "stop": 320.0,
                    "num": 1_000_000,
                    "unit": "K",
                },
                "pressure": {
                    "kind": "explicit",
                    "values": [100_000.0, 200_000.0],
                    "unit": "Pa",
                },
            },
            "properties": ["mass_density"],
        }
    )

    def unexpected_materialization(_sampler: Sampler) -> list[float]:
        raise AssertionError("oversized projections must fail before array allocation")

    monkeypatch.setattr(normalize_module, "materialize_sampler", unexpected_materialization)

    with pytest.raises(ConfigError, match="2,000,000 exceeds limit 1,000,000"):
        normalize_config(config, NormalizationBackend())  # type: ignore[arg-type]


def _property_config(pressure: Sampler) -> CarnopyConfig:
    return CarnopyConfig.model_validate(
        {
            "schema_version": 2,
            "document_type": "dataset",
            "backend": {"name": "coolprop", "model": "heos"},
            "mode": "property_table",
            "fluids": ["Propane"],
            "grid": {
                "temperature": {
                    "kind": "explicit",
                    "values": [300.0],
                    "unit": "K",
                },
                "pressure": pressure.model_dump(mode="json"),
            },
            "properties": ["mass_density"],
        }
    )
