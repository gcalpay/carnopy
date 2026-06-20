from __future__ import annotations

import CoolProp.CoolProp as CP

from carnopy.backends import CoolPropBackend


def test_backend_lists_and_canonicalizes_fluids() -> None:
    backend = CoolPropBackend()
    assert backend.list_fluids()
    assert backend.canonicalize_fluid("Propane") == "n-Propane"
    assert backend.canonicalize_fluid("R290") == "n-Propane"


def test_backend_property_and_phase_calls_work() -> None:
    backend = CoolPropBackend()
    density = backend.property("DMASS", "n-Propane", "T", 300.0, "P", 100_000.0)
    phase = backend.phase("n-Propane", "T", 300.0, "P", 100_000.0)
    assert density.valid and density.value is not None and density.value > 0
    assert phase.valid and phase.value


def test_reference_state_is_initialized_once_per_fluid(monkeypatch: object) -> None:
    calls: list[tuple[str, str]] = []

    def record(fluid: str, state: str) -> None:
        calls.append((fluid, state))

    monkeypatch.setattr(CP, "set_reference_state", record)  # type: ignore[attr-defined]
    CoolPropBackend().initialize_reference_states(["n-Propane", "Water"])
    assert calls == [("n-Propane", "DEF"), ("Water", "DEF")]
