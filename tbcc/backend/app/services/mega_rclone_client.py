"""MEGA account operations via rclone (works with 2FA when remote is configured)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from app.services.mega_account_client import MegaFolderEntry

logger = logging.getLogger(__name__)

_FILE_TYPE = 0
_SKIP_FOLDER_NAMES = frozenset({"mega", "aof logos"})
_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})
_LEGACY_KEYWORDS = (
    "readme",
    "read_me",
    "read me",
    "telegram",
    "promo",
    "banner",
    "links",
    "link",
    "join",
    "channel",
    "discord",
    "onlyfans",
    "gigafans",
    "plugleak",
    "leak",
    "premium",
    "stash",
    "logo",
    "hub",
)


def mega_rclone_remote() -> str:
    raw = (os.getenv("TBCC_MEGA_RCLONE_REMOTE") or "mega").strip().rstrip(":")
    return f"{raw}:"


def mega_rename_suffix_from_env() -> str:
    return (os.getenv("TBCC_MEGA_RENAME_SUFFIX") or "-TME AOFMAINHUB").strip()


def use_mega_rclone() -> bool:
    mode = (os.getenv("TBCC_MEGA_BACKEND") or "rclone").strip().lower()
    return mode == "rclone"


def verify_rclone_mega_access() -> None:
    proc = _run_rclone(["lsf", mega_rclone_remote(), "--dirs-only", "--max-depth", "1"], timeout=300.0)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "rclone mega access failed").strip()
        raise RuntimeError(
            f"{msg}\n"
            "Fix: `rclone config update mega pass YOUR_PASSWORD` — if 2FA is off, clear stale codes: "
            "`rclone config update mega 2fa \"\"`"
        )


def _run_rclone(args: list[str], *, timeout: float = 300.0) -> subprocess.CompletedProcess[str]:
    cmd = ["rclone", *args]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        err = f"rclone timed out after {timeout}s: {' '.join(cmd[:4])}"
        logger.warning(err)
        return subprocess.CompletedProcess(cmd, returncode=-1, stdout="", stderr=err)


def _remote_path(folder_name: str, *, file_name: str | None = None) -> str:
    remote = mega_rclone_remote()
    base = f"{remote}{folder_name}"
    if file_name:
        return f"{base}/{file_name}"
    return base


def should_skip_folder(name: str) -> bool:
    return (name or "").strip().lower() in _SKIP_FOLDER_NAMES


def target_rename_name(current: str, *, suffix: str | None = None) -> str | None:
    suf = (suffix if suffix is not None else mega_rename_suffix_from_env()).strip()
    name = (current or "").strip()
    if not name or should_skip_folder(name):
        return None
    if suf and name.endswith(suf):
        return None
    if not suf:
        return None
    return f"{name}{suf}"[:256]


def list_mega_folders_rclone(*, root_prefix: str | None = None) -> list[MegaFolderEntry]:
    remote = mega_rclone_remote()
    proc = _run_rclone(["lsf", remote, "--dirs-only", "--max-depth", "1"], timeout=300.0)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "rclone lsf failed")[:500])
    prefix = (root_prefix or "").strip().strip("/").lower()
    out: list[MegaFolderEntry] = []
    for line in (proc.stdout or "").splitlines():
        name = line.strip().rstrip("/")
        if not name:
            continue
        if prefix and not name.lower().startswith(prefix):
            continue
        out.append(
            MegaFolderEntry(
                handle=name,
                name=name,
                path=name,
                parent_handle=None,
            )
        )
    out.sort(key=lambda e: e.name.lower())
    return out


def mega_rclone_timeout_seconds(default: float = 900.0) -> float:
    raw = (os.getenv("TBCC_MEGA_RCLONE_TIMEOUT_S") or "").strip()
    if not raw:
        return default
    try:
        return max(60.0, float(raw))
    except ValueError:
        return default


def rename_mega_folder_rclone(entry: MegaFolderEntry, new_name: str) -> None:
    timeout = mega_rclone_timeout_seconds(900.0)
    proc = _run_rclone(
        ["moveto", _remote_path(entry.name), _remote_path(new_name)],
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "rclone moveto failed")[:500])


def apply_rename_suffix_rclone(
    entries: list[MegaFolderEntry],
    *,
    suffix: str | None = None,
    execute: bool,
) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    suf = suffix if suffix is not None else mega_rename_suffix_from_env()
    for entry in entries:
        new_name = target_rename_name(entry.name, suffix=suf)
        if not new_name:
            continue
        row = {"path": entry.path, "from": entry.name, "to": new_name}
        if execute:
            try:
                rename_mega_folder_rclone(entry, new_name)
                row["renamed"] = "true"
            except Exception as exc:
                row["renamed"] = "false"
                row["error"] = str(exc)[:300]
                logger.warning("rename failed %s → %s: %s", entry.name, new_name, exc)
        changes.append(row)
    return changes


def mega_link_delay_seconds() -> float:
    raw = (os.getenv("TBCC_MEGA_LINK_DELAY") or "20").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 20.0


def mega_link_retries_from_env(*, default: int = 4) -> int:
    raw = (os.getenv("TBCC_MEGA_LINK_RETRIES") or "").strip()
    if not raw:
        return max(1, default)
    try:
        return max(1, int(raw))
    except ValueError:
        return max(1, default)


def folder_has_root_file_rclone(folder_name: str, filename: str) -> bool:
    want = (filename or "").strip().lower()
    if not want:
        return False
    for name in list_mega_folder_files_rclone(folder_name):
        if (name or "").strip().lower() == want:
            return True
    return False


def export_folder_link_rclone(entry: MegaFolderEntry, *, retries: int = 4) -> str:
    last_err = "rclone link failed"
    for attempt in range(max(1, retries)):
        if attempt > 0:
            time.sleep(mega_link_delay_seconds() * attempt)
        proc = _run_rclone(["link", _remote_path(entry.name)], timeout=180.0)
        if proc.returncode != 0:
            last_err = (proc.stderr or proc.stdout or "rclone link failed")[:500]
            if "access violation" in last_err.lower() or "timed out" in last_err.lower():
                continue
            raise RuntimeError(last_err)
        link = (proc.stdout or "").strip().splitlines()[0].strip()
        if not link.startswith("http"):
            last_err = f"rclone link returned invalid URL: {link[:120]!r}"
            continue
        return link
    raise RuntimeError(last_err)


def upload_text_to_folder_rclone(
    entry: MegaFolderEntry,
    text: str,
    *,
    dest_filename: str,
) -> str:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tmp:
        tmp.write(text)
        tmp_path = tmp.name
    try:
        proc = _run_rclone(
            ["copyto", tmp_path, _remote_path(entry.name, file_name=dest_filename)],
            timeout=180.0,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "rclone copyto failed")[:500])
        return dest_filename
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass


def list_mega_folder_files_rclone(folder_name: str) -> list[str]:
    proc = _run_rclone(
        ["lsf", _remote_path(folder_name), "--files-only", "--max-depth", "1"],
        timeout=120.0,
    )
    if proc.returncode != 0:
        return []
    return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]


def upload_local_file_to_folder_rclone(
    entry: MegaFolderEntry,
    local_path: Path,
    *,
    dest_filename: str | None = None,
) -> str:
    fname = (dest_filename or local_path.name).strip()
    proc = _run_rclone(
        ["copyto", str(local_path), _remote_path(entry.name, file_name=fname)],
        timeout=180.0,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "rclone copyto failed")[:500])
    return fname


def copy_mega_file_to_folder_rclone(
    *,
    src_folder: str,
    src_filename: str,
    entry: MegaFolderEntry,
    dest_filename: str | None = None,
) -> str:
    fname = (dest_filename or src_filename).strip()
    proc = _run_rclone(
        [
            "copyto",
            _remote_path(src_folder, file_name=src_filename),
            _remote_path(entry.name, file_name=fname),
        ],
        timeout=180.0,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "rclone copyto failed")[:500])
    return fname


def _is_legacy_root_file(name: str, *, keep_names: set[str]) -> bool:
    low = name.lower()
    if low in keep_names:
        return False
    if low.endswith(".txt"):
        return True
    ext = Path(name).suffix.lower()
    if ext in _IMAGE_EXTS:
        return any(k in low for k in _LEGACY_KEYWORDS)
    return False


def purge_legacy_root_files_rclone(
    entry: MegaFolderEntry,
    *,
    keep_filenames: set[str],
    execute: bool,
) -> list[str]:
    proc = _run_rclone(
        ["lsjson", _remote_path(entry.name), "--files-only", "--max-depth", "1"],
        timeout=120.0,
    )
    if proc.returncode != 0:
        return []
    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    removed: list[str] = []
    keep = {k.lower() for k in keep_filenames}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or item.get("Path") or "").strip()
        if not name or "/" in name:
            continue
        if not _is_legacy_root_file(name, keep_names=keep):
            continue
        if execute:
            del_proc = _run_rclone(["delete", _remote_path(entry.name, file_name=name)], timeout=60.0)
            if del_proc.returncode != 0:
                logger.warning("rclone delete failed %s: %s", name, del_proc.stderr[:200])
                continue
        removed.append(name)
    return removed


def folder_size_bytes_rclone(folder_name: str) -> int | None:
    stats = folder_size_stats_rclone(folder_name)
    return stats.get("bytes")


def folder_size_stats_rclone(folder_name: str) -> dict[str, int | float | None]:
    """Bytes, file count, and GB for a MEGA folder via rclone size --json."""
    proc = _run_rclone(
        ["size", _remote_path(folder_name), "--json"],
        timeout=mega_rclone_timeout_seconds(600.0),
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "rclone size failed")[:500])
    try:
        data = json.loads(proc.stdout or "{}")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"rclone size invalid json: {exc}") from exc
    nbytes = int(data.get("bytes") or 0)
    count_raw = data.get("count")
    file_count = int(count_raw) if count_raw is not None else None
    size_gb = round(nbytes / (1024**3), 2) if nbytes > 0 else None
    return {"bytes": nbytes, "file_count": file_count, "size_gb": size_gb}


def folder_size_gb_rclone(folder_name: str) -> float | None:
    try:
        stats = folder_size_stats_rclone(folder_name)
    except Exception:
        return None
    size_gb = stats.get("size_gb")
    return float(size_gb) if size_gb else None


def list_folder_files_json_rclone(folder_name: str, *, max_depth: int = 4) -> list[dict[str, Any]]:
    proc = _run_rclone(
        [
            "lsjson",
            _remote_path(folder_name),
            "-R",
            "--files-only",
            "--max-depth",
            str(max(1, max_depth)),
        ],
        timeout=600.0,
    )
    if proc.returncode != 0:
        return []
    try:
        raw = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [x for x in raw if isinstance(x, dict)]


def download_folder_file_bytes_rclone(folder_name: str, rel_path: str) -> bytes:
    rel = (rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("invalid_rel_path")
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
    try:
        proc = _run_rclone(
            ["copyto", _remote_path(folder_name, file_name=rel), tmp_path],
            timeout=300.0,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "rclone copyto failed")[:500])
        return Path(tmp_path).read_bytes()
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass


_MEDIA_EXTS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".mp4", ".mov", ".webm", ".avi", ".mkv"}
)


def download_mega_folder_to_local_rclone(
    folder_name: str,
    dest_dir: Path,
    *,
    max_files: int | None = None,
    max_depth: int = 4,
) -> int:
    """Copy MEGA folder media to local staging — bulk rclone copy, then optional cap."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest_dir.exists() and any(dest_dir.iterdir()):
        for child in dest_dir.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    transfers = (os.getenv("TBCC_RCLONE_TRANSFERS") or "8").strip()
    args = [
        "copy",
        _remote_path(folder_name),
        str(dest_dir),
        "--fast-list",
        "--transfers",
        transfers,
        "--max-depth",
        str(max(1, max_depth)),
    ]
    for pat in (
        "*.jpg",
        "*.jpeg",
        "*.png",
        "*.gif",
        "*.webp",
        "*.bmp",
        "*.mp4",
        "*.mov",
        "*.webm",
        "*.avi",
        "*.mkv",
    ):
        args.extend(["--include", pat])
    proc = _run_rclone(args, timeout=mega_rclone_timeout_seconds(1200.0))
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "rclone copy failed")[:500])

    found: list[Path] = []
    for path in sorted(dest_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in _MEDIA_EXTS:
            found.append(path)
    if max_files is not None and len(found) > max_files:
        keep = {p.resolve() for p in found[:max_files]}
        for path in found[max_files:]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.debug("staging trim unlink failed %s", path, exc_info=True)
        found = [p for p in found if p.resolve() in keep]
    return len(found)
