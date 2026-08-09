from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

JOB_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LoadedJob:
    path: Path
    data: dict[str, Any] | None
    error: str | None = None


class JobStore:
    """Persist small GUI request records without changing workspace provenance."""

    def __init__(self, private_directory: Path) -> None:
        self.directory = private_directory / "jobs"

    def start(
        self,
        *,
        request_id: str,
        operation: str,
        config_relative_path: str,
        yaml_snapshot: str,
        config_sha256: str,
        owner: str = "execution",
        plan_identity: dict[str, Any] | None = None,
        preparation_source_identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        record: dict[str, Any] = {
            "job_schema_version": JOB_SCHEMA_VERSION,
            "request_id": request_id,
            "operation": operation,
            "owner": owner,
            "status": "running",
            "created_at_utc": now,
            "updated_at_utc": now,
            "completed_at_utc": None,
            "configuration": {
                "relative_path": config_relative_path,
                "yaml_snapshot": yaml_snapshot,
                "sha256": config_sha256,
            },
            "phase": "starting",
            "progress": None,
            "summary": {},
            "terminal_envelope": None,
        }
        if plan_identity is not None:
            record["plan_identity"] = plan_identity
        if preparation_source_identity is not None:
            record["preparation_source_identity"] = preparation_source_identity
        self.write(record)
        return record

    def update_event(
        self, record: dict[str, Any], event_type: str, payload: dict[str, Any]
    ) -> None:
        if event_type == "phase":
            record["phase"] = payload.get("name")
        elif event_type == "progress":
            record["progress"] = {
                "completed": payload.get("completed"),
                "total": payload.get("total"),
            }
        else:
            return
        record["updated_at_utc"] = _utc_now()
        self.write(record)

    def finish(self, record: dict[str, Any], envelope: dict[str, Any]) -> None:
        terminal = envelope.get("terminal_event")
        terminal_type = terminal.get("type") if isinstance(terminal, dict) else None
        payload = terminal.get("payload") if isinstance(terminal, dict) else None
        client_failure = envelope.get("client_failure")
        if isinstance(client_failure, dict):
            payload = client_failure
        clean_transport = (
            client_failure is None
            and envelope.get("exit_code") == 0
            and envelope.get("exit_status") == "normal"
            and not envelope.get("force_stopped")
            and envelope.get("cleanup_error") is None
        )
        if envelope.get("force_stopped"):
            status = "force_stopped"
        elif terminal_type == "result" and clean_transport:
            status = "completed"
        elif terminal_type == "cancelled" and clean_transport:
            status = "cancelled"
        else:
            status = "failed"
            if not isinstance(client_failure, dict) and terminal_type == "result":
                payload = {
                    "category": "process",
                    "code": "execution_failed",
                    "message": (
                        "worker returned a result but exited with status "
                        f"{envelope.get('exit_status')} and code {envelope.get('exit_code')}"
                    ),
                }
        now = _utc_now()
        record["status"] = status
        record["updated_at_utc"] = now
        record["completed_at_utc"] = now
        record["summary"] = payload if isinstance(payload, dict) else {}
        record["terminal_envelope"] = envelope
        self.write(record)

    def finish_start_failure(
        self,
        record: dict[str, Any],
        *,
        request_type: str,
        category: str,
        code: str,
        message: str,
    ) -> None:
        """Record a failure that occurred before the worker transport started."""

        self.finish(
            record,
            {
                "request_id": str(record["request_id"]),
                "request_type": request_type,
                "terminal_event": None,
                "client_failure": {
                    "category": category,
                    "code": code,
                    "message": message,
                },
                "stderr": "",
                "exit_code": None,
                "exit_status": "not_started",
                "force_stopped": False,
                "cleanup_error": None,
            },
        )

    def write(self, record: dict[str, Any]) -> Path:
        request_id = str(record["request_id"])
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{request_id}.json"
        write_json_atomic(destination, record)
        return destination

    def load(self) -> list[LoadedJob]:
        if not self.directory.is_dir():
            return []
        jobs: list[LoadedJob] = []
        for path in self.directory.glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("job record root is not an object")
                if value.get("job_schema_version") != JOB_SCHEMA_VERSION:
                    raise ValueError("unsupported job record schema")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                jobs.append(LoadedJob(path=path, data=None, error=str(exc)))
            else:
                jobs.append(LoadedJob(path=path, data=value))
        return sorted(jobs, key=_job_mtime, reverse=True)

    def remove(self, path: Path) -> None:
        resolved_directory = self.directory.resolve()
        resolved = path.resolve()
        if resolved.parent != resolved_directory or resolved.suffix != ".json":
            raise ValueError("job record is not a direct JSON child of the jobs directory")
        resolved.unlink()


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _job_mtime(job: LoadedJob) -> int:
    try:
        return job.path.stat().st_mtime_ns
    except OSError:
        return 0
