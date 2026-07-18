from __future__ import annotations

import CoolProp.CoolProp as CP
import pytest

from carnopy.backends import CoolPropBackend


def test_backend_lists_and_canonicalizes_fluids() -> None:
    backend = CoolPropBackend()
    assert backend.list_fluids()
    assert backend.canonicalize_fluid("Propane") == "n-Propane"
    assert backend.canonicalize_fluid("R290") == "n-Propane"


def test_heos_fluid_listing_uses_compiled_registry_without_state_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = sorted(str(fluid) for fluid in CP.FluidsList())

    def unexpected_state_probe(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("HEOS capability discovery must not instantiate every fluid")

    monkeypatch.setattr(CP, "AbstractState", unexpected_state_probe)

    assert CoolPropBackend(model="heos").list_fluids() == expected


def test_cubic_backend_lists_only_model_supported_fluids() -> None:
    backend = CoolPropBackend(model="pr")
    assert "n-Propane" in backend.list_fluids()
    assert "Air" not in backend.list_fluids()
    with pytest.raises(ValueError, match="model pr does not support pure fluid"):
        backend.canonicalize_fluid("Air")


def test_backend_property_and_phase_calls_work() -> None:
    backend = CoolPropBackend()
    density = backend.property("DMASS", "n-Propane", "T", 300.0, "P", 100_000.0)
    phase = backend.phase("n-Propane", "T", 300.0, "P", 100_000.0)
    assert density.valid and density.value is not None and density.value > 0
    assert phase.valid and phase.value


@pytest.mark.parametrize(
    ("model", "prefix"),
    [("heos", "HEOS"), ("pr", "PR"), ("srk", "SRK")],
)
def test_reference_state_is_initialized_once_per_fluid(
    monkeypatch: object,
    model: str,
    prefix: str,
) -> None:
    calls: list[tuple[str, str]] = []

    def record(fluid: str, state: str) -> None:
        calls.append((fluid, state))

    monkeypatch.setattr(CP, "set_reference_state", record)  # type: ignore[attr-defined]
    CoolPropBackend(model=model).initialize_reference_states(  # type: ignore[arg-type]
        ["n-Propane", "Water"]
    )
    assert calls == [(f"{prefix}::n-Propane", "DEF"), (f"{prefix}::Water", "DEF")]


def test_backend_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="unsupported CoolProp model"):
        CoolPropBackend(model="invalid")  # type: ignore[arg-type]
