"""Watchdog daemon: local AOF lane folders → Storage Hub forum topic uploads."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.services.local_lane_hub_deposit import (
    deposit_local_file,
    local_lane_hub_enabled,
    local_lane_hub_log_path,
)
from app.services.local_lane_hub_map import lane_watch_targets

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[3] / ".env"
        if root.is_file():
            load_dotenv(root, override=True)
    except Exception:
        pass


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class _DebouncedUploader:
    def __init__(self, debounce_s: float, stable_wait_s: float):
        self.debounce_s = debounce_s
        self.stable_wait_s = stable_wait_s
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(self, path: Path) -> None:
        try:
            path = path.resolve()
        except OSError:
            return
        key = str(path)

        def run() -> None:
            with self._lock:
                self._timers.pop(key, None)
            if not path.is_file():
                return
            ok, msg, _ = deposit_local_file(path, stable_wait_s=self.stable_wait_s)
            if ok:
                logger.info("%s: %s", path.name, msg)
            elif msg not in ("already uploaded", "sidecar", "non_media", "incomplete download", "file still changing"):
                logger.debug("skip %s: %s", path.name, msg)

        with self._lock:
            old = self._timers.pop(key, None)
            if old:
                old.cancel()
            timer = threading.Timer(self.debounce_s, run)
            timer.daemon = True
            self._timers[key] = timer
            timer.start()


def run_daemon() -> int:
    _load_dotenv()
    if not local_lane_hub_enabled():
        logger.error("TBCC_LOCAL_LANE_HUB_ENABLED=0 — worker refused to start.")
        return 2

    targets = lane_watch_targets()
    if not targets:
        logger.error("No lane watch targets — check TBCC_WATCH_LIBRARY and aof_storage_hub_map.")
        return 2

    debounce_s = max(0.5, _env_float("TBCC_LOCAL_LANE_HUB_DEBOUNCE_S", 2.0))
    stable_wait_s = max(0.0, _env_float("TBCC_LOCAL_LANE_HUB_STABLE_WAIT_S", 2.0))
    from app.services.watch_folder_aof import watch_aof_fast_mode

    if watch_aof_fast_mode():
        debounce_s = min(debounce_s, 0.5)
        stable_wait_s = min(stable_wait_s, 0.5)
    uploader = _DebouncedUploader(debounce_s, stable_wait_s)

    class Handler(FileSystemEventHandler):
        def on_created(self, event):  # type: ignore[override]
            if event.is_directory:
                return
            uploader.schedule(Path(event.src_path))

        def on_moved(self, event):  # type: ignore[override]
            if event.is_directory:
                return
            uploader.schedule(Path(event.dest_path))

    observer = Observer()
    for target in targets:
        folder = target.folder_path
        if not folder.is_dir():
            logger.warning("lane folder missing (skipping watch): %s", folder)
            continue
        observer.schedule(Handler(), str(folder), recursive=True)
        logger.info(
            "watching lane %s -> topic %s (%s)",
            folder,
            target.message_thread_id,
            target.topic_title,
        )

    log_path = local_lane_hub_log_path()
    observer.start()
    logger.info(
        "TBCC local lane hub worker started debounce=%ss stable_wait=%ss log=%s lanes=%s",
        debounce_s,
        stable_wait_s,
        log_path,
        [t.network_key for t in targets],
    )

    def _startup_scan() -> None:
        from app.services.local_lane_hub_deposit import scan_lane_folders_once

        try:
            report = scan_lane_folders_once(stable_wait_s=stable_wait_s, dry_run=False)
            logger.info(
                "startup scan uploaded=%s skipped=%s errors=%s",
                report.get("uploaded"),
                report.get("skipped"),
                report.get("errors"),
            )
        except Exception:
            logger.exception("startup lane scan failed")

    if not os.environ.get("TBCC_LOCAL_LANE_HUB_SKIP_STARTUP_SCAN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        threading.Thread(target=_startup_scan, name="lane-hub-startup-scan", daemon=True).start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Stopping observer…")
    finally:
        observer.stop()
        observer.join(timeout=5.0)
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    p = argparse.ArgumentParser(description="Local AOF lane folders → Storage Hub topic uploader")
    p.add_argument("--once", action="store_true", help="Scan lane folders once and exit")
    p.add_argument("--dry-run", action="store_true", help="Log uploads only (no Telegram I/O)")
    args = p.parse_args(argv)

    if args.once:
        from app.services.local_lane_hub_deposit import scan_lane_folders_once

        stable_wait_s = max(0.0, _env_float("TBCC_LOCAL_LANE_HUB_STABLE_WAIT_S", 2.0))
        from app.services.watch_folder_aof import watch_aof_fast_mode

        if watch_aof_fast_mode():
            stable_wait_s = min(stable_wait_s, 0.5)
        report = scan_lane_folders_once(stable_wait_s=stable_wait_s, dry_run=args.dry_run)
        logger.info(
            "scan complete uploaded=%s skipped=%s errors=%s dry_run=%s",
            report.get("uploaded"),
            report.get("skipped"),
            report.get("errors"),
            report.get("dry_run"),
        )
        return 0 if report.get("ok", True) else 1

    return run_daemon()


if __name__ == "__main__":
    sys.exit(main())
