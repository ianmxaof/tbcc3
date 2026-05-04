"""
Read-only status for the download inbox organizer (see app.services.watch_folder_organizer).

Same environment variables as the CLI; the API process loads tbcc/.env on startup (main.py).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter

from app.services.watch_folder_organizer import _CATEGORIES

router = APIRouter()


def _env_path(name: str, default: str | None = None) -> Path | None:
    v = (os.environ.get(name) or "").strip()
    if not v:
        return Path(default).resolve() if default else None
    return Path(v).expanduser().resolve()


def _count_files_direct(p: Path) -> int | None:
    if not p.is_dir():
        return None
    n = 0
    try:
        for x in p.iterdir():
            if x.is_file():
                n += 1
    except OSError:
        return None
    return n


def _tail_jsonl(path: Path, max_records: int = 40) -> list[dict]:
    if not path.is_file() or max_records <= 0:
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 256_000)
            f.seek(max(0, size - chunk))
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    out: list[dict] = []
    for ln in lines[-max_records:]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            out.append({"parse_error": True, "preview": ln[:400]})
    return out


@router.get("/status")
def watch_folder_status():
    """
    Inbox / library paths, shallow file counts, and recent JSONL log lines (if configured).

    Does not start the watcher — run `python -m app.services.watch_folder_organizer` separately.
    """
    inbox = _env_path("TBCC_WATCH_INBOX")
    if not inbox:
        return {
            "configured": False,
            "hint": "Set TBCC_WATCH_INBOX in tbcc/.env to an absolute folder path, then restart the API.",
        }

    default_lib = inbox.parent / "tbcc_library"
    library = _env_path("TBCC_WATCH_LIBRARY", str(default_lib)) or default_lib
    debounce = float(os.environ.get("TBCC_WATCH_DEBOUNCE_S") or "1.5")
    stable_wait_s = float(os.environ.get("TBCC_WATCH_STABLE_WAIT_S") or "2.0")
    category_overrides_raw = (os.environ.get("TBCC_WATCH_CATEGORY_OVERRIDES") or "").strip()
    log_raw = (os.environ.get("TBCC_WATCH_LOG") or "").strip()
    log_path = Path(log_raw).expanduser() if log_raw else None

    inbox_resolved = False
    inbox_exists = False
    inbox_is_dir = False
    inbox_path_str = str(inbox)
    try:
        inbox = inbox.resolve()
        inbox_resolved = True
        inbox_exists = inbox.exists()
        inbox_is_dir = inbox.is_dir()
        inbox_path_str = str(inbox)
    except OSError:
        pass

    lib_path_str = str(library)
    library_resolved = False
    library_exists = False
    library_is_dir = False
    try:
        library = library.resolve()
        library_resolved = True
        library_exists = library.exists()
        library_is_dir = library.is_dir()
        lib_path_str = str(library)
    except OSError:
        pass

    categories = list(_CATEGORIES.keys()) + ["Other"]
    library_files: dict[str, int | None] = {}
    if library_resolved and library_is_dir:
        for name in categories:
            library_files[name] = _count_files_direct(library / name)

    log_info: dict = {"path": str(log_path) if log_path else None, "exists": False, "recent": []}
    if log_path:
        try:
            lp = log_path.expanduser().resolve()
            log_info["path"] = str(lp)
            log_info["exists"] = lp.is_file()
            if log_info["exists"]:
                log_info["recent"] = _tail_jsonl(lp, max_records=35)
        except OSError:
            pass

    return {
        "configured": True,
        "debounce_s": debounce,
        "stable_wait_s": stable_wait_s,
        "inbox": {
            "path": inbox_path_str,
            "resolved": inbox_resolved,
            "exists": inbox_exists,
            "is_dir": inbox_is_dir,
            "file_count": _count_files_direct(inbox) if inbox_is_dir else None,
        },
        "library": {
            "path": lib_path_str,
            "resolved": library_resolved,
            "exists": library_exists,
            "is_dir": library_is_dir,
            "files_per_category": library_files,
        },
        "log": log_info,
        "runbook": {
            "watch": "cd tbcc/backend && python -m app.services.watch_folder_organizer",
            "once": "cd tbcc/backend && python -m app.services.watch_folder_organizer --once",
            "dry_run": "cd tbcc/backend && python -m app.services.watch_folder_organizer --once --dry-run",
        },
        "category_overrides_raw": category_overrides_raw or None,
    }
