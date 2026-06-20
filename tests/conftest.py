from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def property_config_path() -> Path:
    return FIXTURES / "property_table.yaml"


@pytest.fixture
def saturation_config_path() -> Path:
    return FIXTURES / "saturation_table.yaml"


@pytest.fixture
def vapor_config_path() -> Path:
    return FIXTURES / "vapor_mass_fraction_table.yaml"
