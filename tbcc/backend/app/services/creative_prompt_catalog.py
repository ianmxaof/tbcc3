"""Creative prompt catalog v3 — master template + variation composition."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TBCC_ROOT = Path(__file__).resolve().parents[3]
CATALOG_DIR = TBCC_ROOT / "docs" / "samples" / "creative_prompt_catalog"


@dataclass
class MasterTemplate:
    layout_lock_ref: str | None = None
    style_anchors: str = ""
    negative_prompt: str = ""
    chrome_block: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MasterTemplate:
        d = data or {}
        return cls(
            layout_lock_ref=(d.get("layout_lock_ref") or None),
            style_anchors=str(d.get("style_anchors") or "").strip(),
            negative_prompt=str(d.get("negative_prompt") or "").strip(),
            chrome_block=str(d.get("chrome_block") or "").strip(),
        )


@dataclass
class PromptVariation:
    key: str
    subject_delta: str = ""
    tier: str | None = None
    tags: list[str] = field(default_factory=list)
    surfaces: list[str] = field(default_factory=list)
    engagement: dict[str, Any] = field(default_factory=dict)
    prompt_ref: str | None = None
    prompt_body: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptVariation:
        tags = data.get("tags") or []
        surfaces = data.get("surfaces") or []
        return cls(
            key=str(data.get("key") or "").strip(),
            subject_delta=str(data.get("subject_delta") or data.get("prompt_body") or "").strip(),
            tier=(data.get("tier") or None),
            tags=[str(t) for t in tags] if isinstance(tags, list) else [],
            surfaces=[str(s) for s in surfaces] if isinstance(surfaces, list) else [],
            engagement=dict(data.get("engagement") or {}),
            prompt_ref=(data.get("prompt_ref") or None),
            prompt_body=(data.get("prompt_body") or None),
        )


@dataclass
class CreativePromptCatalog:
    campaign: str
    schema_version: int = 3
    master_template: MasterTemplate = field(default_factory=MasterTemplate)
    variations: list[PromptVariation] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CreativePromptCatalog:
        variations = [PromptVariation.from_dict(v) for v in (data.get("variations") or []) if isinstance(v, dict)]
        return cls(
            campaign=str(data.get("campaign") or "default").strip(),
            schema_version=int(data.get("schema_version") or 3),
            master_template=MasterTemplate.from_dict(data.get("master_template")),
            variations=variations,
            notes=str(data.get("notes") or ""),
        )


def _read_ref(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = TBCC_ROOT / path
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return ""


def build_variation_prompt(
    catalog: CreativePromptCatalog | dict[str, Any],
    variation: PromptVariation | dict[str, Any],
) -> str:
    """Compose full prompt_body = layout lock + master blocks + subject_delta."""
    if isinstance(catalog, dict):
        catalog = CreativePromptCatalog.from_dict(catalog)
    if isinstance(variation, dict):
        variation = PromptVariation.from_dict(variation)

    if variation.prompt_body:
        return variation.prompt_body.strip()

    parts: list[str] = []
    master = catalog.master_template
    layout = _read_ref(master.layout_lock_ref)
    if layout:
        parts.append(layout)
    if master.style_anchors:
        parts.append(f"STYLE ANCHORS: {master.style_anchors}")
    if variation.prompt_ref:
        ref_body = _read_ref(variation.prompt_ref)
        if ref_body:
            parts.append(ref_body)
    if variation.subject_delta:
        parts.append(variation.subject_delta.strip())
    if master.chrome_block:
        parts.append(master.chrome_block)
    if master.negative_prompt:
        parts.append(f"AVOID: {master.negative_prompt}")
    return "\n\n".join(p for p in parts if p).strip()


def load_catalog_file(path: Path) -> CreativePromptCatalog:
    data = json.loads(path.read_text(encoding="utf-8"))
    return CreativePromptCatalog.from_dict(data)


def catalog_to_db_rows(catalog: CreativePromptCatalog) -> list[dict[str, Any]]:
    master_json = json.dumps(
        {
            "layout_lock_ref": catalog.master_template.layout_lock_ref,
            "style_anchors": catalog.master_template.style_anchors,
            "negative_prompt": catalog.master_template.negative_prompt,
            "chrome_block": catalog.master_template.chrome_block,
        }
    )
    rows: list[dict[str, Any]] = []
    for var in catalog.variations:
        if not var.key:
            continue
        body = build_variation_prompt(catalog, var)
        rows.append(
            {
                "entry_type": "image_prompt",
                "campaign": catalog.campaign,
                "catalog_key": var.key,
                "title": var.key.replace("_", " ").title(),
                "body": body,
                "master_json": master_json,
                "subject_delta": var.subject_delta or None,
                "tags_json": json.dumps(var.tags) if var.tags else None,
                "prompt_gate_key": var.key,
                "surface": (var.surfaces[0] if var.surfaces else "lv_gate"),
            }
        )
    return rows
