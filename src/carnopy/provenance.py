from __future__ import annotations

import hashlib
import platform
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path

from carnopy._version import __version__

CONFIG_SCHEMA_VERSION = 1
DATASET_SCHEMA_VERSION = 1
METADATA_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
REFERENCE_STATE_POLICY = "coolprop_DEF"


@dataclass(frozen=True)
class Identity:
    raw_config_sha256: str
    normalized_config_sha256: str
    spec_id: str
    generation_context_id: str


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file without loading the complete artifact into memory."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_identity(
    *,
    raw_config: bytes,
    normalized_config: bytes,
    backend_version: str,
) -> Identity:
    from carnopy.config.normalize import canonical_json_bytes

    raw_hash = sha256_bytes(raw_config)
    normalized_hash = sha256_bytes(normalized_config)
    context = {
        "normalized_config_sha256": normalized_hash,
        "carnopy_version": __version__,
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "metadata_schema_version": METADATA_SCHEMA_VERSION,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "backend": "coolprop",
        "backend_version": backend_version,
        "reference_state_policy": REFERENCE_STATE_POLICY,
        "runtime_versions": runtime_versions(),
    }
    context_hash = sha256_bytes(canonical_json_bytes(context))
    return Identity(
        raw_config_sha256=raw_hash,
        normalized_config_sha256=normalized_hash,
        spec_id=f"spec-{normalized_hash}",
        generation_context_id=f"ctx-{context_hash}",
    )


def runtime_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": metadata.version("numpy"),
        "pandas": metadata.version("pandas"),
        "pyarrow": metadata.version("pyarrow"),
        "coolprop": metadata.version("CoolProp"),
    }


def identity_dict(identity: Identity) -> dict[str, str]:
    return asdict(identity)
