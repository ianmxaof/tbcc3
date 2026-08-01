"""Refill Buffer's native X queue with hub + affiliate captions (Linkvertise = Telegram only)."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.data.aof_x_buffer_native_pool import AOF_X_BUFFER_NATIVE_POOL
from app.services.aof_social_links import fill_armory_template, x_linkvertise_enabled, x_outbound_url
from app.services.buffer_graphql import (
    BufferRateLimitError,
    buffer_api_key,
    create_post,
    find_channel_id_by_service,
    list_posts,
    resolve_organization_id,
)
from app.services.buffer_post_result import buffer_create_post_error_message, buffer_create_post_succeeded
from app.services.buffer_x_caption import finalize_buffer_x_caption
from app.services.buffer_x_hashtags import append_x_hashtags

logger = logging.getLogger(__name__)

_LV_HOST_RE = re.compile(
    r"link-center\.net|direct-link\.net|link-hub\.net|link-target\.net|linkvertise",
    re.I,
)
_X_OK_RE = re.compile(
    r"t\.me/|allmylinks|nodress|nudify\.now|musebox|playbun|fapify|drawai|botynude|gravatar|gumroad\.com",
    re.I,
)


def _min_queue_depth() -> int:
    try:
        return max(1, min(10, int((os.getenv("TBCC_BUFFER_NATIVE_MIN_DEPTH") or "3").strip())))
    except ValueError:
        return 3


def _max_scheduled_posts() -> int:
    raw = (os.getenv("TBCC_BUFFER_NATIVE_MAX_SCHEDULED") or "50").strip()
    try:
        return max(1, min(100, int(raw)))
    except ValueError:
        return 50


def _native_pool_entries(db=None) -> list[dict[str, str]]:
    if db is not None:
        try:
            from app.services.social_copy_rotation import build_pool_entries_from_db, rotation_categories

            entries: list[dict[str, str]] = []
            for cat in rotation_categories():
                entries.extend(build_pool_entries_from_db(db, category=cat, limit=100))
            if entries:
                return entries
        except Exception:
            logger.debug("native pool social_copy fallback", exc_info=True)
    return list(AOF_X_BUFFER_NATIVE_POOL)


def _x_channel_ids() -> list[str]:
    ids: list[str] = []
    for key in ("TBCC_BUFFER_CHANNEL_ID_PRIMARY", "TBCC_BUFFER_CHANNEL_ID_X_SECONDARY"):
        cid = (os.getenv(key) or "").strip()
        if cid and cid not in ids:
            ids.append(cid)
    if ids:
        return ids
    if not buffer_api_key():
        return []
    try:
        one = find_channel_id_by_service("twitter")
        return [one] if one else []
    except Exception:
        return []


def _instagram_channel_ids() -> list[str]:
    raw = (os.getenv("TBCC_BUFFER_CHANNEL_IDS") or "").strip()
    return [c.strip() for c in raw.split(",") if c.strip()]


def _x_channel_id() -> str | None:
    ids = _x_channel_ids()
    return ids[0] if ids else None


def _normalize_text_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def build_native_queue_caption(
    entry: dict[str, str],
    *,
    db=None,
    advance_link_cycle: bool = False,
) -> str:
    from app.services.aof_social_links import aof_hub_invite_url
    from app.services.template_expand import expand_template_tokens

    utm_campaign = str(entry.get("utm_campaign") or entry.get("gate_key") or entry.get("category") or "native_x").strip()
    raw_text = expand_template_tokens(str(entry.get("text") or ""), db=db, for_x=True)
    raw = fill_armory_template(
        raw_text,
        utm_source="buffer",
        utm_medium="x",
        utm_campaign=utm_campaign,
        for_x=True,
        db=db,
        advance_affiliate=False,
    )
    overflow = x_outbound_url()
    text = finalize_buffer_x_caption(
        raw,
        db=db,
        overflow_url=overflow or aof_hub_invite_url(),
        advance_link_cycle=advance_link_cycle,
    )
    text = append_x_hashtags(text, max_chars=280)
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
        except BufferRateLimitError as e:
            logger.warning("buffer native refill: rate limited (retry_after=%s)", e.retry_after_s)
            break
        except Exception as e:
            logger.warning("buffer native refill: list_posts status=%s failed: %s", status, e)
            continue
        for node in nodes:
            key = _normalize_text_key(str(node.get("text") or ""))
            if key:
                keys.add(key)
    return keys


def _candidate_entries(*, exclude: set[str], allow_recycle: bool = False, db=None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    pool = _native_pool_entries(db)
    for entry in pool:
        text = build_native_queue_caption(entry, db=db)
        if not text or not _caption_allowed_for_x(text):
            continue
        key = _normalize_text_key(text)
        if key in seen:
            continue
        if key in exclude and not allow_recycle:
            continue
        seen.add(key)
        out.append(entry)
    return out


def _scheduled_count(*, organization_id: str, channel_id: str | None = None) -> int:
    try:
        nodes = list_posts(
            organization_id=organization_id,
            channel_ids=[channel_id] if channel_id else None,
            status=["scheduled"],
            first=100,
        )
    except BufferRateLimitError:
        raise
    except Exception as e:
        logger.warning("buffer native refill: scheduled count failed: %s", e)
        return 0
    return len(nodes)


def refill_buffer_native_queue(*, dry_run: bool = False) -> dict[str, Any]:
    """
    Top up Buffer native queues for all X channels (+ Instagram when configured).
    Respects org-wide TBCC_BUFFER_NATIVE_MAX_SCHEDULED (Buffer plan cap, default 10).
    """
    if not buffer_api_key():
        return {"status": "skipped", "reason": "TBCC_BUFFER_API_KEY unset"}

    x_channels = _x_channel_ids()
    ig_channels = _instagram_channel_ids()
    if not x_channels and not ig_channels:
        return {"status": "skipped", "reason": "no Buffer channel ids configured"}

    min_depth = _min_queue_depth()
    max_scheduled = _max_scheduled_posts()

    try:
        org_id = resolve_organization_id()
    except BufferRateLimitError as e:
        return {"status": "skipped", "reason": "rate_limited", "retry_after_s": e.retry_after_s}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

    try:
        org_scheduled = _scheduled_count(organization_id=org_id)
    except BufferRateLimitError as e:
        return {"status": "skipped", "reason": "rate_limited", "retry_after_s": e.retry_after_s}

    slots = max(0, max_scheduled - org_scheduled)
    report: dict[str, Any] = {
        "status": "ok",
        "org_scheduled_before": org_scheduled,
        "min_depth": min_depth,
        "max_scheduled": max_scheduled,
        "slots_available": slots,
        "x_channels": x_channels,
        "ig_channels": ig_channels,
        "created": 0,
        "by_channel": {},
        "errors": [],
        "captions_preview": [],
    }

    if slots <= 0 and org_scheduled >= min_depth:
        report["status"] = "skipped"
        report["reason"] = f"org depth {org_scheduled} >= min {min_depth} and at plan cap"
        return report

    exclude: set[str] = set()
    for cid in x_channels:
        exclude |= _collect_existing_texts(organization_id=org_id, channel_id=cid)

    allow_recycle = org_scheduled < min_depth

    from app.database.session import SessionLocal

    local = SessionLocal()
    try:
        candidate_entries = _candidate_entries(exclude=exclude, allow_recycle=allow_recycle, db=local)
        if not candidate_entries and not ig_channels:
            report["status"] = "empty"
            report["reason"] = "no captions in pool (templates empty or blocked for X)"
            return report
        if allow_recycle and exclude:
            report["recycled_captions"] = True

        if dry_run:
            report["would_create_x"] = min(slots, len(candidate_entries) * max(1, len(x_channels)))
            report["would_create_ig"] = min(slots, len(ig_channels) * 2)
            return report

        from app.services.promo_affiliate_rotation import pick_affiliate

        from app.services.social_copy_rotation import pick_pool_entry

        entry_idx = 0
        for channel_id in x_channels:
            if slots <= 0:
                break
            ch_before = _scheduled_count(organization_id=org_id, channel_id=channel_id)
            ch_created = 0
            need = max(0, min_depth - ch_before)
            while need > 0 and slots > 0 and candidate_entries:
                entry = pick_pool_entry(local) or candidate_entries[entry_idx % len(candidate_entries)]
                entry_idx += 1
                from app.services.buffer_x_promo_image import direct_url_for_buffer, pick_promo_image

                text = build_native_queue_caption(entry, db=local, advance_link_cycle=True)
                try:
                    from app.services.creative_rag import search_creative

                    prompt_rows = search_creative(
                        local,
                        entry_type="image_prompt",
                        surface="x_buffer",
                        query=str(entry.get("category") or ""),
                        limit=1,
                    )
                    if prompt_rows and prompt_rows[0].catalog_key:
                        from app.services.template_expand import expand_template_tokens

                        teaser = expand_template_tokens(
                            f" {{prompt_teaser:{prompt_rows[0].catalog_key}}}",
                            db=local,
                            for_x=True,
                        )
                        if teaser.strip() and len(text) + len(teaser) <= 280:
                            text = text.rstrip() + teaser
                except Exception:
                    logger.debug("native refill creative_rag teaser skip", exc_info=True)
                if not _caption_allowed_for_x(text):
                    need -= 1
                    continue
                image_url = direct_url_for_buffer(pick_promo_image())
                res = create_post(
                    channel_id,
                    text,
                    mode="addToQueue",
                    scheduling_type="automatic",
                    image_url=image_url,
                )
                if buffer_create_post_succeeded(res):
                    ch_created += 1
                    report["created"] += 1
                    slots -= 1
                    need -= 1
                    exclude.add(_normalize_text_key(text))
                    pick_affiliate(local, "x_buffer", advance=True)
                    local.commit()
                    if len(report["captions_preview"]) < 5:
                        report["captions_preview"].append(text[:120])
                else:
                    msg = buffer_create_post_error_message(res) or "createPost failed"
                    report["errors"].append(msg[:200])
                    logger.warning("buffer native refill createPost: %s", msg)
                    break
            report["by_channel"][channel_id] = {
                "scheduled_before": ch_before,
                "created": ch_created,
            }

        if slots > 0 and ig_channels:
            from app.services.buffer_ig_carousel import ig_create_post_kwargs
            from app.services.buffer_surface_caption import build_instagram_caption
            from app.services.buffer_x_promo_image import direct_url_for_buffer, pick_promo_image

            ig_caption = build_instagram_caption(utm_campaign="native_ig_stock")
            for channel_id in ig_channels:
                if slots <= 0:
                    break
                ch_before = _scheduled_count(organization_id=org_id, channel_id=channel_id)
                ig_need = max(0, min(2, min_depth) - ch_before)
                ig_created = 0
                while ig_need > 0 and slots > 0:
                    ig_kwargs = ig_create_post_kwargs()
                    if not ig_kwargs.get("image_url") and not ig_kwargs.get("assets"):
                        fallback = direct_url_for_buffer(pick_promo_image())
                        if fallback:
                            ig_kwargs["image_url"] = fallback
                    res = create_post(
                        channel_id,
                        ig_caption,
                        mode="addToQueue",
                        scheduling_type="automatic",
                        **ig_kwargs,
                    )
                    if buffer_create_post_succeeded(res):
                        ig_created += 1
                        report["created"] += 1
                        slots -= 1
                        ig_need -= 1
                    else:
                        msg = buffer_create_post_error_message(res) or "createPost failed"
                        report["errors"].append(msg[:200])
                        break
                report["by_channel"][channel_id] = {
                    "scheduled_before": ch_before,
                    "created": ig_created,
                    "surface": "instagram",
                }
    except BufferRateLimitError as e:
        report["status"] = "skipped"
        report["reason"] = "rate_limited"
        report["retry_after_s"] = e.retry_after_s
    finally:
        local.close()

    report["org_scheduled_after"] = org_scheduled + report["created"]
    logger.info("buffer native queue refill: %s", report)
    return report
