from __future__ import annotations

from carnopy.config.normalize import canonical_json_bytes
from carnopy.provenance import build_identity


def test_identity_separates_raw_source_from_normalized_spec() -> None:
    normalized = canonical_json_bytes({"pressure": [100_000.0]})
    first = build_identity(
        raw_config=b"pressure: 1 bar\n",
        normalized_config=normalized,
        backend_version="7.2.0",
    )
    second = build_identity(
        raw_config=b"pressure: 100 kPa\n",
        normalized_config=normalized,
        backend_version="7.2.0",
    )
    assert first.raw_config_sha256 != second.raw_config_sha256
    assert first.normalized_config_sha256 == second.normalized_config_sha256
    assert first.spec_id == second.spec_id
    assert first.generation_context_id == second.generation_context_id


def test_canonical_json_normalizes_negative_zero() -> None:
    assert canonical_json_bytes({"value": -0.0}) == b'{"value":0.0}\n'
