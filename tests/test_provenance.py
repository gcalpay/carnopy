from __future__ import annotations

import hashlib
from pathlib import Path

from carnopy.config.normalize import canonical_json_bytes
from carnopy.provenance import (
    build_identity,
    build_output_request_id,
    sha256_bytes,
    sha256_file,
)


def test_identity_separates_raw_source_from_normalized_spec() -> None:
    normalized = canonical_json_bytes({"pressure": [100_000.0]})
    first = build_identity(
        raw_config=b"pressure: 1 bar\n",
        normalized_config=normalized,
        backend_version="7.2.0",
        backend_name="coolprop",
        backend_model="heos",
    )
    second = build_identity(
        raw_config=b"pressure: 100 kPa\n",
        normalized_config=normalized,
        backend_version="7.2.0",
        backend_name="coolprop",
        backend_model="heos",
    )
    assert first.raw_config_sha256 != second.raw_config_sha256
    assert first.normalized_config_sha256 == second.normalized_config_sha256
    assert first.spec_id == second.spec_id
    assert first.generation_context_id == second.generation_context_id


def test_canonical_json_normalizes_negative_zero() -> None:
    assert canonical_json_bytes({"value": -0.0}) == b'{"value":0.0}\n'


def test_output_request_identity_is_canonical_and_changes_context() -> None:
    normalized = canonical_json_bytes({"pressure": [100_000.0]})
    both = build_output_request_id(("csv", "parquet"))
    csv = build_output_request_id(("csv",))
    assert both.startswith("out-")
    assert both != csv
    both_identity = build_identity(
        raw_config=b"same",
        normalized_config=normalized,
        backend_version="7.2.0",
        backend_name="coolprop",
        backend_model="heos",
        output_request_id=both,
    )
    csv_identity = build_identity(
        raw_config=b"same",
        normalized_config=normalized,
        backend_version="7.2.0",
        backend_name="coolprop",
        backend_model="heos",
        output_request_id=csv,
    )
    assert both_identity.spec_id == csv_identity.spec_id
    assert both_identity.generation_context_id != csv_identity.generation_context_id


def test_backend_model_changes_generation_context() -> None:
    normalized = canonical_json_bytes({"same": True})
    heos = build_identity(
        raw_config=b"same",
        normalized_config=normalized,
        backend_version="7.2.0",
        backend_name="coolprop",
        backend_model="heos",
    )
    pr = build_identity(
        raw_config=b"same",
        normalized_config=normalized,
        backend_version="7.2.0",
        backend_name="coolprop",
        backend_model="pr",
    )
    assert heos.spec_id == pr.spec_id
    assert heos.generation_context_id != pr.generation_context_id


def test_sha256_file_matches_byte_hash_across_multiple_chunks(tmp_path: Path) -> None:
    content = (b"carnopy-hash-test" * 80_000) + b"tail"
    path = tmp_path / "multi-chunk.bin"
    path.write_bytes(content)
    assert len(content) > 1024 * 1024
    assert sha256_file(path) == sha256_bytes(content) == hashlib.sha256(content).hexdigest()
