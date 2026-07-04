#!/usr/bin/env python3
"""
Clipboard (or --url) Mega link → AdMaven gate wrap → AOF pack / loot pool.

Usage:
  cd tbcc/backend
  py -3.13 scripts/clip_mega_to_pack_pool.py              # dry-run from clipboard
  py -3.13 scripts/clip_mega_to_pack_pool.py --execute    # queue modifier + wire scheduler
  py -3.13 scripts/clip_mega_to_pack_pool.py --execute --label "Pack Name"
  py -3.13 scripts/clip_mega_to_pack_pool.py --url "https://mega.nz/folder/..." --execute

Copy a Mega folder/file link, run with --execute; gate URL is copied back to clipboard.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.loot_pack_pool import queue_url_to_pack_pool, refresh_aof_packs_scheduler
from app.services.mega_link_pipeline import resolve_to_file_host
from scripts.import_mega_folders_to_pack_pool import _parse_line


def _read_clipboard() -> str:
    if platform.system() == "Windows":
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                check=False,
            )
            if proc.returncode == 0 and (proc.stdout or "").strip():
                return proc.stdout
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            return root.clipboard_get() or ""
        finally:
            root.destroy()
    except Exception:
        return ""


def _write_clipboard(text: str) -> bool:
    payload = (text or "").strip()
    if not payload:
        return False
    if platform.system() == "Windows":
        try:
            ps = f"Set-Clipboard -Value {json.dumps(payload)}"
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            return proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            root.clipboard_clear()
            root.clipboard_append(payload)
            root.update()
            return True
        finally:
            root.destroy()
    except Exception:
        return False


def _append_export(path: Path, label: str | None, url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{label} | {url}" if label else url
    existing = path.read_text(encoding="utf-8", errors="replace").rstrip("\n") if path.is_file() else ""
    body = (existing + "\n" if existing else "") + line + "\n"
    path.write_text(body, encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    default_export = _backend.parent / "docs" / "samples" / "mega_pack_folders.txt"
    p = argparse.ArgumentParser(description="Clipboard Mega URL → gate wrap → pack pool")
    p.add_argument("--url", default="", help="Mega URL (default: read system clipboard)")
    p.add_argument("--label", default="", help="Loot modifier label (optional)")
    p.add_argument("--execute", action="store_true", help="Insert loot_modifiers row")
    p.add_argument("--wire-scheduler", action="store_true", help="Refresh AOF PACKS scheduler after create")
    p.add_argument("--no-wire-scheduler", action="store_true", help="Skip scheduler refresh")
    p.add_argument("--source-note", default="mega_clipboard", help="loot_modifiers.source_note prefix")
    p.add_argument(
        "--append-export",
        action="store_true",
        help=f"Append label | url to {default_export.name}",
    )
    p.add_argument("--export-file", type=Path, default=default_export, help="Export list path")
    p.add_argument("--no-copy-gate", action="store_true", help="Do not copy gate URL to clipboard")
    args = p.parse_args()

    raw = (args.url or "").strip() or _read_clipboard().strip()
    if not raw:
        print("No Mega URL in --url or clipboard.", file=sys.stderr)
        raise SystemExit(1)

    parsed = _parse_line(raw)
    if not parsed:
        print("Clipboard does not contain a Mega folder/file URL.", file=sys.stderr)
        print(f"Got: {raw[:120]!r}", file=sys.stderr)
        raise SystemExit(1)

    label_arg = (args.label or "").strip() or None
    label, url = parsed
    if label_arg:
        label = label_arg

    preview = resolve_to_file_host(url)
    if not preview.ok:
        print(f"RESOLVE FAIL: {preview.error}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Mega   {url[:100]}")
    print(f"Dest   {(preview.destination_url or '')[:100]}")
    print(f"Tier   {preview.min_rarity_tier}  size_gb≈{preview.size_gb_hint}")
    if label:
        print(f"Label  {label}")

    if not args.execute:
        print("\nDRY-RUN — pass --execute to gate-wrap and queue (pool + optional scheduler).")
        return

    db = SessionLocal()
    try:
        result = queue_url_to_pack_pool(
            db,
            url,
            label=label,
            source_note=args.source_note,
        )
    finally:
        db.close()

    if not result.get("ok"):
        print(f"QUEUE FAIL: {result.get('error')}", file=sys.stderr)
        raise SystemExit(1)

    gate = str(result.get("target_url") or "")
    if result.get("duplicate"):
        print(f"DUP  already in pool")
        print(f"Gate {gate[:100]}")
    else:
        mod = result.get("modifier") or {}
        print(f"OK   id={mod.get('id')} tier={mod.get('min_rarity_tier')}")
        print(f"     {mod.get('label', '')[:60]}")
        print(f"Gate {gate[:100]}")

        wire = args.wire_scheduler and not args.no_wire_scheduler
        if wire:
            db = SessionLocal()
            try:
                sched = refresh_aof_packs_scheduler(db)
                if sched.get("ok"):
                    print(f"SCHEDULER ok modifiers={sched.get('modifier_count')}")
                else:
                    print(f"SCHEDULER skip: {sched.get('error')}", file=sys.stderr)
            finally:
                db.close()

    if args.append_export:
        _append_export(args.export_file, label, url)
        print(f"EXPORT appended → {args.export_file}")

    if gate and not args.no_copy_gate:
        if _write_clipboard(gate):
            print("CLIP gate URL copied to clipboard")
        else:
            print("WARN could not copy gate URL to clipboard", file=sys.stderr)


if __name__ == "__main__":
    main()
