#!/usr/bin/env python3
"""Export prompt campaign manifests from catalog JSON (v2 schema).

Writes:
  docs/samples/prompt_campaigns/LV_MANUAL_MANIFEST.md
  docs/samples/prompt_campaigns/SOCIAL_ROLLOUT.md

Usage (from tbcc/backend):
  py -3.13 scripts/export_prompt_gate_lv_manifest.py
  py -3.13 scripts/export_prompt_gate_lv_manifest.py --write-catalog-urls path/to/lv_urls.json
  py -3.13 scripts/export_prompt_gate_lv_manifest.py --include-tts
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

PROMPT_DROP_MARKER = "AOF PROMPT DROP"
DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"
OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "samples" / "prompt_campaigns"
LV_PATH = OUT_DIR / "LV_MANUAL_MANIFEST.md"
ROLLOUT_PATH = OUT_DIR / "SOCIAL_ROLLOUT.md"

DISPLAY_TITLES: dict[str, str] = {
    "he_coming_discovery": "He's Coming: The Discovery",
    "he_coming_session_logs": "He's Coming: Session Logs",
    "he_coming_window_feed": "He's Coming: Window Feed",
    "he_coming_closet_feed": "He's Coming: Closet Feed",
    "he_coming_backseat": "He's Coming: Backseat",
    "he_coming_filmstrip_5x": "He's Coming: Filmstrip 5×",
    "jackal_tapes_interview": "Jackal Tapes: The Interview",
    "jackal_tapes_break_the_man": "Jackal Tapes: Break the Man",
    "jackal_tapes_war_is_home": "Jackal Tapes: War Is Home",
    "jackal_tapes_mikes_bar": "Jackal Tapes: Mike's Bar",
    "jackal_tapes_monster_display": "Jackal Tapes: The Display",
    "jackal_tapes_filmstrip_5x": "Jackal Tapes: Filmstrip 5×",
    "spicy_reveal_01_trial_photo": "Spicy Reveal: Trial Photo",
    "spicy_reveal_02_chat_persona": "Spicy Reveal: Chat Persona",
    "spicy_reveal_03_referral_earn": "Spicy Reveal: Referral Earn",
    "spicy_reveal_04_scene_builder": "Spicy Reveal: Scene Builder",
    "spicy_reveal_05_full_bundle": "Spicy Reveal: Full 5-Pack",
}


def lv_title_for_key(key: str) -> str:
    return f"AOF Prompt {key.replace('_', ' ').title()} Card Lab Access"


def publisher_slug_base() -> str:
    pub = (os.getenv("TBCC_LINKVERTISE_PUBLISHER_ID") or os.getenv("LINKVERTISE_PUBLISHER_ID") or "1367336").strip()
    return f"https://link-target.net/{pub}/"


def placeholder_url(slug: str = "PASTE_SLUG_HERE") -> str:
    return f"{publisher_slug_base()}{slug}"


def _engagement(item: dict) -> dict[str, Any]:
    raw = item.get("engagement")
    return raw if isinstance(raw, dict) else {}


def display_title(key: str) -> str:
    return DISPLAY_TITLES.get(key, key.replace("_", " ").title())


def telegram_teaser(item: dict) -> str:
    eng = _engagement(item)
    if eng.get("telegram_teaser"):
        return str(eng["telegram_teaser"])
    return "Unlock the full Gemini image prompt behind one ad gate."


def telegram_html(gate_url: str, item: dict) -> str:
    key = str(item.get("key") or "")
    tier = str(item.get("tier") or "promo")
    title = display_title(key)
    teaser = telegram_teaser(item)
    head = f"🎴 <b>{PROMPT_DROP_MARKER}</b> — {html.escape(title)}"
    if tier:
        head += f" <i>({html.escape(tier)})</i>"
    gate_link = f'<a href="{html.escape(gate_url, quote=True)}">Unlock prompt</a>'
    return f"{head}\n\n{teaser}\n\n{gate_link}"


def x_post_plain(item: dict) -> str:
    eng = _engagement(item)
    x_copy = eng.get("x_copy") if isinstance(eng.get("x_copy"), dict) else {}
    hook = str(x_copy.get("hook") or eng.get("quote_hook") or "").strip()
    body = str(x_copy.get("body") or "").strip()
    cta = str(x_copy.get("cta") or "@aofmainhub").strip()
    parts = []
    if hook:
        parts.append(hook)
    if body:
        parts.append(body)
    if cta:
        parts.append(cta)
    return "\n\n".join(parts)


def load_catalogs() -> tuple[list[dict], list[dict]]:
    """Returns (flat rows for LV, campaign bundles for rollout)."""
    rows: list[dict] = []
    campaigns: list[dict] = []
    for path in sorted(DATA_DIR.glob("prompt_gate_catalog_*.json")):
        if path.name.endswith(".sample.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        campaign = str(data.get("campaign") or path.stem.replace("prompt_gate_catalog_", ""))
        bundle = {
            "campaign": campaign,
            "schema_version": data.get("schema_version"),
            "style_anchors": data.get("style_anchors"),
            "negative_prompt": data.get("negative_prompt"),
            "engagement": data.get("engagement") if isinstance(data.get("engagement"), dict) else {},
            "items": [],
        }
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            body = str(item.get("prompt_body") or "").strip()
            if not key or not body:
                continue
            row = {
                "campaign": campaign,
                "key": key,
                "tier": str(item.get("tier") or "promo"),
                "prompt_ref": str(item.get("prompt_ref") or ""),
                "prompt_body": body,
                "lv_title": lv_title_for_key(key),
                "engagement": _engagement(item),
                "item": item,
            }
            rows.append(row)
            bundle["items"].append(item)
        if bundle["items"]:
            campaigns.append(bundle)
    return rows, campaigns


def render_lv_manifest(rows: list[dict], urls: dict[str, str] | None = None) -> str:
    urls = urls or {}
    lines = [
        "# Prompt campaigns — LV manual manifest",
        "",
        "Auto-generated from `backend/app/data/prompt_gate_catalog_*.json` (schema v2).",
        "Engagement + X copy: `SOCIAL_ROLLOUT.md` · Doctrine: `ENGAGEMENT_DOCTRINE.md`",
        "",
        "## Manual workflow (Linkvertise)",
        "",
        "1. [Linkvertise Post & earn](https://linkvertise.com/) → **Create** → **Text** asset.",
        "2. Paste **LV title** and **LV Text body** below.",
        "3. Publish → copy slug URL into `lv_urls.json` → re-export with `--write-catalog-urls`.",
        "4. Paste **Telegram HTML** into scheduler — **no channel addlist footer** on prompt drops.",
        "",
        f"Publisher base: `{publisher_slug_base()}`",
        "",
        "---",
        "",
    ]
    current_campaign = ""
    for row in rows:
        if row["campaign"] != current_campaign:
            current_campaign = row["campaign"]
            lines.append(f"## Campaign: `{current_campaign}`")
            lines.append("")
        key = row["key"]
        gate_url = urls.get(key) or placeholder_url()
        eng = row["engagement"]
        lines.append(f"### `{key}`")
        lines.append("")
        if row["prompt_ref"]:
            lines.append(f"- **Prompt file:** `{row['prompt_ref']}`")
        if eng.get("rollout_day") is not None:
            lines.append(f"- **Rollout day:** {eng.get('rollout_day')}")
        if eng.get("narrative_tension"):
            lines.append(f"- **Tension:** {eng.get('narrative_tension')}")
        lines.append(f"- **LV title:** `{row['lv_title']}`")
        lines.append(f"- **LV URL:** `{gate_url}`")
        lines.append("")
        lines.append("**LV Text body** (paste into Text asset):")
        lines.append("")
        lines.append("```")
        lines.append(row["prompt_body"])
        lines.append("```")
        lines.append("")
        lines.append("**Telegram HTML** (single gate — no addlist footer):")
        lines.append("")
        lines.append("```html")
        lines.append(telegram_html(gate_url, row["item"]))
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def render_social_rollout(campaigns: list[dict], include_tts: bool) -> str:
    lines = [
        "# Prompt campaigns — social rollout (engagement-first)",
        "",
        "Auto-generated. **X = clearnet hub** (no LV). **Telegram = LV prompt drop** per `ENGAGEMENT_DOCTRINE.md`.",
        "",
        "---",
        "",
    ]
    for bundle in campaigns:
        camp = bundle["campaign"]
        meta = bundle.get("engagement") or {}
        lines.append(f"## `{camp}`")
        lines.append("")
        if bundle.get("style_anchors"):
            lines.append(f"**Style anchors:** {bundle['style_anchors']}")
            lines.append("")
        if bundle.get("negative_prompt"):
            lines.append(f"**Negative prompt:** `{bundle['negative_prompt']}`")
            lines.append("")
        cadence = meta.get("cadence_days")
        if cadence:
            lines.append(f"**Suggested cadence:** every {cadence} day(s)")
        lines.append("")
        lines.append("| Day | Key | Tension | X hook |")
        lines.append("| --- | --- | --- | --- |")
        for item in bundle["items"]:
            eng = _engagement(item)
            key = item.get("key", "")
            day = eng.get("rollout_day", "—")
            tension = eng.get("narrative_tension") or "—"
            hook = eng.get("quote_hook") or (eng.get("x_copy") or {}).get("hook") or "—"
            lines.append(f"| {day} | `{key}` | {tension} | {hook} |")
        lines.append("")
        for item in sorted(
            bundle["items"],
            key=lambda i: (_engagement(i).get("rollout_day") is None, _engagement(i).get("rollout_day") or 999),
        ):
            key = str(item.get("key") or "")
            eng = _engagement(item)
            lines.append(f"### `{key}` — day {eng.get('rollout_day', '?')}")
            lines.append("")
            if eng.get("narrative_tension"):
                lines.append(f"**Tension:** {eng['narrative_tension']}")
                lines.append("")
            lines.append("**X / Buffer (clearnet — pair with generated art):**")
            lines.append("")
            lines.append("```")
            lines.append(x_post_plain(item))
            lines.append("```")
            lines.append("")
            lines.append("**Telegram teaser (before LV link):**")
            lines.append("")
            lines.append(f"> {telegram_teaser(item)}")
            lines.append("")
            if include_tts and eng.get("tts_script"):
                lines.append("**TTS hook (optional — not wired in TBCC yet):**")
                lines.append("")
                lines.append("```")
                lines.append(str(eng["tts_script"]))
                lines.append("```")
                lines.append("")
            lines.append("---")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Export LV + social rollout manifests from prompt_gate catalogs")
    p.add_argument(
        "--write-catalog-urls",
        type=Path,
        metavar="JSON",
        help='Optional {"key": "https://link-target.net/..."} to fill real URLs',
    )
    p.add_argument("--include-tts", action="store_true", help="Include tts_script blocks in SOCIAL_ROLLOUT.md")
    p.add_argument("--stdout", action="store_true", help="Print LV manifest to stdout only")
    args = p.parse_args()

    urls: dict[str, str] = {}
    if args.write_catalog_urls and args.write_catalog_urls.is_file():
        raw = json.loads(args.write_catalog_urls.read_text(encoding="utf-8"))
        urls = {str(k): str(v) for k, v in raw.items() if not str(k).startswith("_")}

    rows, campaigns = load_catalogs()
    if not rows:
        print("No catalog rows found.", file=sys.stderr)
        return 1

    lv_text = render_lv_manifest(rows, urls)
    rollout_text = render_social_rollout(campaigns, include_tts=args.include_tts)

    if args.stdout:
        print(lv_text)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LV_PATH.write_text(lv_text, encoding="utf-8")
    ROLLOUT_PATH.write_text(rollout_text, encoding="utf-8")
    print(f"Wrote {len(rows)} LV row(s) -> {LV_PATH}")
    print(f"Wrote social rollout -> {ROLLOUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
