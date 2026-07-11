"""Load, ingest, and LLM-adapt Telegram promo swipes for AOF copy lanes."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data.aof_brand_voice import tactics_prompt_block, voice_prompt_for_lane

logger = logging.getLogger(__name__)

_SWIPES_DIR = Path(__file__).resolve().parent.parent / "data" / "aof_copy_swipes"
_DEFAULT_SWIPE_FILE = "telegram_native_ads.json"
_SWIPE_TITLE_PREFIX = "[swipe] "


def swipes_dir() -> Path:
    return _SWIPES_DIR


def swipe_file_path(name: str | None = None) -> Path:
    return _SWIPES_DIR / (name or _DEFAULT_SWIPE_FILE)


def _slug_id(text: str, prefix: str = "swipe") -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def load_swipe_file(name: str | None = None) -> dict[str, Any]:
    path = swipe_file_path(name)
    if not path.is_file():
        return {"schema_version": 1, "swipes": []}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def list_swipes(name: str | None = None) -> list[dict[str, Any]]:
    data = load_swipe_file(name)
    swipes = data.get("swipes")
    return list(swipes) if isinstance(swipes, list) else []


def get_swipe(swipe_id: str, name: str | None = None) -> dict[str, Any] | None:
    for item in list_swipes(name):
        if (item.get("id") or "").strip() == swipe_id:
            return item
    return None


def ingest_swipe_raw(
    raw_body: str,
    *,
    source: str = "manual_paste",
    format: str = "telegram_promo",
    tags: list[str] | None = None,
    tactics: list[str] | None = None,
    notes: str = "",
    swipe_id: str | None = None,
    file_name: str | None = None,
) -> dict[str, Any]:
    """
    Append a new swipe to the JSON repo (idempotent on exact raw_body match).
    Returns the stored swipe dict.
    """
    body = (raw_body or "").strip()
    if not body:
        raise ValueError("raw_body required")

    path = swipe_file_path(file_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_swipe_file(file_name) if path.is_file() else {"schema_version": 1, "swipes": []}
    swipes: list[dict[str, Any]] = list(data.get("swipes") or [])

    for existing in swipes:
        if (existing.get("raw_body") or "").strip() == body:
            return existing

    sid = (swipe_id or "").strip() or _slug_id(body)
    entry: dict[str, Any] = {
        "id": sid,
        "source": source,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "format": format,
        "tags": tags or [],
        "tactics": tactics or [],
        "raw_body": body,
        "notes": notes,
    }
    swipes.append(entry)
    data["swipes"] = swipes
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    logger.info("Ingested swipe %s → %s", sid, path)
    return entry


def _aof_facts_block(extra_facts: dict[str, Any] | None = None) -> str:
    """Real AOF facts the model may use — extend via extra_facts at adapt time."""
    facts = {
        "network": "AOF — multi-lane adult Telegram network (AI, TABOO, MILF, PACKS, VIP, LOOT, etc.)",
        "bot_mau": "10,000+ monthly active users on the subscription bot (social proof — use when relevant)",
        "positioning": "TBCC pipeline — scraped, gated, curated deposits; not a repost farm",
        "entry": "@aof_lootgod_bot for first contact, Loot Room Group for public commons, @aofsubscriptions_bot for VIP",
    }
    if extra_facts:
        facts.update(extra_facts)
    lines = ["AOF facts (use only these — never invent competitor stats or fake pricing):"]
    for k, v in facts.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def adapt_swipe_sync(
    swipe_id: str,
    lane: str,
    *,
    extra_facts: dict[str, Any] | None = None,
    required_urls: list[str] | None = None,
    swipe_file: str | None = None,
) -> str:
    """
    Rewrite a swipe for an AOF lane using LLM. Preserves tactics, replaces names/numbers with AOF truth.
    """
    from app.services.llm_completions import complete_chat_text_sync, text_llm_configured

    if not text_llm_configured():
        raise RuntimeError("LLM not configured for swipe adapt")

    swipe = get_swipe(swipe_id, swipe_file)
    if not swipe:
        raise ValueError(f"swipe not found: {swipe_id}")

    raw = (swipe.get("raw_body") or "").strip()
    tactic_ids = swipe.get("tactics") if isinstance(swipe.get("tactics"), list) else []
    tactics_block = tactics_prompt_block([str(t) for t in tactic_ids])

    url_block = "(none — do not invent links)"
    if required_urls:
        url_block = "\n".join(f"- {u}" for u in required_urls)

    system = (
        "You adapt competitor/inspiration Telegram promo copy into original AOF brand copy. "
        "Never paste competitor channel names, prices, or file counts. "
        "Keep the persuasion structure and emotional beats. "
        "Output only the final caption — no commentary.\n\n"
        f"{voice_prompt_for_lane(lane)}\n\n"
        f"{tactics_block}\n\n"
        f"{_aof_facts_block(extra_facts)}"
    )

    user = (
        f"Target lane: {lane}\n\n"
        f"Required URLs (verbatim if provided):\n{url_block}\n\n"
        f"Inspiration swipe (DO NOT copy verbatim):\n{raw}\n\n"
        "Adapted AOF caption:"
    )

    text = complete_chat_text_sync(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=_adapt_model(),
        max_tokens=_adapt_max_tokens(lane),
        temperature=0.8,
        timeout=90.0,
    )
    text = _strip_fences(text)
    if lane == "x_mirror":
        text = _fit_x(text)
    return text


def adapt_swipe_to_snippet_title(swipe_id: str, lane: str) -> str:
    return f"{_SWIPE_TITLE_PREFIX}{lane}:{swipe_id}"[:256]


def promote_adapted_to_caption_snippets(
    db: Any,
    swipe_id: str,
    lane: str,
    *,
    extra_facts: dict[str, Any] | None = None,
    required_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Adapt swipe and insert into caption_snippets if title not already present."""
    from app.models.caption_snippet import CaptionSnippet

    body = adapt_swipe_sync(
        swipe_id,
        lane,
        extra_facts=extra_facts,
        required_urls=required_urls,
    ).strip()
    if not body:
        raise RuntimeError("empty adapt result")

    title = adapt_swipe_to_snippet_title(swipe_id, lane)
    existing = db.query(CaptionSnippet).filter(CaptionSnippet.title == title).first()
    if existing:
        return {"created": False, "id": existing.id, "title": title, "body": existing.body}

    row = CaptionSnippet(title=title, body=body[:16000])
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"created": True, "id": row.id, "title": title, "body": body}


def _adapt_model() -> str:
    import os

    from app.services.llm_completions import resolve_text_model

    explicit = (
        os.environ.get("TBCC_AOF_COPY_SWIPE_MODEL")
        or os.environ.get("TBCC_AOF_COPY_LLM_MODEL")
        or os.environ.get("TBCC_LLM_MODEL")
        or ""
    ).strip()
    return resolve_text_model(explicit or None)


def _adapt_max_tokens(lane: str) -> int:
    if lane == "x_mirror":
        return 120
    if lane == "main_group_pulse":
        return 280
    return 900


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _fit_x(text: str, limit: int = 280) -> str:
    t = re.sub(r"<[^>]+>", "", text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip() + "…"
