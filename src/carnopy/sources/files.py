from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from carnopy.sources.errors import SourceImportError

Checkpoint = Callable[[], None]


def checkpoint(callback: Checkpoint | None) -> None:
    if callback is not None:
        callback()


@dataclass(frozen=True)
class SourceDescriptor:
    path: Path
    sha256: str
    size: int
    device: int
    inode: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class SourceSnapshot:
    descriptor: SourceDescriptor
    raw_bytes: bytes


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _regular_path(path: Path) -> os.stat_result:
    # Check the original spelling before resolving it; resolving first hides links.
    for part in (*reversed(path.parents), path):
        if stat.S_ISLNK(part.lstat().st_mode):
            raise SourceImportError("unsafe_source", "symbolic links are not accepted")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise SourceImportError("unsafe_source", "source must be a regular file")
    return info


def read_source_snapshot(
    path: str | Path,
    *,
    maximum_bytes: int,
    cancel: Checkpoint | None = None,
) -> SourceSnapshot:
    return _read_source(path, maximum_bytes=maximum_bytes, cancel=cancel, retain_bytes=True)


def read_source_descriptor(
    path: str | Path,
    *,
    maximum_bytes: int,
    cancel: Checkpoint | None = None,
) -> SourceDescriptor:
    """Hash an artifact with the same stable-read rules, without buffering it."""
    return _read_source(
        path, maximum_bytes=maximum_bytes, cancel=cancel, retain_bytes=False
    ).descriptor


def _read_source(
    path: str | Path,
    *,
    maximum_bytes: int,
    cancel: Checkpoint | None,
    retain_bytes: bool,
) -> SourceSnapshot:
    """Bounded descriptor-backed read, following the existing artifact-read policy.

    The preparation reader imports pandas and the scene reader owns desktop errors;
    neither can serve this lightweight source path. Keep the same stat/hash checks
    here, with bounded cancellable reads and no-follow/nonblocking open flags.
    """
    source = Path(path).absolute()
    checkpoint(cancel)
    try:
        before = _regular_path(source)
        if before.st_size > maximum_bytes:
            raise SourceImportError("byte_limit", f"source exceeds {maximum_bytes} bytes")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = os.open(source, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
                raise SourceImportError("source_changed", "source changed while opening")
            blocks: list[bytes] = []
            digest = hashlib.sha256()
            size = 0
            while True:
                checkpoint(cancel)
                block = stream.read(min(64 * 1024, maximum_bytes + 1 - size))
                if not block:
                    break
                size += len(block)
                if size > maximum_bytes:
                    raise SourceImportError("byte_limit", f"source exceeds {maximum_bytes} bytes")
                digest.update(block)
                if retain_bytes:
                    blocks.append(block)
            after = os.fstat(stream.fileno())
        current = _regular_path(source)
        if (
            _identity(before) != _identity(after)
            or _identity(before) != _identity(current)
            or size != current.st_size
        ):
            raise SourceImportError("source_changed", "source changed while reading")
        content = b"".join(blocks)
        checkpoint(cancel)
        return SourceSnapshot(
            SourceDescriptor(
                source,
                digest.hexdigest(),
                size,
                before.st_dev,
                before.st_ino,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ),
            content,
        )
    except OSError as exc:
        raise SourceImportError("source_unavailable", f"could not read source: {exc}") from exc


def verify_source_snapshot(
    snapshot: SourceSnapshot,
    *,
    maximum_bytes: int,
    cancel: Checkpoint | None = None,
) -> None:
    current = read_source_snapshot(
        snapshot.descriptor.path,
        maximum_bytes=maximum_bytes,
        cancel=cancel,
    )
    if current.descriptor != snapshot.descriptor:
        raise SourceImportError("source_changed", "source changed since the accepted read")
