#!/usr/bin/env python3
"""Import docs/samples/buffer_x_copy/*.json into social_copy_templates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.social_copy_template import SocialCopyTemplate

DEFAULT_DIR = BACKEND / "app" / "data" / "buffer_x_copy"
FALLBACK_DIR = BACKEND.parent / "docs" / "samples" / "buffer_x_copy"


def _load_json_files(import_dir: Path) -> list[dict]:
    items: list[dict] = []
    for path in sorted(import_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        templates = data.get("templates") if isinstance(data, dict) else data
        if not isinstance(templates, list):
            continue
        for tpl in templates:
            if isinstance(tpl, dict) and (tpl.get("body") or "").strip():
                items.append(tpl)
    lanes = import_dir / "lanes"
    if lanes.is_dir():
        for path in sorted(lanes.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            templates = data.get("templates") if isinstance(data, dict) else data
            if not isinstance(templates, list):
                continue
            for tpl in templates:
                if isinstance(tpl, dict) and (tpl.get("body") or "").strip():
                    items.append(tpl)
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed social_copy_templates from JSON catalogs")
    parser.add_argument("--import-dir", type=Path, default=None)
    parser.add_argument("--execute", action="store_true", help="Write to DB (default dry-run)")
    parser.add_argument("--replace-category", action="store_true", help="Delete existing rows per category before import")
    args = parser.parse_args()

    import_dir = args.import_dir
    if import_dir is None:
        import_dir = DEFAULT_DIR if DEFAULT_DIR.is_dir() else FALLBACK_DIR

    items = _load_json_files(import_dir)
    if not items:
        print(json.dumps({"ok": False, "error": "no_templates", "dir": str(import_dir)}))
        return 1

    report: dict = {"ok": True, "execute": args.execute, "imported": 0, "skipped": 0, "categories": {}}
    db = SessionLocal()
    try:
        sort_counters: dict[tuple[str, str], int] = {}
        for tpl in items:
            body = (tpl.get("body") or "").strip()
            category = (tpl.get("category") or "network").strip().lower()
            surface = (tpl.get("surface") or "x_buffer").strip().lower()
            key = (category, surface)
            if args.replace_category and key not in sort_counters:
                db.query(SocialCopyTemplate).filter(
                    SocialCopyTemplate.category == category,
                    SocialCopyTemplate.surface == surface,
                ).delete(synchronize_session=False)
                sort_counters[key] = 0

            exists = (
                db.query(SocialCopyTemplate)
                .filter(
                    SocialCopyTemplate.category == category,
                    SocialCopyTemplate.surface == surface,
                    SocialCopyTemplate.body == body,
                )
                .first()
            )
            if exists:
                report["skipped"] += 1
                continue

            order = sort_counters.get(key, 0)
            sort_counters[key] = order + 1
            row = SocialCopyTemplate(
                category=category,
                surface=surface,
                body=body,
                image_hint=(tpl.get("image_hint") or None),
                max_uses_before_demote=int(tpl.get("max_uses_before_demote") or 2),
                sort_order=order,
                is_active=True,
            )
            if args.execute:
                db.add(row)
            report["imported"] += 1
            report["categories"][category] = report["categories"].get(category, 0) + 1

        if args.execute:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(report, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
