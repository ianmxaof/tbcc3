#!/usr/bin/env python3
"""
Apply manual Post & earn Linkvertise slugs across TBCC DB + all schedulers.

  cd tbcc/backend
  py -3.13 scripts/apply_manual_lv_gates.py              # preview
  py -3.13 scripts/apply_manual_lv_gates.py --execute
  py -3.13 scripts/apply_manual_lv_gates.py --execute --post-bulletin
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_manual_gate_links import (
    LOOT_MODIFIER_LABEL_TO_GATE_KEY,
    manual_gate_url,
    manual_gate_urls,
)
from app.database.session import SessionLocal
from app.models.loot import LootModifier
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_gate_text_replace import replace_stale_gates_in_buttons, replace_stale_gates_in_text
from app.services.aof_growth_hub import sync_network_schedulers


def _sync_loot_modifiers(db, *, execute: bool) -> dict:
    stats = {"updated": 0, "rows": []}
    gates = manual_gate_urls()
    for row in db.query(LootModifier).filter(LootModifier.active.is_(True)).all():
        label = (row.label or "").strip()
        key = LOOT_MODIFIER_LABEL_TO_GATE_KEY.get(label)
        if not key:
            continue
        url = manual_gate_url(key) or gates.get(key)
        if not url:
            continue
        cur = (row.target_url or "").strip().split()[0]
        if cur == url:
            continue
        stats["rows"].append({"id": row.id, "label": label, "key": key, "from": cur, "to": url})
        if execute:
            row.target_url = url
            stats["updated"] += 1
    return stats


def _sweep_scheduled_posts(db, *, execute: bool) -> dict:
    gates = manual_gate_urls()
    stats = {"rows": 0, "updated": 0, "field_changes": 0}
    for row in db.query(ScheduledTextPost).all():
        stats["rows"] += 1
        changed = False
        content = row.content or ""
        new_content, n1 = replace_stale_gates_in_text(content, gates)
        if n1:
            changed = True
            stats["field_changes"] += n1

        new_vars = row.content_variations
        if row.content_variations:
            try:
                vars_list = json.loads(row.content_variations)
                if isinstance(vars_list, list):
                    out_vars = []
                    for v in vars_list:
                        if isinstance(v, str):
                            w, n = replace_stale_gates_in_text(v, gates)
                            if n:
                                changed = True
                                stats["field_changes"] += n
                            out_vars.append(w)
                        else:
                            out_vars.append(v)
                    if changed:
                        new_vars = json.dumps(out_vars)
            except json.JSONDecodeError:
                pass

        new_buttons = row.buttons
        if row.buttons:
            nb, n3 = replace_stale_gates_in_buttons(row.buttons, gates)
            if n3:
                changed = True
                stats["field_changes"] += n3
                new_buttons = nb

        if execute and changed:
            row.content = new_content
            row.content_variations = new_vars
            row.buttons = new_buttons
            stats["updated"] += 1
    return stats


def apply(*, execute: bool, post_bulletin: bool, post_sync: bool) -> dict:
    from scripts.apply_growth_launch import apply as growth_apply

    report: dict = {"gates": manual_gate_urls()}
    db = SessionLocal()
    try:
        report["loot_modifiers"] = _sync_loot_modifiers(db, execute=execute)
        if execute:
            db.commit()
        else:
            db.rollback()

        report["network_schedulers"] = sync_network_schedulers(db, execute=execute)
        if execute:
            db.commit()

        report["scheduled_sweep"] = _sweep_scheduled_posts(db, execute=execute)
        if execute:
            db.commit()
    finally:
        db.close()

    report["growth_launch"] = growth_apply(
        execute=execute,
        post_bulletin=post_bulletin,
        post_commands=False,
        post_sync=post_sync,
        bulletin_only=False,
    )

    if execute:
        # PACKS footer + captions (manual gates on footers; pack URLs from modifiers).
        from scripts.wire_aof_packs_direct_import import main as wire_packs

        try:
            wire_packs()
            report["packs_wire"] = "ok"
        except SystemExit as e:
            report["packs_wire"] = f"skipped: {e}"

    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Apply manual Linkvertise gates to all schedulers")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--post-bulletin", action="store_true")
    p.add_argument("--post-sync", action="store_true")
    args = p.parse_args()
    r = apply(execute=args.execute, post_bulletin=args.post_bulletin, post_sync=args.post_sync)
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
