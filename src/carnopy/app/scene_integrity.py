from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from carnopy.app.scene_contracts import SceneContractError

SCENE_LEASE_NAME: Final = "lease.json"
SCENE_MANIFEST_NAME: Final = "scene.json"
SCENE_BINARY_NAME: Final = "scene.bin"


class SceneBundleError(SceneContractError):
    """A private scene bundle or lease failed exact verification."""


def canonical_scene_json_bytes(value: Mapping[str, object]) -> bytes:
    """Return the only accepted UTF-8 JSON representation for scene metadata."""

    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene metadata is not finite canonical JSON",
        ) from exc
    return (rendered + "\n").encode("utf-8")


def parse_canonical_scene_json_object(data: bytes, *, label: str) -> dict[str, object]:
    """Parse finite UTF-8 JSON while rejecting duplicate object keys."""

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite JSON constant {value}")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            data.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            f"{label} is not valid finite UTF-8 JSON",
        ) from exc
    if not isinstance(parsed, dict):
        raise SceneBundleError(
            "scene_integrity_error",
            f"{label} must contain one JSON object",
        )
    return parsed


def read_scene_regular_file(path: Path, *, maximum_bytes: int, label: str) -> bytes:
    """Read one bounded regular file while detecting replacement or mutation."""

    try:
        initial = path.lstat()
    except OSError as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            f"{label} is unavailable: {path}",
        ) from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise SceneBundleError(
            "scene_integrity_error",
            f"{label} must be a regular file",
        )
    if initial.st_size > maximum_bytes:
        raise SceneBundleError(
            "scene_integrity_error",
            f"{label} exceeds its maximum accepted size",
        )
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            f"{label} cannot be opened safely",
        ) from exc
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (
                opened.st_dev,
                opened.st_ino,
            ) != (initial.st_dev, initial.st_ino):
                raise SceneBundleError(
                    "scene_integrity_error",
                    f"{label} changed while it was opened",
                )
            data = stream.read(maximum_bytes + 1)
            final = os.fstat(stream.fileno())
    except SceneBundleError:
        raise
    except OSError as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            f"{label} cannot be read safely",
        ) from exc
    if len(data) > maximum_bytes:
        raise SceneBundleError(
            "scene_integrity_error",
            f"{label} exceeds its maximum accepted size",
        )
    if (
        (final.st_dev, final.st_ino) != (initial.st_dev, initial.st_ino)
        or final.st_size != initial.st_size
        or final.st_mtime_ns != initial.st_mtime_ns
        or len(data) != final.st_size
    ):
        raise SceneBundleError(
            "scene_integrity_error",
            f"{label} changed while it was read",
        )
    return data


def write_scene_exclusive_regular_file(path: Path, data: bytes, *, label: str) -> None:
    """Durably create one private regular file without replacing any path."""

    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise SceneBundleError(
            "scene_write_failed",
            f"{label} could not be created exclusively: {path}",
        ) from exc
    try:
        opened = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise SceneBundleError(
            "scene_write_failed",
            f"{label} could not be inspected after creation: {path}",
        ) from exc
    try:
        if not stat.S_ISREG(opened.st_mode):
            raise OSError(f"{label} destination is not a regular file")
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            written = stream.write(data)
            if written != len(data):
                raise OSError(f"{label} write was incomplete")
            stream.flush()
            os.fsync(stream.fileno())
            final = os.fstat(stream.fileno())
        current = path.lstat()
        if (
            not stat.S_ISREG(final.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (final.st_dev, final.st_ino) != (opened.st_dev, opened.st_ino)
            or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
            or final.st_size != len(data)
            or current.st_size != len(data)
            or current.st_nlink != 1
        ):
            raise OSError(f"{label} changed while it was written")
    except Exception as exc:
        _unlink_exclusively_created_file(path, opened)
        if isinstance(exc, SceneBundleError):
            raise
        raise SceneBundleError(
            "scene_write_failed",
            f"{label} could not be written safely: {path}",
        ) from exc


def _unlink_exclusively_created_file(path: Path, opened: os.stat_result) -> None:
    try:
        current = path.lstat()
    except OSError:
        return
    if stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == (
        opened.st_dev,
        opened.st_ino,
    ):
        try:
            path.unlink()
        except OSError:
            return
