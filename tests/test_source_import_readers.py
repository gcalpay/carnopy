from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from carnopy import SourceImportError, preview_source_import
from carnopy._execution import ExecutionCancelled, ExecutionControl
from carnopy.sources import evidence, preview
from carnopy.sources.config import load_import_config
from carnopy.sources.files import read_source_snapshot, verify_source_snapshot
from carnopy.sources.json_reader import read_json
from carnopy.sources.preview import plan_source_import
from carnopy.sources.xml_reader import read_xml

FIXTURES = Path(__file__).parent / "fixtures" / "thermoml"


def settings(tmp_path: Path, suffix: str = "xml") -> Path:
    path = tmp_path / "import.yaml"
    path.write_text(f"schema_version: 1\ndocument_type: source_import\nformat: thermoml_{suffix}\n")
    return path


@pytest.mark.parametrize(
    "payload",
    [
        b'<!DOCTYPE DataReport [<!ENTITY x "test">]><DataReport>&x;</DataReport>',
        b'<!DOCTYPE DataReport SYSTEM "file:///must-not-open"><DataReport/>',
        b'<!DOCTYPE DataReport [<!ENTITY x SYSTEM "https://must-not-fetch.invalid/">]><DataReport>&x;</DataReport>',
    ],
)
def test_dtds_and_entities_are_always_forbidden(payload: bytes) -> None:
    with pytest.raises(SourceImportError, match="unsafe_xml"):
        read_xml(payload)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"<", "malformed_xml"),
        (b"<DataReport/>", "unsupported_namespace"),
        (b'<DataReport xmlns="urn:not-thermoml"/>', "unsupported_namespace"),
        (f'<Other xmlns="{evidence.THERMOML_NAMESPACE}"/>'.encode(), "unsupported_root"),
    ],
)
def test_xml_rejects_unsupported_roots_and_malformed_syntax(payload: bytes, code: str) -> None:
    with pytest.raises(SourceImportError, match=code):
        read_xml(payload)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b'{"tml_elements":[],"tml_elements":[]}', "duplicate_json_key"),
        (b'{"tml_elements":[],"value":NaN}', "malformed_json"),
        (b'{"tml_elements":[],"value":Infinity}', "malformed_json"),
        (b'{"tml_elements":[],"value":-Infinity}', "malformed_json"),
        (b'{"tml_elements":[],"Note":"\\ud800"}', "malformed_json"),
        (b'{"tml_elements":["Note","Note"],"Note":"x"}', "ambiguous_structure"),
        (b'{"tml_elements":[],"Note":"omitted evidence"}', "ambiguous_structure"),
        (b'{"tml_elements":["Note"]}', "ambiguous_structure"),
        (b'{"tml_elements":["Note"],"Note":{}}', "ambiguous_structure"),
        (b'{"tml_elements":[', "malformed_json"),
        (b"[]", "unsupported_root"),
        (b"{}", "unsupported_root"),
        (b'{"tml_elements":[1],"1":"not a string element name"}', "ambiguous_structure"),
        (b"\xff", "malformed_json"),
    ],
)
def test_json_rejects_ambiguous_or_unsafe_representations(payload: bytes, code: str) -> None:
    with pytest.raises(SourceImportError, match=code):
        read_json(payload)


@pytest.mark.parametrize("suffix", ["xml", "json"])
@pytest.mark.parametrize(
    ("bound", "value", "code"),
    [
        ("MAX_DEPTH", 2, "depth_limit"),
        ("MAX_SCALAR_BYTES", 16, "scalar_limit"),
        ("MAX_PROPERTY_VALUES", 2, "record_limit"),
        ("MAX_NODES", 2, "node_limit"),
    ],
)
def test_parser_limits_apply_before_inventory_and_selection(
    monkeypatch: pytest.MonkeyPatch, suffix: str, bound: str, value: int, code: str
) -> None:
    monkeypatch.setattr(evidence, bound, value)
    reader = read_xml if suffix == "xml" else read_json
    with pytest.raises(SourceImportError, match=code):
        reader((FIXTURES / f"density.{suffix}").read_bytes())


def test_json_resource_scan_distinguishes_keys_from_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evidence, "MAX_PROPERTY_VALUES", 0)
    text = json.dumps({"tml_elements": ["Note"], "Note": '"PropertyValue": [{[{}]}]'}).encode()
    result = read_json(text)
    assert result.value("Note") == '"PropertyValue": [{[{}]}]'


@pytest.mark.parametrize("suffix", ["xml", "json"])
def test_scalar_limit_inclusive_boundary(monkeypatch: pytest.MonkeyPatch, suffix: str) -> None:
    monkeypatch.setattr(evidence, "MAX_SCALAR_BYTES", 32)

    def document(size: int) -> bytes:
        if suffix == "xml":
            return (
                f'<DataReport xmlns="{evidence.THERMOML_NAMESPACE}">'
                f"<Note>{'x' * size}</Note></DataReport>"
            ).encode()
        return json.dumps({"tml_elements": ["Note"], "Note": "x" * size}).encode()

    reader = read_xml if suffix == "xml" else read_json
    assert reader(document(32)).value("Note") == "x" * 32
    with pytest.raises(SourceImportError, match="scalar_limit"):
        reader(document(33))


@pytest.mark.parametrize("suffix", ["xml", "json"])
def test_cancellation_interrupts_parsing(suffix: str) -> None:
    calls = 0

    def cancel() -> None:
        nonlocal calls
        calls += 1
        if calls == 20:
            raise ExecutionCancelled("test cancellation")

    reader = read_xml if suffix == "xml" else read_json
    with pytest.raises(ExecutionCancelled):
        reader((FIXTURES / f"density.{suffix}").read_bytes(), cancel=cancel)
    assert calls == 20


def test_file_byte_limit_and_regular_file_policy(tmp_path: Path) -> None:
    path = tmp_path / "source"
    path.write_bytes(b"abcd")
    assert read_source_snapshot(path, maximum_bytes=4).raw_bytes == b"abcd"
    with pytest.raises(SourceImportError, match="byte_limit"):
        read_source_snapshot(path, maximum_bytes=3)
    with pytest.raises(SourceImportError, match="unsafe_source"):
        read_source_snapshot(tmp_path, maximum_bytes=4)
    link = tmp_path / "link"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SourceImportError, match="unsafe_source"):
        read_source_snapshot(link, maximum_bytes=4)
    directory_link = tmp_path / "linked-directory"
    directory_link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SourceImportError, match="unsafe_source"):
        read_source_snapshot(directory_link / path.name, maximum_bytes=4)


def test_file_mutation_and_replacement_are_detected(tmp_path: Path) -> None:
    path = tmp_path / "source"
    path.write_bytes(b"before")
    snapshot = read_source_snapshot(path, maximum_bytes=32)
    info = path.stat()
    path.write_bytes(b"after!")
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
    with pytest.raises(SourceImportError, match="source_changed"):
        verify_source_snapshot(snapshot, maximum_bytes=32)
    path.write_bytes(b"before")
    snapshot = read_source_snapshot(path, maximum_bytes=32)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"before")
    replacement.replace(path)
    with pytest.raises(SourceImportError, match="source_changed"):
        verify_source_snapshot(snapshot, maximum_bytes=32)


def test_mutation_during_read_cannot_return_mixed_bytes(tmp_path: Path) -> None:
    path = tmp_path / "source"
    path.write_bytes(b"a" * 70000)
    calls = 0

    def mutate() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            path.write_bytes(b"b" * 70000)

    with pytest.raises(SourceImportError, match="source_changed"):
        read_source_snapshot(path, maximum_bytes=80000, cancel=mutate)


def test_preview_rechecks_source_after_scientific_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.xml"
    source.write_bytes((FIXTURES / "density.xml").read_bytes())
    original = preview.build_inventory

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        source.write_bytes(source.read_bytes().replace(b"1000.00", b"1001.00"))
        return result

    monkeypatch.setattr(preview, "build_inventory", mutate)
    with pytest.raises(SourceImportError, match="source_changed"):
        preview_source_import(source, config=settings(tmp_path))


def test_accepted_preview_binds_exact_config_bytes(tmp_path: Path) -> None:
    source = FIXTURES / "density.xml"
    path = settings(tmp_path)
    accepted = preview_source_import(source, config=path)
    path.write_text(path.read_text() + "# scientifically equivalent, different bytes\n")
    current = preview_source_import(source, config=path)
    assert current.request_id == accepted.request_id
    assert current.context_id != accepted.context_id
    with pytest.raises(SourceImportError, match="stale_preview"):
        plan_source_import(source, path, accepted_preview=accepted)


def test_cancelled_preview_creates_no_output(tmp_path: Path) -> None:
    path = settings(tmp_path)
    control = ExecutionControl(lambda: True, lambda *_: None, lambda *_: None)
    with pytest.raises(ExecutionCancelled):
        plan_source_import(FIXTURES / "density.xml", path, control=control)
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "extra",
    [
        "format: thermoml_json\n",
        "selections: &a [*a]\n",
        "selections: [{dataset_index: 0, property_numbers: [1, 1]}]\n",
        "selections: [{dataset_index: true}]\n",
        "source: data.xml\n",
    ],
)
def test_configuration_rejects_ambiguous_yaml(tmp_path: Path, extra: str) -> None:
    path = settings(tmp_path)
    path.write_text(path.read_text() + extra)
    with pytest.raises(SourceImportError, match="invalid_config"):
        load_import_config(path)
