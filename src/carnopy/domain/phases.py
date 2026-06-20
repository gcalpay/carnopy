from __future__ import annotations

from typing import Final

PHASE_MAP: Final[dict[str, str]] = {
    "liquid": "liquid",
    "gas": "gas",
    "twophase": "two_phase",
    "two_phase": "two_phase",
    "supercritical": "supercritical",
    "supercritical_liquid": "supercritical_liquid",
    "supercritical_gas": "supercritical_gas",
    "critical_point": "critical_point",
    "unknown": "unknown",
}


def normalize_phase(backend_phase: str) -> str:
    return PHASE_MAP.get(backend_phase.strip().lower(), "unknown")
