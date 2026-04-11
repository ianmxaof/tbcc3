"""LLM-assisted copy for shop products — tags must come from existing tbcc_tags (caller supplies catalog)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_DESC_CHARS = 1200
MAX_VARIANTS = 12


def _openai_key() -> str:
    return (os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def _model() -> str:
    return (os.getenv("TBCC_LLM_MODEL") or "gpt-4o-mini").strip()


def openai_configured() -> bool:
    return bool(_openai_key())


def current_model() -> str:
    return _model()


def _parse_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    data = json.loads(t)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


def suggest_shop_product_copy(
    *,
    name: str,
    description: str | None,
    product_type: str,
    tag_catalog: list[dict[str, Any]],
    brand_voice_hint: str | None = None,
) -> dict[str, Any]:
    """
    Call OpenAI chat completions with JSON mode. tag_catalog items: id, slug, name (and optional category).

    Returns:
      tag_ids: list[int] — subset of catalog ids
      description: str | None — main catalog / invoice line
      description_variants: list[str] — extra lines for rotation
      hook_line: str | None — short first line (optional, for UI)
    """
    key = _openai_key()
    if not key:
        raise RuntimeError("Set TBCC_OPENAI_API_KEY or OPENAI_API_KEY to enable AI suggestions")

    if not tag_catalog:
        raise ValueError("tag_catalog is empty — add tags under TBCC first (GET /tags)")

    allowed_ids = {int(t["id"]) for t in tag_catalog if t.get("id") is not None}

    voice = (brand_voice_hint or "").strip() or (
        "Direct, premium adult catalog tone. No minors, no illegal content. "
        "Focus on consenting-adult fantasy product marketing."
    )

    catalog_json = json.dumps(
        [{"id": t["id"], "slug": t["slug"], "name": t["name"]} for t in tag_catalog],
        ensure_ascii=False,
    )

    user_parts = [
        f"Product name: {name}",
        f"Product type: {product_type} (subscription = channel access; bundle = one-time digital pack)",
        f"Existing notes from creator (may be empty): {description or ''}",
        "",
        "Allowed tags (you MUST only use tag ids from this list):",
        catalog_json,
        "",
        "Return a JSON object with keys:",
        '- "tag_ids": array of integer ids (0–12 ids) chosen from the allowed list only',
        '- "description": one main description paragraph for Telegram invoice / product card (plain text, no markdown)',
        '- "description_variants": 1–4 alternate description paragraphs (strings), can be empty array',
        '- "hook_line": optional single short hook (first line teaser), max ~200 chars',
        "Do not invent tag ids. Do not output hashtags in description fields (hashtags will be derived from tags in the UI).",
    ]

    payload = {
        "model": _model(),
        "temperature": 0.75,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": f"You are a copywriter for an adult content creator storefront. {voice}",
            },
            {"role": "user", "content": "\n".join(user_parts)},
        ],
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:500]
        except Exception:
            pass
        logger.warning("OpenAI HTTP error: %s %s", e.response.status_code, detail)
        raise RuntimeError(f"OpenAI API error ({e.response.status_code})") from e
    except Exception as e:
        logger.warning("OpenAI request failed: %s", e)
        raise

    try:
        content = body["choices"][0]["message"]["content"]
        parsed = _parse_json_object(content)
    except (KeyError, IndexError, json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("bad OpenAI response: %s", e)
        raise RuntimeError("Could not parse model response") from e

    raw_ids = parsed.get("tag_ids")
    tag_ids: list[int] = []
    if isinstance(raw_ids, list):
        for x in raw_ids:
            try:
                i = int(x)
                if i in allowed_ids and i not in tag_ids:
                    tag_ids.append(i)
            except (TypeError, ValueError):
                continue
    tag_ids = tag_ids[:12]

    desc = parsed.get("description")
    main_desc = (str(desc).strip()[:MAX_DESC_CHARS] if desc is not None else None) or None

    variants_out: list[str] = []
    raw_var = parsed.get("description_variants")
    if isinstance(raw_var, list):
        for line in raw_var:
            s = str(line or "").strip()
            if s and s not in variants_out:
                variants_out.append(s[:MAX_DESC_CHARS])
            if len(variants_out) >= MAX_VARIANTS:
                break

    hook = parsed.get("hook_line")
    hook_line = None
    if hook is not None:
        h = str(hook).strip()[:240]
        hook_line = h or None

    return {
        "tag_ids": tag_ids,
        "description": main_desc,
        "description_variants": variants_out,
        "hook_line": hook_line,
        "model": _model(),
    }


MAX_MEDIA_CAPTION = 900


def suggest_media_tags_and_caption(
    *,
    media_id: int,
    media_type: str | None,
    existing_tags: str | None,
    pool_name: str | None,
    source_channel: str | None,
    tag_catalog: list[dict[str, Any]],
    brand_voice_hint: str | None = None,
) -> dict[str, Any]:
    """
    Text-only context (no image bytes). Tags must be chosen by id from tag_catalog.

    Returns:
      tag_ids, tags_csv (comma-separated display names for PATCH bulk/tags),
      caption, caption_variants, model
    """
    key = _openai_key()
    if not key:
        raise RuntimeError("Set TBCC_OPENAI_API_KEY or OPENAI_API_KEY to enable AI suggestions")

    if not tag_catalog:
        raise ValueError("tag_catalog is empty — create tags in TBCC first (GET /tags)")

    allowed_ids = {int(t["id"]) for t in tag_catalog if t.get("id") is not None}
    id_to_name = {int(t["id"]): str(t.get("name") or t.get("slug") or "") for t in tag_catalog if t.get("id") is not None}

    voice = (brand_voice_hint or "").strip() or (
        "Direct, premium adult catalog tone. No minors, no illegal content. "
        "Consenting-adult context only. Suggest concise Telegram-friendly copy."
    )

    catalog_json = json.dumps(
        [{"id": t["id"], "slug": t["slug"], "name": t["name"], "category": t.get("category")} for t in tag_catalog],
        ensure_ascii=False,
    )

    user_parts = [
        f"Media id: {media_id}",
        f"Media type: {(media_type or '').strip() or 'unknown'}",
        f"Pool (context): {pool_name or ''}",
        f"Source / URL hint: {source_channel or ''}",
        f"Existing tags string (may be empty): {existing_tags or ''}",
        "",
        "Allowed tags (you MUST only use tag ids from this list):",
        catalog_json,
        "",
        "Return a JSON object with keys:",
        '- "tag_ids": array of integer ids (pick 3–10) from the allowed list only',
        '- "caption": one short caption suitable for a Telegram post under this media (plain text, no markdown)',
        '- "caption_variants": 1–3 alternate caption strings for A/B testing ideas (can be empty array)',
        '- "curator_note": optional one sentence on why these tags fit (for the human reviewer)',
        "Keep caption + variants tasteful and non-explicit if possible; focus on theme/style.",
    ]

    payload = {
        "model": _model(),
        "temperature": 0.65,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": f"You tag and caption media for an adult creator workflow. {voice}",
            },
            {"role": "user", "content": "\n".join(user_parts)},
        ],
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:500]
        except Exception:
            pass
        logger.warning("OpenAI HTTP error: %s %s", e.response.status_code, detail)
        raise RuntimeError(f"OpenAI API error ({e.response.status_code})") from e
    except Exception as e:
        logger.warning("OpenAI request failed: %s", e)
        raise

    try:
        content = body["choices"][0]["message"]["content"]
        parsed = _parse_json_object(content)
    except (KeyError, IndexError, json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("bad OpenAI response: %s", e)
        raise RuntimeError("Could not parse model response") from e

    raw_ids = parsed.get("tag_ids")
    tag_ids: list[int] = []
    if isinstance(raw_ids, list):
        for x in raw_ids:
            try:
                i = int(x)
                if i in allowed_ids and i not in tag_ids:
                    tag_ids.append(i)
            except (TypeError, ValueError):
                continue
    tag_ids = tag_ids[:12]

    names_ordered = [id_to_name[i] for i in tag_ids if i in id_to_name and id_to_name[i]]
    tags_csv = ", ".join(names_ordered)

    cap = parsed.get("caption")
    caption = (str(cap).strip()[:MAX_MEDIA_CAPTION] if cap is not None else "") or ""

    variants_out: list[str] = []
    raw_var = parsed.get("caption_variants")
    if isinstance(raw_var, list):
        for line in raw_var:
            s = str(line or "").strip()
            if s and s not in variants_out:
                variants_out.append(s[:MAX_MEDIA_CAPTION])
            if len(variants_out) >= 6:
                break

    note = parsed.get("curator_note")
    curator_note = None
    if note is not None:
        curator_note = str(note).strip()[:500] or None

    return {
        "media_id": media_id,
        "tag_ids": tag_ids,
        "tags_csv": tags_csv,
        "caption": caption or None,
        "caption_variants": variants_out,
        "curator_note": curator_note,
        "model": _model(),
    }


def hashtag_line_from_slugs(slugs: list[str], limit: int = 10) -> str:
    """Build a single line of #hashtags from tag slugs (Telegram-friendly)."""
    parts: list[str] = []
    for s in slugs:
        h = re.sub(r"[^a-zA-Z0-9_]", "", (s or "").strip().replace("-", ""))
        if len(h) >= 2:
            parts.append("#" + h)
        if len(parts) >= limit:
            break
    return " ".join(parts)
