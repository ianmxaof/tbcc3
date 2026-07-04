#!/usr/bin/env python3
"""
Split a messy paste → Mega pack pool vs Bunkr loot modifiers.

Mega folder URLs → queue_url_to_pack_pool (AOF packs scheduler).
Bunkr /v/ /f/ file URLs → gate-wrapped loot_modifiers (loot rolls, not pack scheduler).
Bunkr /a/ albums → skipped list (gallery not wired to pool yet).

Usage:
  py -3.13 scripts/queue_paste_split.py paste.txt
  py -3.13 scripts/queue_paste_split.py paste.txt --execute --wire-scheduler
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.loot_pack_pool import queue_url_to_pack_pool, refresh_aof_packs_scheduler
from app.services.mega_link_extract import classify_url_host, extract_urls_from_text
from app.services.linkvertise_wrap import _URL_IN_TEXT_RE

_MEGA_FOLDER_RE = re.compile(
    r"https?://(?:mega\.nz|mega\.co\.nz)/folder/[^\s\]\)<>\"']+",
    re.IGNORECASE,
)
_BUNKR_RE = re.compile(r"https?://[^\s\]\)<>\"']+", re.IGNORECASE)


def _is_mega_folder(url: str) -> bool:
    return bool(_MEGA_FOLDER_RE.match((url or "").strip()))


def _is_bunkr(url: str) -> bool:
    low = (url or "").lower()
    return "bunkr" in low or "bunkrr" in low


def _is_bunkr_file(url: str) -> bool:
    if not _is_bunkr(url):
        return False
    low = url.lower()
    return "/v/" in low or "/f/" in low


def _is_bunkr_album(url: str) -> bool:
    if not _is_bunkr(url):
        return False
    return "/a/" in url.lower()


def _labels_from_lines(text: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for line in (text or "").splitlines():
        for m in _URL_IN_TEXT_RE.finditer(line):
            url = m.group(0).rstrip(".,;)]")
            tail = line[m.end() :].strip()
            if tail.startswith("-"):
                name = tail[1:].strip().strip(")]")
                if name and len(name) < 120:
                    labels[url] = name
    return labels


def _normalize_mega_folder(url: str) -> str:
    """Drop nested /folder/child paths — keep root public folder link."""
    u = (url or "").strip()
    m = re.match(r"(https?://(?:mega\.nz|mega\.co\.nz)/folder/[^/\s#]+#[^\s/]+)", u, re.I)
    if m:
        return m.group(1)
    return u.split("/folder/", 1)[0] if "/folder/" in u else u


def split_paste(text: str) -> tuple[list[tuple[str, str | None]], list[tuple[str, str | None]], list[str]]:
    labels = _labels_from_lines(text)
    mega_seen: set[str] = set()
    bunkr_seen: set[str] = set()
    megas: list[tuple[str, str | None]] = []
    bunkrs: list[tuple[str, str | None]] = []
    albums: list[str] = []

    for entry in extract_urls_from_text(text):
        url = entry.url
        if _is_mega_folder(url):
            norm = _normalize_mega_folder(url)
            if norm in mega_seen:
                continue
            mega_seen.add(norm)
            megas.append((norm, labels.get(url) or labels.get(norm)))
            continue
        if _is_bunkr_album(url):
            if url not in albums:
                albums.append(url)
            continue
        if _is_bunkr_file(url):
            if url in bunkr_seen:
                continue
            bunkr_seen.add(url)
            bunkrs.append((url, labels.get(url)))
            continue
    return megas, bunkrs, albums


def _write_lines(path: Path, rows: list[tuple[str, str | None]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for url, label in rows:
        lines.append(f"{label} | {url}" if label else url)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Paste → Mega packs + Bunkr modifiers")
    p.add_argument("file", type=Path, help="Paste text file")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--wire-scheduler", action="store_true", help="Refresh AOF PACKS after Mega queue")
    p.add_argument("--out-dir", type=Path, default=_backend.parent / "docs" / "samples")
    args = p.parse_args()

    if not args.file.is_file():
        print(f"Not found: {args.file}", file=sys.stderr)
        raise SystemExit(1)

    text = args.file.read_text(encoding="utf-8", errors="replace")
    megas, bunkrs, albums = split_paste(text)

    out_dir = args.out_dir
    mega_file = out_dir / "user_paste_mega_packs.txt"
    bunkr_file = out_dir / "user_paste_bunkr_modifiers.txt"
    album_file = out_dir / "user_paste_bunkr_albums_skipped.txt"
    _write_lines(mega_file, megas)
    _write_lines(bunkr_file, bunkrs)
    album_file.write_text("\n".join(albums) + ("\n" if albums else ""), encoding="utf-8")

    print(f"Mega packs:     {len(megas)} → {mega_file}")
    print(f"Bunkr files:    {len(bunkrs)} → {bunkr_file}")
    print(f"Bunkr albums:   {len(albums)} skipped → {album_file}")

    if not args.execute:
        print("\nDRY-RUN — pass --execute to queue")
        return

    db = SessionLocal()
    m_ok = m_dup = m_fail = b_ok = b_dup = b_fail = 0
    try:
        for url, label in megas:
            result = queue_url_to_pack_pool(
                db,
                url,
                label=label,
                source_note="mega_paste_batch",
            )
            if not result.get("ok"):
                m_fail += 1
                print(f"MEGA FAIL {url[:70]} — {result.get('error')}")
                continue
            if result.get("duplicate"):
                m_dup += 1
                print(f"MEGA DUP  {(label or url)[:50]}")
                continue
            m_ok += 1
            mod = result.get("modifier") or {}
            print(f"MEGA OK   id={mod.get('id')} tier={mod.get('min_rarity_tier')} {(mod.get('label') or '')[:45]}")

        for url, label in bunkrs:
            result = queue_url_to_pack_pool(
                db,
                url,
                label=(label or Path(url).name or "Bunkr")[:256],
                source_note="bunkr_modifier_batch",
            )
            if not result.get("ok"):
                b_fail += 1
                print(f"BUNKR FAIL {url[:70]} — {result.get('error')}")
                continue
            if result.get("duplicate"):
                b_dup += 1
                continue
            b_ok += 1
            mod = result.get("modifier") or {}
            print(f"BUNKR OK  id={mod.get('id')} {(mod.get('label') or '')[:50]}")

        if args.wire_scheduler and m_ok > 0:
            sched = refresh_aof_packs_scheduler(db)
            print(f"SCHEDULER ok={sched.get('ok')} modifiers={sched.get('modifier_count')}")
    finally:
        db.close()

    print(
        f"\n--- execute: mega ok={m_ok} dup={m_dup} fail={m_fail} | "
        f"bunkr ok={b_ok} dup={b_dup} fail={b_fail}"
    )


if __name__ == "__main__":
    main()
