from __future__ import annotations

import re
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

STAGING_NAME = re.compile(
    r"^\.\d{8}T\d{6}Z_"
    r"(property|saturation|vapor_fraction|model_sweep|preparation)_"
    r"[0-9a-f]{8}\.staging$"
)


@dataclass(frozen=True)
class StagingCandidate:
    path: Path
    device: int
    inode: int
    modified_at_utc: str
    age_seconds: float
    removable: bool
    issue: str | None = None


def scan_staging_candidates(output_root: Path) -> list[StagingCandidate]:
    root = output_root.resolve()
    if not root.is_dir():
        return []
    now = datetime.now(timezone.utc).timestamp()
    candidates: list[StagingCandidate] = []
    for path in root.iterdir():
        if STAGING_NAME.fullmatch(path.name) is None:
            continue
        try:
            info = path.lstat()
        except OSError as exc:
            candidates.append(StagingCandidate(path, -1, -1, "unknown", 0.0, False, str(exc)))
            continue
        modified = datetime.fromtimestamp(info.st_mtime, timezone.utc)
        issue = None
        if stat.S_ISLNK(info.st_mode):
            issue = "candidate is a symbolic link"
        elif not stat.S_ISDIR(info.st_mode):
            issue = "candidate is not a directory"
        candidates.append(
            StagingCandidate(
                path=path,
                device=info.st_dev,
                inode=info.st_ino,
                modified_at_utc=modified.isoformat().replace("+00:00", "Z"),
                age_seconds=max(0.0, now - info.st_mtime),
                removable=issue is None,
                issue=issue,
            )
        )
    return sorted(candidates, key=lambda item: item.path.name)


def remove_staging_candidate(candidate: StagingCandidate, output_root: Path) -> None:
    root = output_root.resolve()
    path = candidate.path
    if path.parent.resolve() != root or path.parent != output_root:
        raise ValueError("staging candidate is not a direct child of the output root")
    if STAGING_NAME.fullmatch(path.name) is None:
        raise ValueError("staging candidate name is not recognized")
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ValueError("staging candidate is no longer a regular directory")
    if (info.st_dev, info.st_ino) != (candidate.device, candidate.inode):
        raise ValueError("staging candidate was replaced after the scan")
    if path.resolve().parent != root:
        raise ValueError("staging candidate no longer resolves under the output root")
    shutil.rmtree(path)
