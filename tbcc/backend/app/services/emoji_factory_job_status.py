"""On-disk status for async emoji-factory jobs (poll via GET /emoji-factory/jobs/{id}/status)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.emoji_factory_jobs import emoji_factory_jobs_dir

STATUS_FILE = "status.json"
REQUEST_FILE = "request.json"
TERMINAL_STATUSES = frozenset({"done", "failed"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def job_dir_for(job_id: str) -> Path:
    job_id = (job_id or "").strip()
    if not job_id or ".." in job_id or "/" in job_id or "\\" in job_id:
        raise ValueError("invalid job_id")
    return emoji_factory_jobs_dir() / job_id


def write_job_status(job_dir: Path, **fields: Any) -> dict[str, Any]:
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / STATUS_FILE
    current: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except (OSError, json.JSONDecodeError):
            current = {}
    current.update(fields)
    current["updated_at"] = _utc_now()
    if "created_at" not in current:
        current["created_at"] = current["updated_at"]
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def read_job_status(job_dir: Path) -> dict[str, Any] | None:
    path = job_dir / STATUS_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_job_request(job_dir: Path, payload: dict[str, Any]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / REQUEST_FILE).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_job_request(job_dir: Path) -> dict[str, Any] | None:
    path = job_dir / REQUEST_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def public_job_status(job_id: str) -> dict[str, Any]:
    job_id = (job_id or "").strip()
    try:
        job_dir = job_dir_for(job_id)
    except ValueError as e:
        return {"ok": False, "error": str(e), "job_id": job_id}

    if not job_dir.is_dir():
        return {"ok": False, "error": "not_found", "job_id": job_id}

    status = read_job_status(job_dir) or {"status": "unknown", "stage": "unknown"}
    body: dict[str, Any] = {
        "ok": True,
        "job_id": job_id,
        "status": status.get("status") or "unknown",
        "stage": status.get("stage") or status.get("status") or "unknown",
        "poll_url": f"/emoji-factory/jobs/{job_id}/status",
        "updated_at": status.get("updated_at"),
        "created_at": status.get("created_at"),
    }
    if status.get("error"):
        body["error"] = status["error"]
    if status.get("split"):
        body["split"] = status["split"]
    if status.get("upload"):
        body["upload"] = status["upload"]
    if status.get("followup"):
        body["followup"] = status["followup"]
    if status.get("celery_task_id"):
        body["celery_task_id"] = status["celery_task_id"]
    return body
