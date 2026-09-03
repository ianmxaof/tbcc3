"""Digital pack browser — single-message catalog, spoiler previews, paywall, delivery."""

from __future__ import annotations

import html
import logging
import re
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, InputMediaPhoto, Update
from telegram.ext import ContextTypes

from app.services.bundle_storage import bundle_zip2_path, bundle_zip_nth_path, bundle_zip_path
from bots.payment_ui import (
    BACK_BUTTON,
    clear_preview_album,
    render_payment_ui,
    set_album_message_ids,
)

logger = logging.getLogger(__name__)

PB_CATALOG = "pb:cat"
PREVIEW_PAGE_SIZE = 10


def parse_pack_start_payload(payload: str) -> int | None:
    """Deep links: pack_12, pack12, pack-12."""
    raw = (payload or "").strip().lower()
    if not raw.startswith("pack"):
        return None
    rest = raw[4:].lstrip("_-")
    if rest.isdigit():
        return int(rest)
    m = re.match(r"^[_-]?(\d+)$", raw[4:])
    if m:
        return int(m.group(1))
    return None


def user_owns_plan(active_subs: list[dict], plan_id: int) -> bool:
    pid = int(plan_id)
    for sub in active_subs:
        if str(sub.get("status") or "").lower() != "active":
            continue
        try:
            if int(sub.get("plan_id") or 0) == pid:
                return True
        except (TypeError, ValueError):
            continue
    return False


def pack_zip_part_count(plan: dict) -> int:
    parts = plan.get("bundle_zip_parts")
    if isinstance(parts, list) and parts:
        return len([p for p in parts if isinstance(p, str) and p.strip()])
    count = 0
    if plan.get("bundle_zip1_available") or plan.get("bundle_zip_available"):
        count += 1
    if plan.get("bundle_zip2_available"):
        count += 1
    try:
        n = int(plan.get("bundle_zip_part_count") or 0)
        if n > count:
            return n
    except (TypeError, ValueError):
        pass
    return count


def pack_summary(plan: dict) -> dict[str, int]:
    raw = plan.get("pack_asset_summary")
    if isinstance(raw, dict):
        return {
            "image": int(raw.get("image") or 0),
            "video": int(raw.get("video") or 0),
            "other": int(raw.get("other") or 0),
            "total": int(raw.get("total") or 0),
            "previews": int(raw.get("previews") or 0),
        }
    return {"image": 0, "video": 0, "other": 0, "total": 0, "previews": 0}


def pack_stats_line(plan: dict) -> str:
    summary = pack_summary(plan)
    bits: list[str] = []
    if summary["video"]:
        bits.append(f"{summary['video']} video{'s' if summary['video'] != 1 else ''}")
    if summary["image"]:
        bits.append(f"{summary['image']} image{'s' if summary['image'] != 1 else ''}")
    if summary["total"]:
        bits.append(f"Total: {summary['total']} files")
    if not bits:
        zips = pack_zip_part_count(plan)
        if zips:
            bits.append(f"{zips} zip{'s' if zips != 1 else ''}")
        promos = len(_promo_urls(plan))
        if promos:
            bits.append(f"{promos} promo{'s' if promos != 1 else ''}")
    stars = int(plan.get("price_stars") or 0)
    if stars > 0:
        bits.append(f"{stars} ⭐")
    return " · ".join(bits) if bits else "Digital pack"


def _normalize_kind_filter(raw: str | None) -> str:
    val = (raw or "a").strip().lower()
    if val in ("all", "a", ""):
        return "a"
    if val in ("image", "i", "images"):
        return "i"
    if val in ("video", "v", "videos"):
        return "v"
    return "a"


def parse_pack_browser_callback(data: str) -> dict[str, Any] | None:
    if not data or not data.startswith("pb:"):
        return None
    if data == PB_CATALOG:
        return {"action": "catalog"}
    m = re.match(r"^pb:d:(\d+)$", data)
    if m:
        return {"action": "detail", "plan_id": int(m.group(1)), "page": 0, "filter": "a"}
    m = re.match(r"^pb:pv:(\d+):(\d+)(?::([aiv]))?$", data)
    if m:
        return {
            "action": "preview",
            "plan_id": int(m.group(1)),
            "page": int(m.group(2)),
            "filter": _normalize_kind_filter(m.group(3)),
        }
    m = re.match(r"^pb:dl:(\d+)$", data)
    if m:
        return {"action": "download", "plan_id": int(m.group(1))}
    return None


def _promo_urls(plan: dict) -> list[str]:
    from bots.payment_bot import _plan_promo_urls

    return _plan_promo_urls(plan)


def _truncate_btn(s: str, max_len: int = 64) -> str:
    from bots.payment_bot import _truncate_btn as tb

    return tb(s, max_len)


def _owned_plan_ids(active_subs: list[dict]) -> set[int]:
    out: set[int] = set()
    for sub in active_subs:
        if str(sub.get("status") or "").lower() != "active":
            continue
        try:
            out.add(int(sub.get("plan_id") or 0))
        except (TypeError, ValueError):
            continue
    out.discard(0)
    return out


def _catalog_keyboard(bundles: list[dict], owned: set[int]) -> InlineKeyboardMarkup:
    row: list[InlineKeyboardButton] = []
    rows: list[list[InlineKeyboardButton]] = []
    for p in bundles[:100]:
        pid = int(p["id"])
        name = str(p.get("name") or f"Pack #{pid}")
        prefix = "✅ " if pid in owned else "🔒 "
        stars = int(p.get("price_stars") or 0)
        label = f"{prefix}{name}"
        if stars and len(label) < 52:
            label = f"{label} · {stars}⭐"
        row.append(
            InlineKeyboardButton(
                _truncate_btn(label, 64),
                callback_data=f"pb:d:{pid}",
            )
        )
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([BACK_BUTTON])
    return InlineKeyboardMarkup(rows)


def _detail_nav_row(*, owned: bool) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton("◀ All packs", callback_data=PB_CATALOG),
        BACK_BUTTON,
    ]


def _detail_keyboard(
    plan: dict,
    *,
    owned: bool,
    page: int,
    page_count: int,
    kind_filter: str,
    summary: dict[str, int],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    pid = int(plan["id"])
    filt = _normalize_kind_filter(kind_filter)
    dl_count = summary.get("total") or pack_zip_part_count(plan)
    if owned:
        if dl_count > 0:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"📥 Get all ({dl_count})",
                        callback_data=f"pb:dl:{pid}",
                    )
                ]
            )
    else:
        from bots.payment_bot import _plan_checkout_keyboard_rows

        rows.extend(_plan_checkout_keyboard_rows([plan], pack=True))
    if summary.get("video") and summary.get("image"):
        rows.append(
            [
                InlineKeyboardButton(
                    f"All ({summary.get('total', 0)})",
                    callback_data=f"pb:pv:{pid}:0:a",
                ),
                InlineKeyboardButton(
                    f"Videos ({summary.get('video', 0)})",
                    callback_data=f"pb:pv:{pid}:0:v",
                ),
                InlineKeyboardButton(
                    f"Images ({summary.get('image', 0)})",
                    callback_data=f"pb:pv:{pid}:0:i",
                ),
            ]
        )
    if page_count > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"pb:pv:{pid}:{page - 1}:{filt}"))
        nav.append(InlineKeyboardButton(f"[{page + 1}/{page_count}]", callback_data=f"pb:d:{pid}"))
        if page + 1 < page_count:
            nav.append(InlineKeyboardButton("Next ▶", callback_data=f"pb:pv:{pid}:{page + 1}:{filt}"))
        rows.append(nav)
    rows.append(_detail_nav_row(owned=owned))
    return InlineKeyboardMarkup(rows)


def _detail_html(
    plan: dict,
    *,
    owned: bool,
    page: int,
    page_count: int,
    preview_count: int,
    kind_filter: str,
    summary: dict[str, int],
) -> str:
    name = html.escape(str(plan.get("name") or "Pack"))
    stats = html.escape(pack_stats_line(plan))
    from bots.payment_bot import _pick_display_description

    desc = _pick_display_description(plan)
    lines = [f"<b>{name}</b>"]
    if owned:
        lines.append("✅ <b>Unlocked</b> — your files are ready.")
    else:
        lines.append("🔒 <b>Preview</b> — unlock to download.")
    lines.append(stats)
    filt = _normalize_kind_filter(kind_filter)
    if filt == "v" and summary.get("video") and preview_count == 0:
        lines.append(
            f"<i>🎬 {summary['video']} video{'s' if summary['video'] != 1 else ''} in pack — "
            f"{'download below' if owned else 'unlock to download'}.</i>"
        )
    elif preview_count:
        if page_count > 1:
            start = page * PREVIEW_PAGE_SIZE + 1
            end = min((page + 1) * PREVIEW_PAGE_SIZE, preview_count)
            lines.append(f"<i>Preview {start}–{end} of {preview_count}</i>")
        elif not owned:
            lines.append("<i>Spoiler previews above — tap to peek.</i>")
    if desc:
        lines.append(html.escape(desc[:600]))
    if not owned:
        stars = int(plan.get("price_stars") or 0)
        if stars:
            lines.append(f"\nUnlock for <b>{stars} ⭐</b> or crypto below.")
    return "\n".join(lines)


def _catalog_html(bundles: list[dict], owned: set[int]) -> str:
    total = len(bundles)
    unlocked = sum(1 for p in bundles if int(p.get("id") or 0) in owned)
    lines = [
        "📦 <b>Digital packs</b>",
        "",
        f"<b>{total}</b> pack{'s' if total != 1 else ''} in catalog"
        + (f" · <b>{unlocked}</b> unlocked for you" if unlocked else ""),
        "",
        "Pick a pack — preview, then unlock to download privately in this chat.",
    ]
    if total > 100:
        lines.append(f"\n<i>Showing first 100 of {total} packs.</i>")
    return "\n".join(lines)


async def fetch_pack_assets(plan_id: int, *, preview_only: bool = False) -> dict:
    import os

    import httpx

    api_base = os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{api_base}/subscription-plans/{int(plan_id)}/pack-assets",
                params={"preview_only": preview_only},
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning("fetch_pack_assets(%s) failed: %s", plan_id, e)
    return {"plan_id": plan_id, "summary": pack_summary({}), "assets": []}


def _assets_for_filter(assets: list[dict], kind_filter: str, *, preview_only: bool) -> list[dict]:
    filt = _normalize_kind_filter(kind_filter)
    out: list[dict] = []
    for row in assets:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "other").lower()
        if preview_only and not row.get("preview_url"):
            continue
        if filt == "a":
            if preview_only and not row.get("preview_url"):
                continue
            out.append(row)
        elif filt == "i" and kind == "image":
            out.append(row)
        elif filt == "v" and kind == "video":
            out.append(row)
    return out


async def _resolve_promo_photos(plan: dict) -> list[Any]:
    from bots.payment_bot import _resolve_bundle_promo_photo

    resolved: list[Any] = []
    for u in _promo_urls(plan):
        ph = await _resolve_bundle_promo_photo(u)
        if ph is not None:
            resolved.append(ph)
    return resolved


async def _resolve_preview_media(plan: dict, assets: list[dict]) -> list[Any]:
    from bots.payment_bot import _resolve_bundle_promo_photo

    resolved: list[Any] = []
    for row in assets:
        url = str(row.get("preview_url") or "").strip()
        if url:
            ph = await _resolve_bundle_promo_photo(url)
            if ph is not None:
                resolved.append(ph)
    if resolved:
        return resolved
    return await _resolve_promo_photos(plan)


async def _send_preview_album(
    *,
    bot,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    plan: dict,
    owned: bool,
    page: int,
    preview_media: list[Any],
) -> int:
    if not preview_media:
        return 1
    page_count = max(1, (len(preview_media) + PREVIEW_PAGE_SIZE - 1) // PREVIEW_PAGE_SIZE)
    page = max(0, min(page, page_count - 1))
    chunk = preview_media[page * PREVIEW_PAGE_SIZE : (page + 1) * PREVIEW_PAGE_SIZE]
    if not chunk:
        return page_count
    spoiler = not owned
    media: list[InputMediaPhoto] = []
    for i, ph in enumerate(chunk):
        if i == 0:
            cap = html.escape(str(plan.get("name") or "Pack"))
            media.append(
                InputMediaPhoto(
                    media=ph,
                    caption=cap,
                    parse_mode="HTML",
                    has_spoiler=spoiler,
                )
            )
        else:
            media.append(InputMediaPhoto(media=ph, has_spoiler=spoiler))
    try:
        msgs = await bot.send_media_group(chat_id=chat_id, media=media)
        set_album_message_ids(
            context,
            chat_id=chat_id,
            message_ids=[m.message_id for m in msgs],
        )
    except Exception as e:
        logger.warning("pack preview album failed plan_id=%s: %s", plan.get("id"), e)
    return page_count


async def show_pack_catalog(
    msg,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    edit_message=None,
    user_id: int | None = None,
) -> None:
    from bots.payment_bot import fetch_bundles, fetch_user_subscriptions

    if not msg:
        return
    chat_id = msg.chat_id
    await clear_preview_album(context.bot, context, chat_id=chat_id)
    bundles = await fetch_bundles()
    uid = user_id
    if uid is None and getattr(msg, "from_user", None):
        uid = msg.from_user.id
    owned: set[int] = set()
    if uid:
        subs = await fetch_user_subscriptions(int(uid))
        owned = _owned_plan_ids([s for s in subs if s.get("status") == "active"])
    if not bundles:
        await render_payment_ui(
            bot=context.bot,
            chat_id=chat_id,
            context=context,
            text=(
                "📦 <b>Digital packs</b>\n\n"
                "No <b>bundle</b> products yet. Create them in the dashboard as "
                "<b>Bundle (digital pack)</b> with Stars pricing."
            ),
            reply_markup=InlineKeyboardMarkup([[BACK_BUTTON]]),
            parse_mode="HTML",
            edit_message=edit_message,
            include_back=False,
        )
        return
    await render_payment_ui(
        bot=context.bot,
        chat_id=chat_id,
        context=context,
        text=_catalog_html(bundles, owned),
        reply_markup=_catalog_keyboard(bundles, owned),
        parse_mode="HTML",
        edit_message=edit_message,
        include_back=False,
    )


async def show_pack_detail(
    msg,
    context: ContextTypes.DEFAULT_TYPE,
    plan: dict,
    *,
    edit_message=None,
    user_id: int | None = None,
    page: int = 0,
    kind_filter: str = "a",
) -> None:
    from bots.payment_bot import fetch_user_subscriptions

    if not msg:
        return
    chat_id = msg.chat_id
    uid = user_id
    if uid is None and getattr(msg, "from_user", None):
        uid = msg.from_user.id
    owned = False
    if uid:
        subs = await fetch_user_subscriptions(int(uid))
        owned = user_owns_plan(subs, int(plan["id"]))
    asset_payload = await fetch_pack_assets(int(plan["id"]), preview_only=False)
    summary_raw = asset_payload.get("summary")
    if isinstance(summary_raw, dict):
        summary = {
            "image": int(summary_raw.get("image") or 0),
            "video": int(summary_raw.get("video") or 0),
            "other": int(summary_raw.get("other") or 0),
            "total": int(summary_raw.get("total") or 0),
            "previews": int(summary_raw.get("previews") or 0),
        }
    else:
        summary = pack_summary(plan)
    if summary.get("total"):
        plan = {**plan, "pack_asset_summary": summary}
    filt = _normalize_kind_filter(kind_filter)
    assets = asset_payload.get("assets") if isinstance(asset_payload.get("assets"), list) else []
    filtered = _assets_for_filter(assets, filt, preview_only=True)
    await clear_preview_album(context.bot, context, chat_id=chat_id)
    preview_media = await _resolve_preview_media(plan, filtered)
    page_count = await _send_preview_album(
        bot=context.bot,
        chat_id=chat_id,
        context=context,
        plan=plan,
        owned=owned,
        page=page,
        preview_media=preview_media,
    )
    text = _detail_html(
        plan,
        owned=owned,
        page=page,
        page_count=page_count,
        preview_count=len(preview_media),
        kind_filter=filt,
        summary=summary,
    )
    await render_payment_ui(
        bot=context.bot,
        chat_id=chat_id,
        context=context,
        text=text,
        reply_markup=_detail_keyboard(
            plan,
            owned=owned,
            page=page,
            page_count=page_count,
            kind_filter=filt,
            summary=summary,
        ),
        parse_mode="HTML",
        edit_message=edit_message,
        include_back=False,
    )


async def deliver_pack_zips(
    *,
    bot,
    chat_id: int,
    plan: dict,
    user_id: int,
) -> tuple[int, str | None]:
    """Send zip parts for an owned pack. Returns (sent_count, error_message)."""
    from bots.payment_bot import fetch_user_subscriptions

    subs = await fetch_user_subscriptions(user_id)
    if not user_owns_plan(subs, int(plan["id"])):
        return 0, "Unlock this pack first."

    plan_id = int(plan["id"])
    sent = 0
    parts = plan.get("bundle_zip_parts")
    if isinstance(parts, list) and parts:
        total = len(parts)
        for i, fn in enumerate(parts):
            if not isinstance(fn, str) or not fn.strip():
                continue
            zp = bundle_zip_nth_path(plan_id, i)
            if not zp.is_file():
                continue
            disp = fn.strip()[:250]
            cap = f"📦 Part {i + 1} of {total}" if total > 1 else "📦 Your digital pack"
            try:
                await bot.send_document(chat_id=chat_id, document=InputFile(zp), filename=disp, caption=cap)
                sent += 1
            except Exception as e:
                logger.warning("pack_browser zip part %s failed: %s", i, e)
    else:
        zp = bundle_zip_path(plan_id)
        z2p = bundle_zip2_path(plan_id)
        if zp.is_file() and (plan.get("bundle_zip_original_name") or "").strip():
            fn = (plan.get("bundle_zip_original_name") or f"pack_{plan_id}.zip")[:250]
            both = z2p.is_file() and (plan.get("bundle_zip2_original_name") or "").strip()
            try:
                await bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(zp),
                    filename=fn,
                    caption="📦 Part 1 of 2" if both else "📦 Your digital pack",
                )
                sent += 1
            except Exception as e:
                logger.warning("pack_browser zip1 failed: %s", e)
        if z2p.is_file() and (plan.get("bundle_zip2_original_name") or "").strip():
            fn2 = (plan.get("bundle_zip2_original_name") or f"pack_{plan_id}_2.zip")[:250]
            try:
                await bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(z2p),
                    filename=fn2,
                    caption="📦 Part 2 of 2",
                )
                sent += 1
            except Exception as e:
                logger.warning("pack_browser zip2 failed: %s", e)
    if sent == 0:
        if not plan.get("bundle_zip_available"):
            return 0, "No zip files uploaded for this pack yet."
        return 0, "Could not send files — try again later."
    return sent, None


async def handle_pack_browser_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    parsed = parse_pack_browser_callback(query.data)
    if not parsed:
        return
    msg = query.message
    user = query.from_user
    if not msg or not user:
        await query.answer()
        return

    action = parsed["action"]
    if action == "catalog":
        await query.answer()
        await show_pack_catalog(msg, context, edit_message=msg, user_id=user.id)
        return

    plan_id = int(parsed["plan_id"])
    from bots.payment_bot import fetch_plan_by_id

    plan = await fetch_plan_by_id(plan_id)
    if not plan or (plan.get("product_type") or "").lower() != "bundle":
        await query.answer("Pack not found.", show_alert=True)
        return

    if action == "download":
        await query.answer("Sending files…")
        n, err = await deliver_pack_zips(bot=context.bot, chat_id=msg.chat_id, plan=plan, user_id=user.id)
        if err:
            await query.answer(err, show_alert=True)
        elif n:
            await query.answer(f"Sent {n} file{'s' if n != 1 else ''}.")
        return

    if action in ("detail", "preview"):
        page = int(parsed.get("page") or 0)
        filt = _normalize_kind_filter(parsed.get("filter"))
        await query.answer()
        await show_pack_detail(
            msg,
            context,
            plan,
            edit_message=msg,
            user_id=user.id,
            page=page,
            kind_filter=filt,
        )
