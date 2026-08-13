#!/usr/bin/env python3
"""Compile historical prompt sources into v3 creative_prompt_catalog JSON + DB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TBCC = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.creative_prompt_catalog import (  # noqa: E402
    CreativePromptCatalog,
    MasterTemplate,
    PromptVariation,
    build_variation_prompt,
    catalog_to_db_rows,
)

OUT_DIR = BACKEND / "app" / "data" / "creative_prompt_catalog"
FALLBACK_OUT_DIR = TBCC / "docs" / "samples" / "creative_prompt_catalog"


def _ingest_loot_cards() -> CreativePromptCatalog:
    path = BACKEND / "app" / "data" / "aof_loot_card_presets.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    master = MasterTemplate(
        layout_lock_ref="docs/samples/gemini_loot_card_layout_lock.txt",
        style_anchors="magenta marquee trading card chrome, loot god tier reveal",
        negative_prompt="gibberish UI text, wrong aspect ratio, watermark",
    )
    variations: list[PromptVariation] = []
    scenes = data.get("scenes") or data.get("presets") or {}
    if isinstance(scenes, dict):
        for key, preset in scenes.items():
            if not isinstance(preset, dict):
                continue
            variations.append(
                PromptVariation(
                    key=f"loot_card_{key}",
                    subject_delta=str(preset.get("text") or preset.get("scene") or preset.get("description") or key),
                    tier=str(preset.get("tier") or key),
                    tags=["loot", "card", "tier"],
                    surfaces=["lv_gate", "gemini", "perchance"],
                )
            )
    return CreativePromptCatalog(campaign="loot_tier_cards", master_template=master, variations=variations)


def _ingest_promo_scenes() -> CreativePromptCatalog:
    path = BACKEND / "app" / "data" / "aof_promo_scene_presets.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    master = MasterTemplate(
        layout_lock_ref="docs/samples/gemini_aof_promo_layout_lock.txt",
        style_anchors="AOF 9:16 promo poster, QR + pill columns",
        negative_prompt="misspelled UI, wrong aspect, cartoon",
    )
    variations: list[PromptVariation] = []
    for key, preset in (data.get("presets") or {}).items():
        if not isinstance(preset, dict):
            continue
        variations.append(
            PromptVariation(
                key=f"promo_{key}",
                subject_delta=str(preset.get("scene") or preset.get("description") or key),
                tags=["promo", "x", "poster"],
                surfaces=["lv_gate", "gemini", "perchance", "x_teaser"],
            )
        )
    scenes = data.get("scenes") or {}
    if isinstance(scenes, dict):
        for key, scene in scenes.items():
            if not isinstance(scene, dict):
                continue
            variations.append(
                PromptVariation(
                    key=f"promo_scene_{key}",
                    subject_delta=str(scene.get("description") or key),
                    tags=["promo", "scene"],
                    surfaces=["lv_gate", "gemini"],
                )
            )
    return CreativePromptCatalog(campaign="aof_promo_posters", master_template=master, variations=variations)


def _ingest_prompt_gate_catalogs() -> list[CreativePromptCatalog]:
    catalogs: list[CreativePromptCatalog] = []
    for path in sorted((BACKEND / "app" / "data").glob("prompt_gate_catalog*.json")):
        if path.name.endswith(".sample.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        campaign = str(data.get("campaign") or path.stem.replace("prompt_gate_catalog_", ""))
        master = MasterTemplate(
            style_anchors=str(data.get("style_anchors") or ""),
            negative_prompt=str(data.get("negative_prompt") or ""),
        )
        variations: list[PromptVariation] = []
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            variations.append(
                PromptVariation(
                    key=key,
                    subject_delta=str(item.get("prompt_body") or ""),
                    prompt_body=str(item.get("prompt_body") or "") or None,
                    prompt_ref=item.get("prompt_ref"),
                    tier=str(item.get("tier") or ""),
                    tags=[campaign],
                    surfaces=["lv_gate", "telegram", "x_teaser"],
                    engagement=dict(item.get("engagement") or {}),
                )
            )
        if variations:
            catalogs.append(
                CreativePromptCatalog(
                    campaign=campaign,
                    master_template=master,
                    variations=variations,
                    notes=str(data.get("notes") or ""),
                )
            )
    return catalogs


def _ingest_link_hub_prompts() -> CreativePromptCatalog:
    path = TBCC / "docs" / "samples" / "link_hub_menus" / "IMAGE_PROMPTS.md"
    master = MasterTemplate(style_anchors="AOF link hub menu card, 9:16", negative_prompt="gibberish text")
    variations: list[PromptVariation] = []
    if path.is_file():
        blocks = path.read_text(encoding="utf-8").split("## ")
        for block in blocks[1:]:
            lines = block.strip().splitlines()
            if not lines:
                continue
            title = lines[0].strip().lower().replace(" ", "_")
            body = "\n".join(lines[1:]).strip()
            if body:
                variations.append(
                    PromptVariation(
                        key=f"link_hub_{title}",
                        subject_delta=body,
                        tags=["link_hub", "menu"],
                        surfaces=["lv_gate", "gemini"],
                    )
                )
    return CreativePromptCatalog(campaign="link_hub_menus", master_template=master, variations=variations)


def _write_catalog(catalog: CreativePromptCatalog) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "campaign": catalog.campaign,
        "schema_version": catalog.schema_version,
        "master_template": {
            "layout_lock_ref": catalog.master_template.layout_lock_ref,
            "style_anchors": catalog.master_template.style_anchors,
            "negative_prompt": catalog.master_template.negative_prompt,
            "chrome_block": catalog.master_template.chrome_block,
        },
        "variations": [
            {
                "key": v.key,
                "subject_delta": v.subject_delta,
                "tier": v.tier,
                "tags": v.tags,
                "surfaces": v.surfaces,
                "engagement": v.engagement,
                "prompt_ref": v.prompt_ref,
            }
            for v in catalog.variations
        ],
        "notes": catalog.notes,
    }
    out = OUT_DIR / f"{catalog.campaign}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def _sync_db(catalogs: list[CreativePromptCatalog], *, execute: bool) -> dict:
    from app.database.session import SessionLocal
    from app.models.creative_catalog import CreativeCatalogEntry
    from app.services.prompt_gate_registry import upsert_catalog_row

    report = {"catalog_rows": 0, "prompt_gates_queued": 0}
    db = SessionLocal()
    try:
        for catalog in catalogs:
            for row in catalog_to_db_rows(catalog):
                existing = (
                    db.query(CreativeCatalogEntry)
                    .filter(
                        CreativeCatalogEntry.entry_type == "image_prompt",
                        CreativeCatalogEntry.catalog_key == row["catalog_key"],
                    )
                    .first()
                )
                if existing:
                    existing.body = row["body"]
                    existing.master_json = row["master_json"]
                    existing.subject_delta = row.get("subject_delta")
                    existing.tags_json = row.get("tags_json")
                    existing.campaign = row["campaign"]
                elif execute:
                    db.add(CreativeCatalogEntry(**row))
                report["catalog_rows"] += 1
                if execute and row.get("prompt_gate_key") and row.get("body"):
                    upsert_catalog_row(
                        db,
                        row["prompt_gate_key"],
                        row["body"],
                        tier=row.get("campaign"),
                        prompt_ref=row.get("catalog_key"),
                    )
                    report["prompt_gates_queued"] += 1
        if execute:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest creative prompt catalogs")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--skip-db", action="store_true", help="Skip DB sync (default when not --execute)")
    args = parser.parse_args()
    skip_db = args.skip_db or not args.execute

    catalogs = [
        _ingest_loot_cards(),
        _ingest_promo_scenes(),
        _ingest_link_hub_prompts(),
        *_ingest_prompt_gate_catalogs(),
    ]
    written = [_write_catalog(c) for c in catalogs]
    report = {
        "ok": True,
        "catalogs": len(catalogs),
        "variations": sum(len(c.variations) for c in catalogs),
        "files": [str(p) for p in written],
    }
    if not skip_db:
        report["db"] = _sync_db(catalogs, execute=args.execute)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
