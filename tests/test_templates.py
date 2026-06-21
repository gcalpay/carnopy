from __future__ import annotations

from pathlib import Path

import pytest

from carnopy.config.io import load_config_file
from carnopy.templates import (
    TEMPLATE_FILENAMES,
    TemplateError,
    initialize_config,
    template_text,
)


def test_packaged_templates_match_repository_examples_and_validate() -> None:
    root = Path(__file__).resolve().parents[1]
    example_names = {
        "property_table": "property_table_example.yaml",
        "saturation_table": "saturation_table_example.yaml",
        "vapor_mass_fraction_table": "vapor_mass_fraction_table_example.yaml",
    }
    for mode, filename in TEMPLATE_FILENAMES.items():
        packaged = template_text(mode)
        example = (root / "configs" / example_names[mode]).read_text(encoding="utf-8")
        assert packaged == example
        assert filename.endswith(".yaml")
        assert load_config_file(root / "configs" / example_names[mode]).model.mode == mode


def test_interactive_initialization_can_confirm_parent_creation(tmp_path: Path) -> None:
    output = tmp_path / "created" / "config.yml"
    requested_parents: list[Path] = []

    def confirm(parent: Path) -> bool:
        requested_parents.append(parent)
        return True

    created = initialize_config(
        "property_table",
        output,
        interactive=True,
        confirm_create=confirm,
    )
    assert created == output.resolve()
    assert requested_parents == [output.parent]


def test_interactive_initialization_default_refusal_leaves_no_file(tmp_path: Path) -> None:
    output = tmp_path / "refused" / "config.yaml"
    with pytest.raises(TemplateError, match="parent directory does not exist"):
        initialize_config(
            "property_table",
            output,
            interactive=True,
            confirm_create=lambda _parent: False,
        )
    assert not output.exists()
