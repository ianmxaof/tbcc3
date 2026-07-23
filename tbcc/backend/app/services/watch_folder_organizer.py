"""
Watch TBCC_WATCH_INBOX and move finished files into TBCC_WATCH_LIBRARY by type (Images, Videos, …).

Run from ``tbcc/backend`` with the API venv:
  python -m app.services.watch_folder_organizer
  python -m app.services.watch_folder_organizer --once

Configure in ``tbcc/.env`` (see TBCC_WATCH_* variables).
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Images": (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".heic", ".jfif"),
    "Videos": (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".mpeg", ".mpg", ".wmv", ".flv", ".m2ts", ".ts"),
    "Audio": (".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".opus", ".wma", ".aiff"),
    "Archives": (".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst"),
    "Documents": (
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".txt",
        ".md",
        ".csv",
        ".json",
        ".xml",
        ".rtf",
        ".odt",
        ".ods",
    ),
    # JDownloader / link grabber containers (keep separate from generic .txt notes)
    "LinkLists": (".dlc", ".crawljob", ".ccf", ".rsdf", ".url", ".webloc"),
    "Playlists": (".m3u8", ".mpd"),
}

_CATEGORY_OVERRIDES: dict[str, str] = {}
_MEDIA_ONLY_CATEGORIES = {"Images", "Videos"}


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[3] / ".env"
        if root.is_file():
            load_dotenv(root, override=True)
    except Exception:
        pass


def _looks_incomplete(path: Path) -> bool:
    n = path.name.lower()
    if n.endswith(".crdownload") or n.endswith(".part"):
        return True
    if n.endswith((".tmp", ".temp", ".download", ".filepart")):
        return True
    if ".!qb" in n:
        return True
    return False


def _parse_category_overrides(raw: str) -> dict[str, str]:
    """
    Parse TBCC_WATCH_CATEGORY_OVERRIDES.
    Format: ".ext=Category,.ext2=Category2" (category names are case-sensitive with _CATEGORIES keys + Other).
    """
    out: dict[str, str] = {}
    if not raw:
        return out
    valid = set(_CATEGORIES.keys()) | {"Other"}
    for chunk in raw.split(","):
        part = chunk.strip()
        if not part or "=" not in part:
            continue
        left, right = part.split("=", 1)
        ext = left.strip().lower()
        cat = right.strip()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        if cat not in valid:
            logger.warning("Ignoring TBCC_WATCH_CATEGORY_OVERRIDES entry with unknown category: %s", part)
            continue
        out[ext] = cat
    return out


def _category_for_path(path: Path) -> str:
    suf = path.suffix.lower()
    if not suf and path.name:
        suf = ""
    if suf in _CATEGORY_OVERRIDES:
        return _CATEGORY_OVERRIDES[suf]
    # Best-effort mime fallback for extension-less files.
    if not suf:
        mime, _ = mimetypes.guess_type(path.name, strict=False)
        if mime:
            if mime.startswith("image/"):
                return "Images"
            if mime.startswith("video/"):
                return "Videos"
            if mime.startswith("audio/"):
                return "Audio"
            if mime in ("application/zip", "application/x-tar", "application/gzip", "application/x-7z-compressed"):
                return "Archives"
            if mime.startswith("text/"):
                return "Documents"
    for folder, exts in _CATEGORIES.items():
        if suf in exts:
            return folder
    return "Other"


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    parent = dest.parent
    for i in range(1, 10_000):
        cand = parent / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
    return parent / f"{stem}_{int(time.time())}{suffix}"


def _append_log(log_path: Path | None, record: dict) -> None:
    if not log_path:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning("watch log write failed: %s", e)


def _is_truthy_env(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def organize_file(
    src: Path,
    library_root: Path,
    log_path: Path | None,
    stable_wait_s: float,
    media_only: bool = False,
    reject_dir: Path | None = None,
    dry_run: bool = False,
) -> tuple[bool, str, Path | None]:
    """
    Move ``src`` into library_root/<Category>/, flat AOF lane folders when enabled,
    or Images/<tier>/… when legacy NSFW sorting is on and lanes are off / unresolved.
    Returns (ok, message, dest_or_none).
    """
    try:
        src = src.resolve()
    except OSError:
        return False, "unreadable path", None
    if not src.is_file():
        return False, "not a file", None
    try:
        from app.services.watch_folder_nsfw import is_watch_sidecar_file

        if is_watch_sidecar_file(src):
            return False, "sidecar companion", None
    except Exception:
        if src.name.lower().endswith(".tbcc-meta.json"):
            return False, "sidecar companion", None
    if _looks_incomplete(src):
        return False, "incomplete download", None
    if stable_wait_s > 0:
        try:
            s1 = src.stat()
            time.sleep(stable_wait_s)
            s2 = src.stat()
            if s1.st_size != s2.st_size or int(s1.st_mtime) != int(s2.st_mtime):
                return False, "file still changing", None
        except OSError:
            return False, "file unavailable", None
    cat = _category_for_path(src)
    if media_only and cat not in _MEDIA_ONLY_CATEGORIES:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "skip_non_media" if not reject_dir else ("dry_run_reject_non_media" if dry_run else "reject_non_media"),
            "category": cat,
            "src": str(src),
        }
        if not reject_dir:
            _append_log(log_path, record)
            return False, f"non-media ({cat})", None
        reject_dest = _unique_dest(reject_dir / src.name)
        record["dest"] = str(reject_dest)
        if dry_run:
            _append_log(log_path, record)
            return True, f"would move non-media -> {reject_dest}", reject_dest
        try:
            reject_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(reject_dest))
        except OSError as e:
            logger.exception("reject move failed %s -> %s", src, reject_dest)
            record["action"] = "error"
            record["error"] = str(e)
            _append_log(log_path, record)
            return False, str(e), None
        _append_log(log_path, record)
        return True, f"moved non-media -> {reject_dest}", reject_dest

    nsfw_meta: dict | None = None
    rel_subdir = cat
    try:
        from app.services.watch_folder_aof import (
            aof_library_subdir,
            preprocess_inbox_media,
            resolve_lane_from_meta,
            watch_aof_lane_folders_enabled,
        )
        from app.services.watch_folder_nsfw import (
            build_watch_metadata,
            image_library_subdir,
            read_watch_sidecar,
            sidecar_path_for,
            watch_nsfw_tier_subfolders_enabled,
            write_watch_sidecar,
        )

        existing = read_watch_sidecar(src) or {}

        if cat in _MEDIA_ONLY_CATEGORIES and not dry_run:
            src, existing = preprocess_inbox_media(src, existing)

        nsfw_meta = dict(existing) if existing else {}
        lane_resolved = resolve_lane_from_meta(nsfw_meta)
        aof_sub = aof_library_subdir(cat, nsfw_meta)

        if aof_sub is not None:
            # Flat AOF lane folders (includes Unsorted) — skip CLIP/NSFW
            rel_subdir = aof_sub
            if lane_resolved:
                nsfw_meta["lane_key"] = lane_resolved
                nsfw_meta["lane_folder"] = aof_sub
                nsfw_meta["route_source"] = "tags"
            else:
                nsfw_meta["route_source"] = "unsorted"
        elif cat == "Images" and watch_nsfw_tier_subfolders_enabled() and not watch_aof_lane_folders_enabled():
            # Legacy nest only when AOF lane mode is explicitly off
            nsfw_meta = build_watch_metadata(src)
            if existing:
                for k, v in existing.items():
                    if k not in nsfw_meta or nsfw_meta.get(k) in (None, "", "unknown"):
                        nsfw_meta[k] = v
            rel_subdir = image_library_subdir(cat, src, nsfw_meta)
    except Exception as e:
        logger.warning("watch metadata/route skipped for %s: %s", src.name, e)

    # Flat emoji lane names are a single segment; legacy paths use /
    sub = str(rel_subdir).replace("\\", "/")
    dest_dir = library_root.joinpath(*sub.split("/")) if "/" in sub else (library_root / sub)
    dest = _unique_dest(dest_dir / src.name)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": "dry_run" if dry_run else "move",
        "category": cat,
        "library_subdir": rel_subdir,
        "src": str(src),
        "dest": str(dest),
    }
    if nsfw_meta:
        record["nsfw_tier"] = nsfw_meta.get("nsfw_tier")
        record["nsfw_class"] = nsfw_meta.get("top_class")
        record["lane_key"] = nsfw_meta.get("lane_key")
        record["route_source"] = nsfw_meta.get("route_source")
        niche = nsfw_meta.get("niche") or {}
        if isinstance(niche, dict):
            record["niche_slug"] = niche.get("primary_slug") or (niche.get("clip") or {}).get("top_slug")
            record["niche_source"] = niche.get("primary_source")
        if nsfw_meta.get("llm"):
            record["llm_niche"] = (nsfw_meta.get("llm") or {}).get("niche")
    if dry_run:
        _append_log(log_path, record)
        return True, f"would move -> {dest}", dest
    try:
        from app.services.watch_folder_nsfw import sidecar_path_for, write_watch_sidecar

        dest_dir.mkdir(parents=True, exist_ok=True)
        old_sidecar = sidecar_path_for(src)
        shutil.move(str(src), str(dest))
        if old_sidecar.is_file():
            try:
                shutil.move(str(old_sidecar), str(sidecar_path_for(dest)))
            except OSError:
                pass
        if nsfw_meta:
            write_watch_sidecar(dest, nsfw_meta)
    except OSError as e:
        logger.exception("move failed %s -> %s", src, dest)
        record["action"] = "error"
        record["error"] = str(e)
        _append_log(log_path, record)
        return False, str(e), None
    _append_log(log_path, record)
    return True, f"moved -> {dest}", dest


def scan_inbox_once(
    inbox: Path,
    library_root: Path,
    log_path: Path | None,
    stable_wait_s: float,
    media_only: bool = False,
    reject_dir: Path | None = None,
    dry_run: bool = False,
) -> int:
    n = 0
    if not inbox.is_dir():
        logger.error("TBCC_WATCH_INBOX is not a directory: %s", inbox)
        return 0
    for entry in sorted(inbox.iterdir()):
        if not entry.is_file():
            continue
        ok, msg, _ = organize_file(
            entry,
            library_root,
            log_path,
            stable_wait_s=stable_wait_s,
            media_only=media_only,
            reject_dir=reject_dir,
            dry_run=dry_run,
        )
        if ok:
            n += 1
            logger.info("%s: %s", entry.name, msg)
        else:
            if msg != "incomplete download":
                logger.debug("skip %s: %s", entry.name, msg)
    return n


def _env_path(name: str, default: str | None = None) -> Path | None:
    v = (os.environ.get(name) or "").strip()
    if not v:
        return Path(default).resolve() if default else None
    return Path(v).expanduser().resolve()


class _DebouncedOrganizer:
    def __init__(
        self,
        inbox: Path,
        library_root: Path,
        log_path: Path | None,
        debounce_s: float,
        stable_wait_s: float,
        media_only: bool,
        reject_dir: Path | None,
    ):
        self.inbox = inbox
        self.library_root = library_root
        self.log_path = log_path
        self.debounce_s = debounce_s
        self.stable_wait_s = stable_wait_s
        self.media_only = media_only
        self.reject_dir = reject_dir
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(self, path: Path) -> None:
        try:
            path = path.resolve()
        except OSError:
            return
        try:
            if path.parent.resolve() != self.inbox.resolve():
                return
        except OSError:
            return
        key = str(path)

        def run() -> None:
            with self._lock:
                self._timers.pop(key, None)
            if not path.is_file():
                return
            ok, msg, _ = organize_file(
                path,
                self.library_root,
                self.log_path,
                stable_wait_s=self.stable_wait_s,
                media_only=self.media_only,
                reject_dir=self.reject_dir,
                dry_run=False,
            )
            if ok:
                logger.info("%s: %s", path.name, msg)
            elif msg not in ("incomplete download", "file still changing"):
                logger.debug("skip %s: %s", path.name, msg)

        with self._lock:
            old = self._timers.pop(key, None)
            if old:
                old.cancel()
            t = threading.Timer(self.debounce_s, run)
            self._timers[key] = t
            t.daemon = True
            t.start()


def run_watch_loop(
    inbox: Path,
    library_root: Path,
    log_path: Path | None,
    debounce_s: float,
    stable_wait_s: float,
    media_only: bool = False,
    reject_dir: Path | None = None,
) -> None:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError as e:
        logger.error("Install watchdog: pip install watchdog (%s)", e)
        sys.exit(1)

    inbox.mkdir(parents=True, exist_ok=True)
    library_root.mkdir(parents=True, exist_ok=True)
    for sub in _CATEGORIES.keys():
        (library_root / sub).mkdir(parents=True, exist_ok=True)
    (library_root / "Other").mkdir(parents=True, exist_ok=True)
    if media_only and reject_dir:
        reject_dir.mkdir(parents=True, exist_ok=True)

    deb = _DebouncedOrganizer(
        inbox,
        library_root,
        log_path,
        debounce_s,
        stable_wait_s,
        media_only=media_only,
        reject_dir=reject_dir,
    )

    class Handler(FileSystemEventHandler):
        def on_created(self, event):  # type: ignore[override]
            if event.is_directory:
                return
            deb.schedule(Path(event.src_path))

        def on_moved(self, event):  # type: ignore[override]
            if event.is_directory:
                return
            deb.schedule(Path(event.dest_path))

    observer = Observer()
    observer.schedule(Handler(), str(inbox), recursive=False)
    observer.start()
    logger.info(
        "TBCC watch organizer: inbox=%s library=%s debounce=%ss stable_wait=%ss overrides=%s media_only=%s reject_dir=%s aof_lanes=%s aof_preprocess=%s nsfw_tier=%s nsfw_class=%s clip_niche=%s vision_llm=%s",
        inbox,
        library_root,
        debounce_s,
        stable_wait_s,
        len(_CATEGORY_OVERRIDES),
        media_only,
        str(reject_dir) if reject_dir else "-",
        _is_truthy_env(os.environ.get("TBCC_WATCH_AOF_LANE_FOLDERS"))
        if (os.environ.get("TBCC_WATCH_AOF_LANE_FOLDERS") or "").strip()
        else True,
        _is_truthy_env(os.environ.get("TBCC_WATCH_AOF_PREPROCESS"))
        if (os.environ.get("TBCC_WATCH_AOF_PREPROCESS") or "").strip()
        else True,
        _is_truthy_env(os.environ.get("TBCC_WATCH_NSFW_TIER_SUBFOLDERS")),
        _is_truthy_env(os.environ.get("TBCC_WATCH_NSFW_CLASS_SUBFOLDERS")),
        bool((os.environ.get("TBCC_CLIP_CATEGORIZE_URL") or "").strip()),
        (os.environ.get("TBCC_VISION_LLM_PROVIDER") or os.environ.get("TBCC_WATCH_LLM_TAG") or "").strip() or "-",
    )
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Stopping observer…")
    finally:
        observer.stop()
        observer.join(timeout=5.0)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    p = argparse.ArgumentParser(description="TBCC inbox → library file organizer")
    p.add_argument("--once", action="store_true", help="Scan inbox once and exit")
    p.add_argument("--dry-run", action="store_true", help="Log moves only (no --once moves)")
    args = p.parse_args(argv)

    inbox = _env_path("TBCC_WATCH_INBOX")
    if not inbox:
        logger.error("Set TBCC_WATCH_INBOX in tbcc/.env to an absolute folder path (e.g. D:/Downloads/tbcc/inbox).")
        return 2

    default_lib = inbox.parent / "tbcc_library"
    library = _env_path("TBCC_WATCH_LIBRARY", str(default_lib))
    if not library:
        library = default_lib

    debounce = float(os.environ.get("TBCC_WATCH_DEBOUNCE_S") or "1.5")
    stable_wait_s = max(0.0, float(os.environ.get("TBCC_WATCH_STABLE_WAIT_S") or "2.0"))
    media_only = _is_truthy_env(os.environ.get("TBCC_WATCH_MEDIA_ONLY"))
    reject_dir_raw = (os.environ.get("TBCC_WATCH_REJECT_DIR") or "").strip()
    reject_dir = Path(reject_dir_raw).expanduser().resolve() if reject_dir_raw else None
    log_path_raw = (os.environ.get("TBCC_WATCH_LOG") or "").strip()
    log_path = Path(log_path_raw).expanduser() if log_path_raw else None
    global _CATEGORY_OVERRIDES
    _CATEGORY_OVERRIDES = _parse_category_overrides((os.environ.get("TBCC_WATCH_CATEGORY_OVERRIDES") or "").strip())

    if args.once:
        n = scan_inbox_once(
            inbox,
            library,
            log_path,
            stable_wait_s=stable_wait_s,
            media_only=media_only,
            reject_dir=reject_dir,
            dry_run=args.dry_run,
        )
        logger.info("Scan complete: organized %s file(s)", n)
        return 0

    if args.dry_run:
        logger.error("--dry-run is only supported with --once")
        return 2

    run_watch_loop(
        inbox,
        library,
        log_path,
        debounce,
        stable_wait_s=stable_wait_s,
        media_only=media_only,
        reject_dir=reject_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
