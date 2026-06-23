from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from carnopy.config.io import load_config_file, load_sweep_config_file
from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.sampling.generate import materialize_sampler
from carnopy.templates import (
    FULL_REFERENCE_FILENAME,
    TEMPLATE_FILENAMES,
    TemplateError,
    initialize_config,
    template_text,
)
from carnopy.visualization.requests import PlotFormat, PlotKindV2, PlotScale


def test_packaged_templates_match_repository_examples_and_validate() -> None:
    root = Path(__file__).resolve().parents[1]
    example_names = {
        "property_table": "property_table_example.yaml",
        "saturation_table": "saturation_table_example.yaml",
        "vapor_mass_fraction_table": "vapor_mass_fraction_table_example.yaml",
        "model_sweep": "model_sweep_example.yaml",
    }
    for mode, filename in TEMPLATE_FILENAMES.items():
        packaged = template_text(mode)
        example = (root / "configs" / example_names[mode]).read_text(encoding="utf-8")
        assert packaged == example
        assert filename.endswith(".yaml")
        if mode == "model_sweep":
            assert (
                load_sweep_config_file(root / "configs" / example_names[mode]).model.document_type
                == "model_sweep"
            )
        else:
            assert load_config_file(root / "configs" / example_names[mode]).model.mode == mode

    property_model = load_config_file(root / "configs" / "property_table_example.yaml").model
    pressure = materialize_sampler(property_model.grid["pressure"])
    assert pressure == [1.0, 5.75, 10.5, 15.25, 20.0]


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


@pytest.mark.parametrize("mode", list(TEMPLATE_FILENAMES))
def test_full_templates_are_valid_and_append_one_authoritative_reference(
    tmp_path: Path,
    mode: str,
) -> None:
    concise = template_text(mode)
    full = template_text(mode, full=True)
    reference = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "carnopy"
        / "templates"
        / FULL_REFERENCE_FILENAME
    ).read_text(encoding="utf-8")
    assert full == concise.rstrip() + "\n" + reference
    assert "Carnopy configuration reference" in full
    assert "kind: explicit" in full
    assert "kind: linspace" in full
    assert "kind: stepspace" in full
    assert "kind: geomspace" in full
    assert "kind: logspace" in full
    output = tmp_path / f"{mode}.yaml"
    initialize_config(mode, output, full=True)
    assert output.read_text(encoding="utf-8") == full
    if mode == "model_sweep":
        assert load_sweep_config_file(output).model.document_type == "model_sweep"
    else:
        assert load_config_file(output).model.mode == mode


def test_full_reference_tracks_public_registries_and_enums() -> None:
    reference = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "carnopy"
        / "templates"
        / FULL_REFERENCE_FILENAME
    ).read_text(encoding="utf-8")
    for property_name in PROPERTY_REGISTRY:
        assert f"#   {property_name}" in reference
    for plot_kind in get_args(PlotKindV2):
        assert str(plot_kind) in reference
    for plot_format in get_args(PlotFormat):
        assert str(plot_format) in reference
    for plot_scale in get_args(PlotScale):
        assert str(plot_scale) in reference
