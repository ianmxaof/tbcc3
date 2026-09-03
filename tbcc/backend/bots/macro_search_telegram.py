"""
Telegram macro model search — extension parity in the payment bot DM + dedicated macro bot.

Commands: /macrosearch, /videofind (alias), /find (archive), /recent, /macroaddsource (admin), /macrolist (admin)
Deep links: /start ms_<username> or vf_<username>

UX mirrors the OnlyFans username-search overlay: category chips, hit cards with Open buttons,
recent history. Archive keyword search runs first when enabled; external SEO is the fallback.
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import re
from typing import Any, Awaitable, Callable

import httpx
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.services.model_search_engine import (
    analyze_model_search_html,
    build_model_search_url,
    derive_username_template_from_search_url,
    extract_video_links_from_html,
    get_model_search_sites_for_mode,
    new_custom_site_id,
    validate_custom_source_url,
)
from bots.macro_search_overlay_ui import (
    category_chip_keyboard,
    hit_open_keyboard,
    history_keyboard,
    list_search_history,
    macro_overlay_reply_keyboard,
    normalize_search_category,
    parse_category_and_query,
    push_search_history,
    reply_label_action,
)

logger = logging.getLogger(__name__)

MACRO_SEARCH_CONCURRENCY = 8

(MS_ADD_URL, MS_ADD_USER, MS_ADD_NAME) = range(3)

_GetSettings = Callable[[], Awaitable[dict[str, Any]]]
_PatchCustomSources = Callable[[list[dict[str, Any]]], Awaitable[bool]]


def normalize_macro_username(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("@"):
        s = s[1:]
    s = re.sub(r"^[^\w]+|[^\w.-]+$", "", s)
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", s or ""):
        return ""
    return s


def admin_user_id() -> int | None:
    raw = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def is_admin(user_id: int | None) -> bool:
    aid = admin_user_id()
    return aid is not None and user_id is not None and user_id == aid


def resolve_sources_for_mode(st: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    """Prefer dashboard-configured macro list for macro mode; otherwise filter full catalog."""
    mode_n = normalize_search_category(mode)
    custom = st.get("macro_search_custom_sources")
    if not isinstance(custom, list):
        custom = []
    disabled_raw = st.get("macro_search_disabled_ids")
    disabled: set[str] = set()
    if isinstance(disabled_raw, list):
        disabled = {str(x) for x in disabled_raw if x}
    if mode_n == "macro":
        sources = st.get("macro_search_sources") or []
        if sources:
            return list(sources)
    return get_model_search_sites_for_mode(
        mode=mode_n,
        custom_sites=custom,
        disabled_ids=disabled,
    )


async def probe_macro_site(
    client: httpx.AsyncClient,
    site: dict[str, Any],
    username: str,
) -> dict[str, Any]:
    search_url = build_model_search_url(str(site.get("url") or ""), username)
    out: dict[str, Any] = {
        "site": site,
        "search_url": search_url,
        "has_results": False,
        "count": 0,
        "fetch_status": "err",
        "reason": "err",
        "html": "",
        "final_url": search_url,
    }
    try:
        r = await client.get(search_url)
        text = r.text or ""
        out["html"] = text
        out["final_url"] = str(r.url) if r.url else search_url
        out["fetch_status"] = "ok" if r.is_success else f"http_{r.status_code}"
        analysis = analyze_model_search_html(text, out["final_url"], username=username)
        if not r.is_success and analysis.get("reason") == "none":
            analysis = {**analysis, "reason": out["fetch_status"]}
        out["has_results"] = bool(analysis.get("has_results"))
        out["count"] = int(analysis.get("count") or 0)
        out["reason"] = analysis.get("reason") or "none"
        out["confidence"] = analysis.get("confidence") or "none"
        out["signal"] = analysis.get("signal") or "none"
    except Exception as e:
        logger.debug("macro probe failed %s: %s", site.get("id"), e)
    return out


async def run_macro_search(
    username: str,
    sources: list[dict[str, Any]],
    max_links: int,
) -> list[dict[str, Any]]:
    """Probe all sources; return hits with video links or labeled probe-only rows."""
    sem = asyncio.Semaphore(MACRO_SEARCH_CONCURRENCY)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=headers) as client:

        async def one(site: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                return await probe_macro_site(client, site, username)

        rows = await asyncio.gather(*[one(s) for s in sources])

    hits: list[dict[str, Any]] = []
    user_lc = username.lower()
    for row in rows:
        site = row["site"]
        html_text = row.get("html") or ""
        links: list[str] = []
        if html_text:
            links = extract_video_links_from_html(
                html_text,
                row.get("final_url") or row["search_url"],
                site,
                username,
                max_links,
            )
        if links:
            hits.append(
                {
                    "site_id": site.get("id"),
                    "name": site.get("name"),
                    "search_url": row["search_url"],
                    "count": len(links),
                    "links": links,
                    "kind": "links",
                    "category": site.get("category"),
                    "reason": row.get("reason"),
                    "fetch_status": row.get("fetch_status"),
                    "signal": row.get("signal"),
                }
            )
            continue
        if not row.get("has_results") or int(row.get("count") or 0) <= 0:
            continue
        if user_lc not in html_text.lower():
            continue
        if (row.get("confidence") or "none") == "none":
            continue
        hits.append(
            {
                "site_id": site.get("id"),
                "name": site.get("name"),
                "search_url": row["search_url"],
                "count": row.get("count"),
                "links": [],
                "kind": "probe",
                "category": site.get("category"),
                "reason": row.get("reason"),
                "fetch_status": row.get("fetch_status"),
                "signal": row.get("signal"),
            }
        )
    hits.sort(
        key=lambda h: (
            0 if h.get("kind") == "links" else 1,
            -int(h.get("count") or 0),
            str(h.get("name") or ""),
        )
    )
    return hits


async def send_macro_search_results(
    update: Update,
    username: str,
    hits: list[dict[str, Any]],
    scanned: int,
    *,
    category: str = "macro",
) -> None:
    """Overlay-style report: summary + Open buttons + category chips (not raw URL walls)."""
    msg = update.effective_message
    if not msg:
        return
    cat_label = {
        "macro": "Macro",
        "onlyfans": "OnlyFans",
        "livecams": "Live cams",
        "videos": "Videos",
        "all": "All sources",
    }.get(category, category)
    chips = category_chip_keyboard(username, active=category)

    if not hits:
        await msg.reply_text(
            f"No real hits on <b>{scanned}</b> {html.escape(cat_label)} source(s) for "
            f"<b>@{html.escape(username)}</b>.\n"
            "<i>Sites with only search-box echoes are hidden — same as the browser overlay.</i>",
            parse_mode="HTML",
            reply_markup=chips,
        )
        return

    link_hits = sum(1 for h in hits if h.get("kind") == "links")
    probe_hits = sum(1 for h in hits if h.get("kind") == "probe")
    total_est = sum(int(h.get("count") or 0) for h in hits)
    await msg.reply_text(
        f"<b>{html.escape(cat_label)} search</b> — <b>{len(hits)}</b> hit(s) for "
        f"<b>@{html.escape(username)}</b>\n"
        f"{link_hits} with video URLs · {probe_hits} probe-only · ~{total_est} estimated\n"
        f"<i>{scanned} source(s) scanned</i>",
        parse_mode="HTML",
        reply_markup=chips,
    )

    lines: list[str] = []
    for i, h in enumerate(hits[:12], 1):
        name = html.escape(str(h.get("name") or h.get("site_id") or "source"))
        kind = "🎬" if h.get("kind") == "links" else "🔎"
        cnt = h.get("count") or 0
        lines.append(f"{i}. {kind} <b>{name}</b> · {cnt}")
    if len(hits) > 12:
        lines.append(f"… +{len(hits) - 12} more")
    open_kb = hit_open_keyboard(hits)
    await msg.reply_text(
        "<b>Hits</b> — tap Open to visit the search page:\n" + "\n".join(lines),
        parse_mode="HTML",
        reply_markup=open_kb,
        disable_web_page_preview=True,
    )

    video_lines: list[str] = []
    for h in hits:
        if h.get("kind") != "links":
            continue
        name = html.escape(str(h.get("name") or "source"))
        for u in (h.get("links") or [])[:3]:
            video_lines.append(f"• <b>{name}</b> — {html.escape(u)}")
        if len(video_lines) >= 12:
            break
    if video_lines:
        await msg.reply_text(
            "<b>Direct video URLs</b>\n" + "\n".join(video_lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


async def _run_external_macro_probe(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    get_settings: _GetSettings,
    query: str,
    category: str,
    status_msg=None,
) -> None:
    from app.services.aof_macro_search_router import macro_fallback_username

    user = update.effective_user
    msg = update.effective_message
    if not msg:
        return

    username = macro_fallback_username(query)
    if not username:
        username = normalize_macro_username(query)
    if not username:
        text = (
            f"<code>{html.escape(query[:80])}</code> is not a valid model username.\n"
            "Try <code>/macrosearch of:modelname</code> or tap a category chip."
        )
        if status_msg:
            await status_msg.edit_text(text, parse_mode="HTML")
        else:
            await msg.reply_text(text, parse_mode="HTML")
        return

    st = await get_settings()
    if not bool(st.get("video_finder_enabled", True)):
        await msg.reply_text("Macro search is disabled in bot settings.")
        return
    sources = resolve_sources_for_mode(st, category)
    if not sources:
        await msg.reply_text(
            f"No sources configured for category <code>{html.escape(category)}</code>.",
            parse_mode="HTML",
        )
        return
    max_links = int(st.get("video_finder_max_links_per_source") or 8)
    cat_label = category.replace("_", " ")
    progress = (
        f"🔎 {html.escape(cat_label.title())} probe for <b>@{html.escape(username)}</b> — "
        f"{len(sources)} source(s)…"
    )
    if status_msg:
        await status_msg.edit_text(progress, parse_mode="HTML")
    else:
        status_msg = await msg.reply_text(progress, parse_mode="HTML")

    hits = await run_macro_search(username, sources, max_links)
    try:
        await status_msg.delete()
    except Exception:
        pass
    await send_macro_search_results(update, username, hits, len(sources), category=category)
    if user:
        push_search_history(int(user.id), query=username, category=category)
    if hits:
        await msg.reply_text(
            f"Done. {len(hits)} site(s) with hits for @{username}.",
            disable_web_page_preview=True,
            reply_markup=macro_overlay_reply_keyboard(),
        )


async def cmd_macrosearch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    get_settings: _GetSettings,
    force_category: str | None = None,
) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg:
        return
    args = list(context.args or [])
    if not args and not force_category:
        await msg.reply_text(
            "<b>Macrosearch</b> — Telegram twin of the OnlyFans overlay\n\n"
            "<b>1)</b> AOF archive first (tags / emoji) → DM album\n"
            "<b>2)</b> Else probe external sources (hits only + Open buttons)\n\n"
            "<b>Examples</b>\n"
            "• <code>/macrosearch modelname</code> — Macro family\n"
            "• <code>/macrosearch of:modelname</code> — OnlyFans family\n"
            "• <code>/macrosearch cams:modelname</code> — Live cams\n"
            "• <code>/macrosearch videos:modelname</code> — Videos\n"
            "• <code>/find milf pawg</code> — archive keywords only\n\n"
            "Use the keyboard chips or /recent for history.",
            parse_mode="HTML",
            reply_markup=macro_overlay_reply_keyboard(),
        )
        return

    category, query = parse_category_and_query(args)
    if force_category:
        category = normalize_search_category(force_category)
        if not query and args:
            query = " ".join(args).strip()
    if not query:
        context.user_data["ms_pending_cat"] = category
        await msg.reply_text(
            f"Category set to <b>{html.escape(category)}</b>.\n"
            "Send a username (or <code>/macrosearch &lt;user&gt;</code>).",
            parse_mode="HTML",
            reply_markup=macro_overlay_reply_keyboard(),
        )
        return

    from app.services.aof_macro_search_router import macro_search_aof_first_enabled

    if macro_search_aof_first_enabled() and user and category == "macro":
        status_msg = await msg.reply_text(
            f"🔎 Checking <b>AOF archive</b> for <i>{html.escape(query[:120])}</i>…",
            parse_mode="HTML",
        )
        try:
            from bots.macro_search_aof_bridge import try_aof_archive_delivery

            archive_out = await asyncio.to_thread(try_aof_archive_delivery, int(user.id), query)
        except Exception as e:
            logger.warning("archive search bridge failed: %s", e)
            archive_out = {"ok": False, "reason": "bridge_error"}
        if archive_out.get("ok"):
            await status_msg.edit_text(
                archive_out.get("summary_html") or "<b>Archive results sent to your DM.</b>",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return
        await status_msg.edit_text(
            "No archive hit — probing <b>external</b> sources…",
            parse_mode="HTML",
        )
        await _run_external_macro_probe(
            update,
            context,
            get_settings=get_settings,
            query=query,
            category=category,
            status_msg=status_msg,
        )
        return

    await _run_external_macro_probe(
        update, context, get_settings=get_settings, query=query, category=category
    )


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    entries = list_search_history(int(user.id))
    if not entries:
        await msg.reply_text(
            "No recent searches yet. Try /macrosearch &lt;username&gt;.",
            parse_mode="HTML",
            reply_markup=macro_overlay_reply_keyboard(),
        )
        return
    kb = history_keyboard(entries)
    await msg.reply_text(
        "<b>Recent searches</b> — tap to re-run:",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def on_macro_overlay_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    get_settings: _GetSettings,
) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("ms:"):
        return
    await query.answer()
    parts = query.data.split(":", 3)
    if len(parts) < 3:
        return
    kind = parts[1]
    if kind == "cat" and len(parts) >= 4:
        cat, username = parts[2], parts[3]
        context.args = [f"{cat}:{username}"]
        await cmd_macrosearch(update, context, get_settings=get_settings)
        return
    if kind == "hist" and len(parts) >= 4:
        cat, username = parts[2], parts[3]
        context.args = [f"{cat}:{username}"]
        await cmd_macrosearch(update, context, get_settings=get_settings)


async def on_macro_overlay_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    get_settings: _GetSettings,
) -> None:
    """Reply-keyboard chips + bare username when a category is pending."""
    msg = update.effective_message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    action = reply_label_action(text)
    if action == "search":
        context.user_data["ms_pending_cat"] = "macro"
        await msg.reply_text(
            "Send a <b>username</b> to probe macro sources.\n"
            "Or <code>/macrosearch of:name</code> for OnlyFans family.",
            parse_mode="HTML",
            reply_markup=macro_overlay_reply_keyboard(),
        )
        return
    if action == "archive":
        from bots.aof_search_telegram import cmd_find

        context.args = []
        await cmd_find(update, context, bot_kind="macro")
        return
    if action == "recent":
        await cmd_recent(update, context)
        return
    if action in ("onlyfans", "livecams", "videos"):
        context.user_data["ms_pending_cat"] = action
        await msg.reply_text(
            f"Category <b>{html.escape(action)}</b> — send a username.",
            parse_mode="HTML",
            reply_markup=macro_overlay_reply_keyboard(),
        )
        return

    if not text.startswith("/"):
        from bots.aof_search_telegram import consume_find_pending_lane_text

        if await consume_find_pending_lane_text(update, context, bot_kind="macro"):
            return

    pending = (context.user_data or {}).get("ms_pending_cat")
    if pending and not text.startswith("/"):
        context.user_data.pop("ms_pending_cat", None)
        context.args = [f"{pending}:{text}"]
        await cmd_macrosearch(update, context, get_settings=get_settings)
        return

    if not text.startswith("/") and normalize_macro_username(text):
        context.args = [text]
        await cmd_macrosearch(update, context, get_settings=get_settings)


async def _fetch_settings_overrides(get_settings: _GetSettings) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    st = await get_settings()
    custom = st.get("macro_search_custom_sources")
    if not isinstance(custom, list):
        custom = []
    disabled_raw = st.get("macro_search_disabled_ids")
    disabled: dict[str, bool] = {}
    if isinstance(disabled_raw, list):
        for sid in disabled_raw:
            disabled[str(sid)] = False
    return custom, disabled


async def _append_custom_source(
    patch_custom: _PatchCustomSources,
    get_settings: _GetSettings,
    site: dict[str, str],
) -> bool:
    custom, _ = await _fetch_settings_overrides(get_settings)
    custom = list(custom)
    custom.append(site)
    return await patch_custom(custom)


async def macroadd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("macro_add", None)
    if update.effective_message:
        await update.effective_message.reply_text("Cancelled.")
    return ConversationHandler.END


async def macroadd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return ConversationHandler.END
    if not is_admin(user.id):
        await msg.reply_text("Only the configured admin can add macro sources.")
        return ConversationHandler.END
    context.user_data["macro_add"] = {}
    await msg.reply_text(
        "Add a macro search source\n\n"
        "1) Run a manual search on the site in your browser.\n"
        "2) Paste the <b>full address bar URL</b> here (after the search).\n\n"
        "Send /cancel to abort.",
        parse_mode="HTML",
    )
    return MS_ADD_URL


async def macroadd_got_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    if not msg or not msg.text:
        return MS_ADD_URL
    raw = msg.text.strip()
    if not raw.startswith(("http://", "https://")):
        await msg.reply_text("Send a valid http(s) URL from the address bar after searching.")
        return MS_ADD_URL
    context.user_data.setdefault("macro_add", {})["search_url"] = raw
    await msg.reply_text(
        "What <b>username</b> did you use in that search? (no @)\n\n"
        "TBCC will suggest a <code>{username}</code> template from your answer.",
        parse_mode="HTML",
    )
    return MS_ADD_USER


async def macroadd_got_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    if not msg or not msg.text:
        return MS_ADD_USER
    username = normalize_macro_username(msg.text)
    if not username:
        await msg.reply_text("Enter a valid username (letters/numbers/._-).")
        return MS_ADD_USER
    data = context.user_data.setdefault("macro_add", {})
    data["username"] = username
    tpl = derive_username_template_from_search_url(data.get("search_url") or "", username)
    if not tpl:
        await msg.reply_text(
            "Could not find that username in the URL. "
            "Paste the exact address bar URL from after you searched, then try /macroaddsource again."
        )
        return ConversationHandler.END
    err = validate_custom_source_url(tpl)
    if err:
        await msg.reply_text(f"Template invalid: {err}")
        return ConversationHandler.END
    data["template"] = tpl
    await msg.reply_text(
        "Suggested search URL template:\n"
        f"<code>{html.escape(tpl)}</code>\n\n"
        "Copy it if you like, then reply with the <b>display name</b> for this source "
        "(e.g. <code>My Cam Site</code>).",
        parse_mode="HTML",
    )
    return MS_ADD_NAME


async def macroadd_got_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    get_settings: _GetSettings,
    patch_custom: _PatchCustomSources,
) -> int:
    msg = update.effective_message
    if not msg or not msg.text:
        return MS_ADD_NAME
    name = msg.text.strip()[:128]
    if not name:
        await msg.reply_text("Enter a display name for the source.")
        return MS_ADD_NAME
    data = context.user_data.get("macro_add") or {}
    tpl = data.get("template")
    if not tpl:
        await msg.reply_text("Session expired. Run /macroaddsource again.")
        return ConversationHandler.END
    site = {
        "id": new_custom_site_id(),
        "name": name,
        "url": tpl,
        "category": "macro",
    }
    ok = await _append_custom_source(patch_custom, get_settings, site)
    context.user_data.pop("macro_add", None)
    if not ok:
        await msg.reply_text("Failed to save source to the database. Check API/logs.")
        return ConversationHandler.END
    await msg.reply_text(
        f"✅ Added macro source <b>{html.escape(name)}</b>\n"
        f"<code>{html.escape(tpl)}</code>\n\n"
        "Enabled immediately for /macrosearch.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cmd_macrodebug(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    get_settings: _GetSettings,
) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not is_admin(user.id):
        if msg:
            await msg.reply_text("Admin only.")
        return
    args = context.args or []
    if not args:
        await msg.reply_text("Usage: /macrodebug &lt;username&gt;", parse_mode="HTML")
        return
    category, username_raw = parse_category_and_query(list(args))
    username = normalize_macro_username(username_raw)
    if not username:
        await msg.reply_text("Invalid username.")
        return
    st = await get_settings()
    sources = resolve_sources_for_mode(st, category)
    max_links = int(st.get("video_finder_max_links_per_source") or 8)
    await msg.reply_text(f"Debug scan ({category}) for @{username} — {len(sources)} sources…")
    sem = asyncio.Semaphore(MACRO_SEARCH_CONCURRENCY)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=headers) as client:

        async def one(site: dict[str, Any]) -> str:
            async with sem:
                row = await probe_macro_site(client, site, username)
                html_text = row.get("html") or ""
                nlinks = 0
                if html_text:
                    nlinks = len(
                        extract_video_links_from_html(
                            html_text,
                            row.get("final_url") or row["search_url"],
                            site,
                            username,
                            max_links,
                        )
                    )
                name = str(site.get("name") or site.get("id") or "?")[:40]
                return (
                    f"{name}: status={row.get('fetch_status')} signal={row.get('signal')} "
                    f"conf={row.get('confidence')} count={row.get('count')} links={nlinks} "
                    f"html={len(html_text)} reason={row.get('reason')}"
                )

        lines = await asyncio.gather(*[one(s) for s in sources[:30]])
    body = "\n".join(lines)
    if len(sources) > 30:
        body += f"\n… +{len(sources) - 30} more sources (truncated)"
    if len(body) > 3900:
        body = body[:3900] + "\n…"
    await msg.reply_text(f"<pre>{html.escape(body)}</pre>", parse_mode="HTML")


async def cmd_macrolist(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    get_settings: _GetSettings,
) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not is_admin(user.id):
        if msg:
            await msg.reply_text("Admin only.")
        return
    st = await get_settings()
    sources = st.get("macro_search_sources") or []
    custom = st.get("macro_search_custom_sources") or []
    lines = [f"<b>Macro sources ({len(sources)})</b>"]
    for s in sources[:40]:
        tag = "custom" if str(s.get("id", "")).startswith("custom_") else "builtin"
        lines.append(f"• [{tag}] {html.escape(str(s.get('name') or s.get('id')))}")
    if len(sources) > 40:
        lines.append(f"… and {len(sources) - 40} more")
    lines.append(f"\nCustom in DB: {len(custom) if isinstance(custom, list) else 0}")
    await msg.reply_text("\n".join(lines), parse_mode="HTML")


def build_macro_search_handlers(
    get_settings: _GetSettings,
    patch_custom_sources: _PatchCustomSources,
    force_refresh_settings: Callable[[], Awaitable[None]] | None = None,
    *,
    command_filters: filters.BaseFilter | None = None,
    include_overlay_text: bool = False,
) -> list:
    async def _refresh() -> None:
        if force_refresh_settings:
            await force_refresh_settings()

    async def _patch(custom: list[dict[str, Any]]) -> bool:
        ok = await patch_custom_sources(custom)
        if ok:
            await _refresh()
        return ok

    async def macrosearch_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        await cmd_macrosearch(u, c, get_settings=get_settings)

    async def macrodebug_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        await cmd_macrodebug(u, c, get_settings=get_settings)

    async def macrolist_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        await cmd_macrolist(u, c, get_settings=get_settings)

    async def recent_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        await cmd_recent(u, c)

    async def got_name(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
        return await macroadd_got_name(u, c, get_settings=get_settings, patch_custom=_patch)

    conv = ConversationHandler(
        entry_points=[CommandHandler("macroaddsource", macroadd_start, filters=command_filters)],
        states={
            MS_ADD_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, macroadd_got_url)],
            MS_ADD_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, macroadd_got_user)],
            MS_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_name)],
        },
        fallbacks=[CommandHandler("cancel", macroadd_cancel)],
        allow_reentry=True,
    )

    handlers: list = [
        CommandHandler("macrosearch", macrosearch_cmd, filters=command_filters),
        CommandHandler("macrodebug", macrodebug_cmd, filters=command_filters),
        CommandHandler("macrolist", macrolist_cmd, filters=command_filters),
        CommandHandler("recent", recent_cmd, filters=command_filters),
        CallbackQueryHandler(
            lambda u, c: on_macro_overlay_callback(u, c, get_settings=get_settings),
            pattern=r"^ms:",
        ),
        conv,
    ]
    if include_overlay_text:
        handlers.append(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & (command_filters or filters.ALL),
                lambda u, c: on_macro_overlay_text(u, c, get_settings=get_settings),
            )
        )
    return handlers
