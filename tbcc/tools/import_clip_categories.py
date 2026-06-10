#!/usr/bin/env python3
"""
Normalize a niche category list into TBCC CLIP catalog JSON.

Usage:
  cd tbcc
  python tools/import_clip_categories.py --in C:/path/categories.txt --out data/clip-categories.json
  python tools/import_clip_categories.py --in topics.json --out data/clip-categories.json --sync-tags

Input formats:
  - Plain text: one label per line (# comments allowed)
  - JSON array of strings or {slug,name,group,prompts} objects
  - JSON object (OrganizerBot TOPICS.JSON style): {"MILF": "MILF", ...}
  - OrganizerGM config.json with category_settings.categories array
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _slugify(raw: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", (raw or "").strip().lower()).strip("-")
    return (s[:64] or "other") if s else "other"


def load_entries(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig").strip()
    out: list[dict] = []

    def add_label(label: str, *, group: str | None = None) -> None:
        label = label.strip()
        if not label:
            return
        slug = _slugify(label)
        out.append({"slug": slug, "name": label, "prompts": [label], "group": group})

    if raw.startswith("[") or raw.startswith("{"):
        data = json.loads(raw)
        if isinstance(data, dict):
            if isinstance(data.get("categories"), list):
                data = data["categories"]
            elif isinstance(data.get("category_settings"), dict) and isinstance(
                data["category_settings"].get("categories"), list
            ):
                data = data["category_settings"]["categories"]
            else:
                for k, v in data.items():
                    add_label(str(v or k))
                data = None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    add_label(item)
                elif isinstance(item, dict):
                    slug = _slugify(str(item.get("slug") or item.get("name") or ""))
                    name = str(item.get("name") or slug).strip()
                    prompts = item.get("prompts")
                    if not isinstance(prompts, list) or not prompts:
                        prompts = [name]
                    group = str(item.get("group") or item.get("category") or "").strip() or None
                    out.append(
                        {
                            "slug": slug,
                            "name": name,
                            "prompts": [str(p).strip() for p in prompts if str(p).strip()],
                            "group": group,
                        }
                    )
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Markdown numbered lists: "1. Just Boobs" or "123. Label"
            m = re.match(r"^\d+\.\s+(.+)$", line)
            if m:
                line = m.group(1).strip()
            label = line.split("|")[0].split(",")[0].strip()
            # Skip prose headers and stray page numbers
            if not label or re.fullmatch(r"\d+", label):
                continue
            if label.lower().startswith("here is the complete") or "**" in label[:20]:
                continue
            add_label(label)

    seen: set[str] = set()
    deduped: list[dict] = []
    for e in out:
        if e["slug"] in seen:
            continue
        seen.add(e["slug"])
        deduped.append(e)
    return deduped


def sync_tbcc_tags(entries: list[dict]) -> int:
    tbcc_root = Path(__file__).resolve().parents[1]
    try:
        from dotenv import load_dotenv

        load_dotenv(tbcc_root / ".env", override=True)
    except Exception:
        pass
    sys.path.insert(0, str(tbcc_root / "backend"))
    from app.database.session import SessionLocal
    from app.services.media_tagging import ensure_tag

    db = SessionLocal()
    n = 0
    try:
        for e in entries:
            ensure_tag(db, e["slug"], e["name"], "topic")
            n += 1
        db.commit()
    finally:
        db.close()
    return n


def main() -> int:
    p = argparse.ArgumentParser(description="Import niche categories for TBCC CLIP sidecar")
    p.add_argument("--in", dest="inp", required=True, help="Source categories file")
    p.add_argument("--out", required=True, help="Output clip-categories.json path")
    p.add_argument("--sync-tags", action="store_true", help="Also upsert slugs into tbcc_tags (topic)")
    args = p.parse_args()

    src = Path(args.inp).expanduser().resolve()
    dst = Path(args.out).expanduser().resolve()
    if not src.is_file():
        print(f"Input not found: {src}", file=sys.stderr)
        return 2

    entries = load_entries(src)
    if not entries:
        print("No categories parsed.", file=sys.stderr)
        return 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    payload = {"categories": entries, "count": len(entries), "source": str(src)}
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(entries)} categories -> {dst}")

    if args.sync_tags:
        synced = sync_tbcc_tags(entries)
        print(f"Synced {synced} tags to tbcc_tags")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
