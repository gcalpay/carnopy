from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

import carnopy.app.config_document as config_documents
from carnopy.app.config_document import (
    ConfigDocumentError,
    ConfigurationDocument,
    DatasetConfigDocument,
    ExternalModificationError,
    document_from_worker_payload,
    new_document,
    replace_config_atomic,
    serialize_configuration,
    serialize_dataset_config,
    serialize_preparation_config,
    serialize_sweep_config,
    source_matches,
    write_new_config,
)
from carnopy.config.io import load_config_bytes, load_sweep_config_bytes
from carnopy.preparation.models import load_preparation_config_bytes
from carnopy.templates import template_text


@pytest.mark.parametrize(
    "mode",
    ["property_table", "saturation_table", "vapor_mass_fraction_table"],
)
def test_concise_templates_serialize_deterministically_and_remain_valid(mode: str) -> None:
    payload = yaml.safe_load(template_text(mode))

    first = serialize_dataset_config(payload)
    second = serialize_dataset_config(payload)
    loaded = load_config_bytes(first, source_name=f"{mode}.yaml")

    assert first == second
    assert loaded.model.mode == mode
    assert loaded.model.outputs.dataset_formats == ("csv", "parquet")
    text = first.decode()
    assert text.index("schema_version:") < text.index("backend:") < text.index("mode:")
    assert text.index("grid:") < text.index("properties:") < text.index("outputs:")


@pytest.mark.parametrize(
    ("sampler", "expected_keys"),
    [
        ({"kind": "explicit", "values": [2.0, 1.0], "unit": "bar"}, ["kind", "values", "unit"]),
        (
            {"kind": "linspace", "start": 1.0, "stop": 2.0, "num": 3, "unit": "bar"},
            ["kind", "start", "stop", "num", "unit"],
        ),
        (
            {"kind": "stepspace", "start": 1.0, "stop": 2.0, "step": 0.5, "unit": "bar"},
            ["kind", "start", "stop", "step", "unit"],
        ),
        (
            {"kind": "geomspace", "start": 1.0, "stop": 2.0, "num": 3, "unit": "bar"},
            ["kind", "start", "stop", "num", "unit"],
        ),
        (
            {
                "kind": "logspace",
                "start_exp": 0.0,
                "stop_exp": 2.0,
                "num": 3,
                "base": 10.0,
                "unit": "bar",
            },
            ["kind", "start_exp", "stop_exp", "num", "base", "unit"],
        ),
    ],
)
def test_sampler_serialization_uses_public_field_order(
    sampler: dict[str, object],
    expected_keys: list[str],
) -> None:
    payload = yaml.safe_load(template_text("property_table"))
    payload["grid"]["pressure"] = sampler

    serialized = yaml.safe_load(serialize_dataset_config(payload))

    assert list(serialized["grid"]["pressure"]) == expected_keys
    if sampler["kind"] == "explicit":
        assert serialized["grid"]["pressure"]["values"] == [2.0, 1.0]


def test_visualization_serialization_preserves_public_fields_and_series_order() -> None:
    payload = yaml.safe_load(template_text("property_table"))
    payload["visualization"] = {
        "format": "png",
        "fluids": ["Propane"],
        "filters": {"phase": "gas"},
        "display_units": {"pressure": "bar"},
        "plots": [
            {
                "name": "density-curves",
                "kind": "property_curves",
                "property": "mass_density",
                "x": "temperature",
                "filters": {"phase": "gas"},
                "series": {"pressure": [500000.0, 100000.0]},
                "display_units": {"temperature": "degC", "pressure": "bar"},
                "fluids": ["Propane"],
                "value_scale": "log",
                "color_scale": "linear",
                "x_scale": "linear",
                "y_scale": "linear",
                "format": "svg",
            },
            {
                "name": "enthalpy-entropy",
                "kind": "xy",
                "x": "specific_enthalpy",
                "y": "specific_entropy",
                "group_by": "pressure",
                "x_scale": "linear",
                "y_scale": "log",
            },
        ],
    }

    serialized = serialize_dataset_config(payload)
    round_trip = yaml.safe_load(serialized)
    loaded = load_config_bytes(serialized, source_name="visualization.yaml")

    assert round_trip["visualization"].get("format") is None
    first_plot = round_trip["visualization"]["plots"][0]
    assert list(first_plot) == [
        "name",
        "kind",
        "property",
        "x",
        "filters",
        "series",
        "display_units",
        "fluids",
        "value_scale",
        "format",
    ]
    assert first_plot["series"]["pressure"] == [500000.0, 100000.0]
    assert loaded.model.visualization is not None
    assert [plot.name for plot in loaded.model.visualization.plots] == [
        "density-curves",
        "enthalpy-entropy",
    ]


def test_dataset_output_formats_use_canonical_order() -> None:
    payload = yaml.safe_load(template_text("property_table"))
    payload["outputs"]["dataset_formats"] = ["parquet", "csv"]

    serialized = yaml.safe_load(serialize_dataset_config(payload))

    assert serialized["outputs"]["dataset_formats"] == ["csv", "parquet"]


@pytest.mark.parametrize(
    ("template", "serializer", "schema_version"),
    [
        ("property_table", serialize_dataset_config, 2),
        ("model_sweep", serialize_sweep_config, 2),
        ("preparation", serialize_preparation_config, 1),
    ],
)
def test_configuration_documents_serialize_deterministically_by_discriminator(
    template: str,
    serializer: Callable[[dict[str, Any]], bytes],
    schema_version: int,
) -> None:
    payload = yaml.safe_load(template_text(template))

    first = serializer(payload)
    second = serialize_configuration(payload)

    assert first == second
    assert yaml.safe_load(first)["document_type"] == payload["document_type"]
    assert yaml.safe_load(first)["schema_version"] == schema_version
    document = new_document(payload)
    assert isinstance(document, ConfigurationDocument)
    assert isinstance(document, DatasetConfigDocument)
    assert document.document_type == payload["document_type"]
    assert document.yaml_bytes == first


def test_sweep_serialization_preserves_complete_current_schema() -> None:
    payload = yaml.safe_load(template_text("model_sweep"))
    payload["grid"] = {
        "pressure": payload["grid"]["pressure"],
        "temperature": payload["grid"]["temperature"],
    }
    payload["outputs"]["dataset_formats"] = ["parquet", "csv"]
    payload["comparison_plots"] = {
        "format": "svg",
        "plots": [
            {
                "name": "density-comparison",
                "kind": "property_comparison",
                "fluid": "Propane",
                "property": "mass_density",
                "x": "temperature",
                "group_by": "pressure",
                "filters": {"phase": "gas", "pressure": 100000.0},
                "models": ["srk", "heos", "pr"],
                "value_scale": "log",
                "format": "pdf",
            },
            {
                "name": "density-delta",
                "kind": "property_delta",
                "fluid": "Propane",
                "property": "mass_density",
                "x": "pressure",
                "models": ["pr", "srk"],
                "delta_metric": "signed_absolute_difference",
            },
        ],
    }

    first = serialize_sweep_config(payload)
    second = serialize_sweep_config(payload)
    expected = load_sweep_config_bytes(
        yaml.safe_dump(payload).encode("utf-8"),
        source_name="rich-sweep-input.yaml",
    ).model
    loaded = load_sweep_config_bytes(first, source_name="rich-sweep-output.yaml").model
    serialized = yaml.safe_load(first)

    assert first == second
    assert loaded == expected
    assert list(serialized) == [
        "schema_version",
        "document_type",
        "backend",
        "mode",
        "fluids",
        "grid",
        "properties",
        "outputs",
        "comparison_plots",
    ]
    assert list(serialized["grid"]) == ["temperature", "pressure"]
    assert serialized["outputs"]["dataset_formats"] == ["csv", "parquet"]
    assert list(serialized["comparison_plots"]["plots"][0]) == [
        "name",
        "kind",
        "fluid",
        "property",
        "x",
        "group_by",
        "filters",
        "models",
        "delta_metric",
        "value_scale",
        "format",
    ]


def test_preparation_serialization_preserves_complete_current_schema() -> None:
    payload = {
        "schema_version": 1,
        "document_type": "preparation",
        "source_policy": {"allow_partial_sweep": True},
        "features": {
            "numeric": ["temperature", "pressure"],
            "derived": ["specific_volume"],
        },
        "categorical_features": [
            {
                "field": "phase",
                "encoding": "one_hot",
                "categories": ["gas", "liquid"],
            },
            {"field": "fluid", "encoding": "one_hot", "categories": "observed"},
        ],
        "targets": ["mass_density"],
        "auxiliary": ["backend_model", "run_id"],
        "scenarios": [
            {
                "name": "stratified",
                "kind": "stratified_hash",
                "seed": 9,
                "partitions": {"test": 0.2, "train": 0.7, "validation": 0.1},
                "strata": {
                    "numeric_bins": {"temperature": [280.0, 320.0]},
                    "categorical": ["phase"],
                },
                "transformations": [
                    {"field": "pressure", "methods": ["log10", "standard"]},
                    {"field": "temperature", "methods": ["minmax"]},
                ],
            },
            {
                "name": "coordinate-block",
                "kind": "coordinate_block",
                "holdouts": {
                    "test": {
                        "pressure": {"min": 100000.0, "max": 200000.0},
                        "temperature": {"min": 280.0, "max": 300.0},
                    }
                },
                "remainder": "train",
                "transformations": [{"field": "pressure", "methods": ["robust"]}],
            },
        ],
        "quality": {
            "matrix_diagnostics": {
                "correlation_threshold": 0.99,
                "near_constant_relative_spread": 1e-10,
            },
            "baseline_diagnostics": {
                "models": ["hist_gradient_boosting", "dummy_mean", "ridge"],
                "random_seed": 7,
                "ridge_alpha": 0.5,
                "histogram_max_iterations": 50,
            },
        },
        "outputs": {
            "formats": ["parquet"],
            "parquet": True,
            "arrays": {
                "formats": ["safetensors", "npy", "npz"],
                "dtype": "float64",
                "include_auxiliary": True,
            },
        },
    }

    first = serialize_preparation_config(payload)
    second = serialize_preparation_config(payload)
    expected = load_preparation_config_bytes(
        yaml.safe_dump(payload).encode("utf-8"),
        source_name="rich-preparation-input.yaml",
    ).model
    loaded = load_preparation_config_bytes(
        first,
        source_name="rich-preparation-output.yaml",
    ).model
    serialized = yaml.safe_load(first)

    assert first == second
    assert loaded == expected
    assert list(serialized) == [
        "schema_version",
        "document_type",
        "source_policy",
        "features",
        "categorical_features",
        "targets",
        "auxiliary",
        "scenarios",
        "quality",
        "outputs",
    ]
    assert [item["name"] for item in serialized["scenarios"]] == [
        "stratified",
        "coordinate-block",
    ]
    assert serialized["scenarios"][0]["transformations"] == [
        {"field": "pressure", "methods": ["log10", "standard"]},
        {"field": "temperature", "methods": ["minmax"]},
    ]
    assert serialized["outputs"]["arrays"]["formats"] == [
        "npy",
        "npz",
        "safetensors",
    ]


@pytest.mark.parametrize("document_type", [None, "sweep", "PREPARATION"])
def test_generic_document_rejects_missing_or_unknown_discriminator(
    document_type: str | None,
) -> None:
    payload: dict[str, object] = {"schema_version": 2}
    if document_type is not None:
        payload["document_type"] = document_type

    with pytest.raises(ConfigDocumentError, match="document_type"):
        new_document(payload)


def test_document_tracks_unsaved_and_dirty_state_without_exposing_mutable_payload() -> None:
    payload = yaml.safe_load(template_text("property_table"))
    document = new_document(payload)

    assert document.needs_save
    assert not document.dirty
    detached = document.payload
    detached["fluids"].append("Cyclopentane")
    assert document.payload["fluids"] == payload["fluids"]

    document.set_payload(detached)
    assert document.dirty
    assert document.payload["fluids"] == ["Propane", "Isobutane", "Cyclopentane"]


def test_worker_document_identity_and_workspace_ownership(tmp_path: Path) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    source = configs / "dataset.yaml"
    content = serialize_dataset_config(yaml.safe_load(template_text("property_table")))
    source.write_bytes(content)
    worker_payload = {
        "config": yaml.safe_load(content),
        "source_name": str(source),
        "source_sha256": hashlib.sha256(content).hexdigest(),
    }

    document = document_from_worker_payload(worker_payload, configs_root=configs)

    assert document.source_path == source.resolve()
    assert document.workspace_owned
    assert document.imported
    assert not document.dirty
    assert source_matches(source, document.source_sha256 or "")


def test_worker_document_rejects_an_inconsistent_top_level_discriminator(
    tmp_path: Path,
) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    source = configs / "sweep.yaml"
    content = serialize_sweep_config(yaml.safe_load(template_text("model_sweep")))
    source.write_bytes(content)

    with pytest.raises(ConfigDocumentError, match="document type is inconsistent"):
        document_from_worker_payload(
            {
                "document_type": "preparation",
                "config": yaml.safe_load(content),
                "source_name": str(source),
                "source_sha256": hashlib.sha256(content).hexdigest(),
            },
            configs_root=configs,
        )


def test_new_and_atomic_save_refuse_overwrite_and_external_modification(tmp_path: Path) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    destination = configs / "dataset.yaml"
    first = b"schema_version: 2\n"
    second = b"schema_version: 2\ndocument_type: dataset\n"

    assert write_new_config(destination, first, configs_root=configs) == destination.resolve()
    original_mode = destination.stat().st_mode
    with pytest.raises(ConfigDocumentError, match="overwrite"):
        write_new_config(destination, second, configs_root=configs)

    replace_config_atomic(
        destination,
        second,
        expected_sha256=hashlib.sha256(first).hexdigest(),
        configs_root=configs,
    )
    assert destination.read_bytes() == second
    assert destination.stat().st_mode == original_mode

    destination.write_bytes(b"external change\n")
    with pytest.raises(ExternalModificationError, match="outside Carnopy"):
        replace_config_atomic(
            destination,
            first,
            expected_sha256=hashlib.sha256(second).hexdigest(),
            configs_root=configs,
        )
    assert destination.read_bytes() == b"external change\n"


def test_atomic_save_rechecks_source_before_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    destination = configs / "dataset.yaml"
    original = b"original\n"
    destination.write_bytes(original)
    monkeypatch.setattr(config_documents, "source_matches", lambda *_args: False)

    with pytest.raises(ExternalModificationError, match="outside Carnopy"):
        replace_config_atomic(
            destination,
            b"replacement\n",
            expected_sha256=hashlib.sha256(original).hexdigest(),
            configs_root=configs,
        )

    assert destination.read_bytes() == original
    assert list(configs.glob(".*.tmp")) == []


def test_save_rejects_invalid_or_escaping_destinations(tmp_path: Path) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()

    with pytest.raises(ConfigDocumentError, match="under"):
        write_new_config(tmp_path / "outside.yaml", b"value\n", configs_root=configs)
    with pytest.raises(ConfigDocumentError, match="end in"):
        write_new_config(configs / "dataset.txt", b"value\n", configs_root=configs)

    if hasattr(os, "symlink"):
        outside = tmp_path / "outside"
        outside.mkdir()
        link = configs / "linked"
        link.symlink_to(outside, target_is_directory=True)
        with pytest.raises(ConfigDocumentError, match="under"):
            write_new_config(link / "dataset.yaml", b"value\n", configs_root=configs)


def test_mark_saved_updates_document_identity(tmp_path: Path) -> None:
    payload = yaml.safe_load(template_text("property_table"))
    document = DatasetConfigDocument(payload, imported=True)
    destination = tmp_path / "dataset.yaml"
    content = document.yaml_bytes

    document.mark_saved(destination, content)

    assert document.source_path == destination.resolve()
    assert document.source_sha256 == hashlib.sha256(content).hexdigest()
    assert document.workspace_owned
    assert not document.imported
    assert not document.dirty


@pytest.mark.parametrize(
    ("template", "document_type"),
    [
        ("property_table", "dataset"),
        ("model_sweep", "model_sweep"),
        ("preparation", "preparation"),
    ],
)
def test_execution_snapshot_requires_exact_saved_workspace_bytes(
    tmp_path: Path,
    template: str,
    document_type: str,
) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    document = new_document(yaml.safe_load(template_text(template)))
    destination = configs / f"{document_type}.yaml"
    content = document.yaml_bytes
    destination.write_bytes(content)
    document.mark_saved(destination, content)

    snapshot = document.execution_snapshot(configs_root=configs)

    assert snapshot.path == destination.resolve()
    assert snapshot.yaml_bytes == content
    assert snapshot.sha256 == hashlib.sha256(content).hexdigest()
    assert snapshot.document_type == document_type

    destination.write_bytes(content + b"# changed\n")
    with pytest.raises(ExternalModificationError, match="outside Carnopy"):
        document.execution_snapshot(configs_root=configs)
