"""Refill Buffer's native X queue with hub + affiliate captions (Linkvertise = Telegram only)."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.data.aof_x_buffer_native_pool import AOF_X_BUFFER_NATIVE_POOL
from app.services.aof_social_links import fill_armory_template, x_linkvertise_enabled, x_outbound_url
from app.services.buffer_graphql import (
    buffer_api_key,
    create_post,
    find_channel_id_by_service,
    list_posts,
    resolve_organization_id,
)
from app.services.buffer_post_result import buffer_create_post_error_message, buffer_create_post_succeeded
from app.services.buffer_x_caption import fit_plaintext_for_x

logger = logging.getLogger(__name__)

_LV_HOST_RE = re.compile(
    r"link-center\.net|direct-link\.net|link-hub\.net|link-target\.net|linkvertise",
    re.I,
)
_X_OK_RE = re.compile(
    r"t\.me/|allmylinks|nodress|nudify\.now|musebox|playbun|fapify|drawai|botynude|gravatar",
    re.I,
)


def _min_queue_depth() -> int:
    try:
        return max(1, min(10, int((os.getenv("TBCC_BUFFER_NATIVE_MIN_DEPTH") or "3").strip())))
    except ValueError:
        return 3


def _max_scheduled_posts() -> int:
    try:
        return max(1, min(50, int((os.getenv("TBCC_BUFFER_NATIVE_MAX_SCHEDULED") or "10").strip())))
    except ValueError:
        return 10


def _x_channel_id() -> str | None:
    primary = (os.getenv("TBCC_BUFFER_CHANNEL_ID_PRIMARY") or "").strip()
    if primary:
        return primary
    if not buffer_api_key():
        return None
    try:
        return find_channel_id_by_service("twitter")
    except Exception:
        return None


def _normalize_text_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def build_native_queue_caption(entry: dict[str, str]) -> str:
    from app.services.aof_social_links import aof_hub_invite_url

    utm_campaign = str(entry.get("utm_campaign") or entry.get("gate_key") or "native_x").strip()
    raw = fill_armory_template(
        str(entry.get("text") or ""),
        utm_source="buffer",
        utm_medium="x",
        utm_campaign=utm_campaign,
        for_x=True,
    )
    overflow = x_outbound_url()
    text = fit_plaintext_for_x(raw, overflow_url=overflow or aof_hub_invite_url())
    if len(text) > 280:
        text = text[:277].rstrip() + "…"
    return text


def _caption_allowed_for_x(text: str) -> bool:
    if not text:
        return False
    if not x_linkvertise_enabled() and _LV_HOST_RE.search(text):
        return False
    return bool(_X_OK_RE.search(text))


def _collect_existing_texts(*, organization_id: str, channel_id: str) -> set[str]:
    keys: set[str] = set()
    for status in ("scheduled", "draft", "sent"):
        try:
            nodes = list_posts(
                organization_id=organization_id,
                channel_ids=[channel_id],
                status=[status],
                first=100,
            )
        except Exception as e:
            logger.warning("buffer native refill: list_posts status=%s failed: %s", status, e)
            continue
        for node in nodes:
            key = _normalize_text_key(str(node.get("text") or ""))
            if key:
                keys.add(key)
    return keys


def _candidate_captions(*, exclude: set[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for entry in AOF_X_BUFFER_NATIVE_POOL:
        text = build_native_queue_caption(entry)
        if not text or not _caption_allowed_for_x(text):
            continue
        key = _normalize_text_key(text)
        if key in exclude or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def refill_buffer_native_queue(*, dry_run: bool = False) -> dict[str, Any]:
    """
    Top up Buffer's native X queue when scheduled count < TBCC_BUFFER_NATIVE_MIN_DEPTH.
    Fills toward TBCC_BUFFER_NATIVE_MAX_SCHEDULED (plan limit default 10).
    """
    if not buffer_api_key():
        return {"status": "skipped", "reason": "TBCC_BUFFER_API_KEY unset"}

    channel_id = _x_channel_id()
    if not channel_id:
        return {"status": "skipped", "reason": "no X channel id (set TBCC_BUFFER_CHANNEL_ID_PRIMARY)"}

    min_depth = _min_queue_depth()
    max_scheduled = _max_scheduled_posts()

    try:
        org_id = resolve_organization_id()
    except Exception as e:
        return {"status": "error", "reason": str(e)}

    scheduled = list_posts(
        organization_id=org_id,
        channel_ids=[channel_id],
        status=["scheduled"],
        first=max_scheduled + 5,
    )
    scheduled_count = len(scheduled)
    report: dict[str, Any] = {
        "status": "ok",
        "channel_id": channel_id,
        "scheduled_before": scheduled_count,
        "min_depth": min_depth,
        "max_scheduled": max_scheduled,
        "created": 0,
        "errors": [],
        "captions_preview": [],
    }

    if scheduled_count >= min_depth:
        report["status"] = "skipped"
        report["reason"] = f"depth {scheduled_count} >= min {min_depth}"
        return report

    slots = max(0, max_scheduled - scheduled_count)
    if slots <= 0:
        report["status"] = "skipped"
        report["reason"] = "at plan max"
        return report

    exclude = _collect_existing_texts(organization_id=org_id, channel_id=channel_id)
    candidates = _candidate_captions(exclude=exclude)
    if not candidates:
        report["status"] = "empty"
        report["reason"] = "no fresh captions (all pool entries match recent posts)"
        return report

    to_create = candidates[:slots]
    report["captions_preview"] = to_create[:5]

    if dry_run:
        report["would_create"] = len(to_create)
        return report

    for text in to_create:
        from app.services.buffer_x_promo_image import direct_url_for_buffer, pick_promo_image

        image_url = direct_url_for_buffer(pick_promo_image())
        res = create_post(
            channel_id,
            text,
            mode="addToQueue",
            scheduling_type="automatic",
            image_url=image_url,
        )
        if buffer_create_post_succeeded(res):
            report["created"] += 1
            exclude.add(_normalize_text_key(text))
            from app.database.session import SessionLocal
            from app.services.promo_affiliate_rotation import pick_affiliate

            local = SessionLocal()
            try:
                if pick_affiliate(local, "x_buffer", advance=True):
                    local.commit()
            finally:
                local.close()
        else:
            msg = buffer_create_post_error_message(res) or "createPost failed"
            report["errors"].append(msg[:200])
            logger.warning("buffer native refill createPost: %s", msg)

    report["scheduled_after"] = scheduled_count + report["created"]
    logger.info("buffer native queue refill: %s", report)
    return report
