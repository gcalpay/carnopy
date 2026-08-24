from __future__ import annotations

import os
import re
import stat
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError
from PySide6.QtCore import QLockFile

from carnopy.app.scene_integrity import (
    SCENE_BINARY_NAME,
    SCENE_LEASE_NAME,
    SCENE_MANIFEST_NAME,
    SceneBundleError,
    canonical_scene_json_bytes,
    parse_canonical_scene_json_object,
    read_scene_regular_file,
)
from carnopy.app.workspace import Workspace, open_workspace

SCENE_LEASE_SCHEMA_VERSION: Final[Literal[1]] = 1
SCENE_LEASE_ROOT_NAME: Final = "scene-leases"
SCENE_SESSION_LOCK_ROOT_NAME: Final = "scene-session-locks"

_LEASE_RECORD_MAX_BYTES = 4_096
_ALLOWED_LEASE_FILES = frozenset({SCENE_LEASE_NAME, SCENE_MANIFEST_NAME, SCENE_BINARY_NAME})
_UUID_HEX_PATTERN = re.compile(r"^[0-9a-f]{32}$")

NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]
UuidHex = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{32}$")]

SceneCleanupAction = Literal["removed", "preserved"]


class SceneLeaseRecord(BaseModel):
    """Parent-written identity record for one private scene lease."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_lease_schema_version: Literal[1] = SCENE_LEASE_SCHEMA_VERSION
    lease_id: UuidHex
    session_id: UuidHex
    device: NonNegativeInt
    inode: PositiveInt


class SceneLeasePayload(BaseModel):
    """Minimal parent-to-worker destination identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lease_id: UuidHex
    session_id: UuidHex
    device: NonNegativeInt
    inode: PositiveInt


@dataclass(frozen=True)
class SceneLease:
    """Verified location and identity for one parent-created lease."""

    workspace_root: Path
    lease_id: str
    session_id: str
    path: Path
    device: int
    inode: int

    def worker_payload(self) -> dict[str, int | str]:
        return {
            "lease_id": self.lease_id,
            "session_id": self.session_id,
            "device": self.device,
            "inode": self.inode,
        }


class SceneSession:
    """Workspace-session ownership held by one ``QLockFile`` instance."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        session_id: str,
        lock_path: Path,
        lock: QLockFile,
    ) -> None:
        self.workspace_root = workspace_root
        self.session_id = session_id
        self.lock_path = lock_path
        self._lock = lock
        self._closed = False

    @property
    def is_active(self) -> bool:
        return not self._closed and self._lock.isLocked()

    def close(self) -> None:
        if self._closed:
            return
        self._lock.unlock()
        self._closed = True

    def __enter__(self) -> SceneSession:
        if not self.is_active:
            raise SceneBundleError(
                "scene_cleanup_failed",
                "scene session lock is not active",
            )
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()


@dataclass(frozen=True)
class SceneCleanupEntry:
    path: Path
    action: SceneCleanupAction
    reason: str


@dataclass(frozen=True)
class SceneCleanupReport:
    entries: tuple[SceneCleanupEntry, ...]

    @property
    def removed(self) -> tuple[Path, ...]:
        return tuple(entry.path for entry in self.entries if entry.action == "removed")

    @property
    def preserved(self) -> tuple[Path, ...]:
        return tuple(entry.path for entry in self.entries if entry.action == "preserved")


def acquire_scene_session(
    workspace_path: Path,
    *,
    session_id: str | None = None,
) -> SceneSession:
    """Acquire one liveness lock for a workspace application session."""

    workspace = open_workspace(workspace_path)
    selected_id = uuid4().hex if session_id is None else session_id
    if _UUID_HEX_PATTERN.fullmatch(selected_id) is None:
        raise SceneBundleError(
            "scene_cleanup_failed",
            "scene session ID must be 32 lowercase hexadecimal characters",
        )
    root = _session_lock_root(workspace, create=True)
    lock_path = root / f"{selected_id}.lock"
    _verify_lock_path_type(lock_path)
    lock = QLockFile(str(lock_path))
    # Disable age-only takeover of a slow but live process. Qt still recognizes
    # a same-host lock whose recorded process has exited, including hard exits.
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise SceneBundleError(
            "scene_cleanup_failed",
            f"scene session lock is already held or cannot be acquired: {lock_path}",
        )
    return SceneSession(
        workspace_root=workspace.root,
        session_id=selected_id,
        lock_path=lock_path,
        lock=lock,
    )


def create_scene_lease(session: SceneSession) -> SceneLease:
    """Create a UUID lease and its parent-owned canonical identity record."""

    if not session.is_active:
        raise SceneBundleError(
            "scene_cleanup_failed",
            "cannot create a scene lease without an active session lock",
        )
    workspace = open_workspace(session.workspace_root)
    expected_lock = _session_lock_root(workspace, create=False) / f"{session.session_id}.lock"
    if session.lock_path != expected_lock:
        raise SceneBundleError("scene_cleanup_failed", "scene session lock path is invalid")
    root = _required_lease_root(workspace, create=True)
    lease_id = uuid4().hex
    path = root / lease_id
    created = False
    try:
        path.mkdir(mode=0o700)
        created = True
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise SceneBundleError(
                "scene_cleanup_failed",
                "scene lease is not a regular directory",
            )
        lease = SceneLease(
            workspace_root=workspace.root,
            lease_id=lease_id,
            session_id=session.session_id,
            path=path,
            device=info.st_dev,
            inode=info.st_ino,
        )
        record = SceneLeaseRecord(
            lease_id=lease.lease_id,
            session_id=lease.session_id,
            device=lease.device,
            inode=lease.inode,
        )
        _write_exclusive_regular_file(
            path / SCENE_LEASE_NAME,
            canonical_scene_json_bytes(record.model_dump(mode="json")),
        )
        verify_scene_lease(lease)
        return lease
    except Exception:
        if created:
            _remove_new_empty_or_recorded_lease(path)
        raise


def validate_scene_lease(
    workspace_path: Path,
    payload: SceneLeasePayload | Mapping[str, object],
) -> SceneLease:
    """Reconstruct and verify a parent-created worker destination."""

    workspace = open_workspace(workspace_path)
    try:
        parsed = (
            payload
            if isinstance(payload, SceneLeasePayload)
            else SceneLeasePayload.model_validate(payload, strict=True)
        )
    except ValidationError as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene lease payload is invalid",
        ) from exc
    lease = SceneLease(
        workspace_root=workspace.root,
        lease_id=parsed.lease_id,
        session_id=parsed.session_id,
        path=_required_lease_root(workspace, create=False) / parsed.lease_id,
        device=parsed.device,
        inode=parsed.inode,
    )
    verify_scene_lease(lease)
    return lease


def verify_scene_lease(lease: SceneLease) -> SceneLeaseRecord:
    """Revalidate containment, inode identity, and the parent lease record."""

    workspace = open_workspace(lease.workspace_root)
    root = _required_lease_root(workspace, create=False)
    expected_path = root / lease.lease_id
    if _UUID_HEX_PATTERN.fullmatch(lease.lease_id) is None:
        raise SceneBundleError("scene_integrity_error", "scene lease ID is invalid")
    if _UUID_HEX_PATTERN.fullmatch(lease.session_id) is None:
        raise SceneBundleError("scene_integrity_error", "scene session ID is invalid")
    if lease.path != expected_path:
        raise SceneBundleError("scene_integrity_error", "scene lease path is invalid")
    try:
        info = lease.path.lstat()
    except OSError as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            f"scene lease is unavailable: {lease.path}",
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SceneBundleError(
            "scene_integrity_error",
            "scene lease must be a regular directory",
        )
    if (info.st_dev, info.st_ino) != (lease.device, lease.inode):
        raise SceneBundleError("scene_integrity_error", "scene lease was replaced")
    if lease.path.resolve().parent != root.resolve():
        raise SceneBundleError("scene_integrity_error", "scene lease escapes its workspace")
    record = _read_scene_lease_record(lease.path / SCENE_LEASE_NAME)
    expected = SceneLeaseRecord(
        lease_id=lease.lease_id,
        session_id=lease.session_id,
        device=lease.device,
        inode=lease.inode,
    )
    if record != expected:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene lease record disagrees with its parent-held identity",
        )
    return record


def remove_scene_lease(lease: SceneLease) -> None:
    """Remove one explicitly owned lease after exact identity revalidation."""

    verify_scene_lease(lease)
    _remove_recognized_lease(lease)


def cleanup_abandoned_scene_leases(workspace_path: Path) -> SceneCleanupReport:
    """Remove only recognized leases whose session liveness can be locked."""

    workspace = open_workspace(workspace_path)
    root = _lease_root(workspace, create=False, allow_missing=True)
    if root is None:
        return SceneCleanupReport(entries=())
    entries: list[SceneCleanupEntry] = []
    try:
        candidates = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise SceneBundleError(
            "scene_cleanup_failed",
            f"scene lease root cannot be scanned: {root}",
        ) from exc
    for candidate in candidates:
        try:
            lease = _recognized_cleanup_lease(workspace, candidate)
        except SceneBundleError as exc:
            entries.append(
                SceneCleanupEntry(path=candidate, action="preserved", reason=exc.message)
            )
            continue
        probe = _try_lock_abandoned_session(workspace, lease.session_id)
        if probe is None:
            entries.append(
                SceneCleanupEntry(
                    path=candidate,
                    action="preserved",
                    reason="scene session lock is held or its liveness is uncertain",
                )
            )
            continue
        try:
            lease = _recognized_cleanup_lease(workspace, candidate)
            _remove_recognized_lease(lease)
        except SceneBundleError as exc:
            entries.append(
                SceneCleanupEntry(path=candidate, action="preserved", reason=exc.message)
            )
        else:
            entries.append(
                SceneCleanupEntry(
                    path=candidate,
                    action="removed",
                    reason="recognized scene lease has no live session owner",
                )
            )
        finally:
            probe.unlock()
    return SceneCleanupReport(entries=tuple(entries))


def _read_scene_lease_record(path: Path) -> SceneLeaseRecord:
    data = read_scene_regular_file(
        path,
        maximum_bytes=_LEASE_RECORD_MAX_BYTES,
        label="scene lease",
    )
    raw = parse_canonical_scene_json_object(data, label="scene lease")
    version = raw.get("scene_lease_schema_version")
    if isinstance(version, bool) or version != SCENE_LEASE_SCHEMA_VERSION:
        raise SceneBundleError(
            "scene_integrity_error",
            f"unsupported scene lease schema version: {version!r}",
        )
    try:
        record = SceneLeaseRecord.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene lease record is invalid",
        ) from exc
    if data != canonical_scene_json_bytes(record.model_dump(mode="json")):
        raise SceneBundleError(
            "scene_integrity_error",
            "scene lease record is not canonical JSON",
        )
    return record


def _recognized_cleanup_lease(workspace: Workspace, candidate: Path) -> SceneLease:
    if candidate.parent != _required_lease_root(workspace, create=False):
        raise SceneBundleError("scene_cleanup_failed", "scene cleanup path is outside lease root")
    if _UUID_HEX_PATTERN.fullmatch(candidate.name) is None:
        raise SceneBundleError("scene_cleanup_failed", "unrecognized scene lease name")
    try:
        info = candidate.lstat()
    except OSError as exc:
        raise SceneBundleError("scene_cleanup_failed", "scene lease cannot be inspected") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SceneBundleError(
            "scene_cleanup_failed",
            "scene cleanup candidate is not a regular directory",
        )
    record = _read_scene_lease_record(candidate / SCENE_LEASE_NAME)
    lease = SceneLease(
        workspace_root=workspace.root,
        lease_id=record.lease_id,
        session_id=record.session_id,
        path=candidate,
        device=record.device,
        inode=record.inode,
    )
    try:
        verify_scene_lease(lease)
        _verify_allowed_lease_children(lease)
    except SceneBundleError as exc:
        raise SceneBundleError("scene_cleanup_failed", exc.message) from exc
    return lease


def _verify_allowed_lease_children(lease: SceneLease) -> None:
    try:
        children = tuple(lease.path.iterdir())
    except OSError as exc:
        raise SceneBundleError("scene_cleanup_failed", "scene lease cannot be scanned") from exc
    for child in children:
        if child.name not in _ALLOWED_LEASE_FILES:
            raise SceneBundleError(
                "scene_cleanup_failed",
                f"scene lease contains an unrecognized entry: {child.name}",
            )
        try:
            info = child.lstat()
        except OSError as exc:
            raise SceneBundleError(
                "scene_cleanup_failed",
                f"scene lease entry cannot be inspected: {child.name}",
            ) from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise SceneBundleError(
                "scene_cleanup_failed",
                f"scene lease entry is not a regular file: {child.name}",
            )


def _remove_recognized_lease(lease: SceneLease) -> None:
    verify_scene_lease(lease)
    _verify_allowed_lease_children(lease)
    for name in (SCENE_MANIFEST_NAME, SCENE_BINARY_NAME, SCENE_LEASE_NAME):
        path = lease.path / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SceneBundleError(
                "scene_cleanup_failed",
                f"scene lease entry cannot be inspected before removal: {name}",
            ) from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise SceneBundleError(
                "scene_cleanup_failed",
                f"scene lease entry changed before removal: {name}",
            )
        try:
            path.unlink()
        except OSError as exc:
            raise SceneBundleError(
                "scene_cleanup_failed",
                f"scene lease entry could not be removed: {name}",
            ) from exc
    try:
        current = lease.path.lstat()
        if (current.st_dev, current.st_ino) != (lease.device, lease.inode):
            raise SceneBundleError("scene_cleanup_failed", "scene lease changed during cleanup")
        lease.path.rmdir()
    except SceneBundleError:
        raise
    except OSError as exc:
        raise SceneBundleError(
            "scene_cleanup_failed",
            "scene lease directory could not be removed",
        ) from exc


def _try_lock_abandoned_session(workspace: Workspace, session_id: str) -> QLockFile | None:
    root = _session_lock_root(workspace, create=True)
    lock_path = root / f"{session_id}.lock"
    try:
        _verify_lock_path_type(lock_path)
    except SceneBundleError:
        return None
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        return None
    return lock


def _verify_lock_path_type(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SceneBundleError(
            "scene_cleanup_failed",
            f"scene session lock cannot be inspected safely: {path}",
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SceneBundleError(
            "scene_cleanup_failed",
            f"scene session lock is not a private regular file: {path}",
        )


def _lease_root(
    workspace: Workspace,
    *,
    create: bool,
    allow_missing: bool = False,
) -> Path | None:
    return _private_child_root(
        workspace,
        name=SCENE_LEASE_ROOT_NAME,
        create=create,
        allow_missing=allow_missing,
    )


def _required_lease_root(workspace: Workspace, *, create: bool) -> Path:
    root = _lease_root(workspace, create=create)
    if root is None:  # pragma: no cover - excluded by allow_missing=False
        raise SceneBundleError("scene_cleanup_failed", "scene lease root is missing")
    return root


def _session_lock_root(workspace: Workspace, *, create: bool) -> Path:
    root = _private_child_root(
        workspace,
        name=SCENE_SESSION_LOCK_ROOT_NAME,
        create=create,
        allow_missing=False,
    )
    if root is None:  # pragma: no cover - excluded by allow_missing=False
        raise SceneBundleError("scene_cleanup_failed", "scene session lock root is missing")
    return root


def _private_child_root(
    workspace: Workspace,
    *,
    name: str,
    create: bool,
    allow_missing: bool,
) -> Path | None:
    private = workspace.private_directory
    if private.is_symlink():
        raise SceneBundleError(
            "scene_cleanup_failed",
            "workspace private directory must not be a symbolic link",
        )
    root = private / name
    if root.is_symlink():
        raise SceneBundleError(
            "scene_cleanup_failed",
            f"{name} root must not be a symbolic link",
        )
    if create:
        try:
            root.mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:
            raise SceneBundleError(
                "scene_cleanup_failed",
                f"{name} root cannot be created: {root}",
            ) from exc
    if not root.exists():
        if allow_missing:
            return None
        raise SceneBundleError("scene_cleanup_failed", f"{name} root is missing: {root}")
    try:
        info = root.lstat()
    except OSError as exc:
        raise SceneBundleError(
            "scene_cleanup_failed",
            f"{name} root cannot be inspected: {root}",
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SceneBundleError(
            "scene_cleanup_failed",
            f"{name} root is not a regular directory: {root}",
        )
    if root.resolve().parent != private.resolve():
        raise SceneBundleError(
            "scene_cleanup_failed",
            f"{name} root escapes the workspace private directory",
        )
    return root


def _write_exclusive_regular_file(path: Path, data: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        with suppress(OSError):
            path.unlink()
        raise


def _remove_new_empty_or_recorded_lease(path: Path) -> None:
    try:
        children = tuple(path.iterdir())
    except OSError:
        return
    if any(child.name != SCENE_LEASE_NAME or child.is_symlink() for child in children):
        return
    for child in children:
        try:
            child.unlink()
        except OSError:
            return
    try:
        path.rmdir()
    except OSError:
        return
