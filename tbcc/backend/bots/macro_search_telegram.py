"""
Telegram macro model search — extension parity in the payment bot DM.

Commands: /macrosearch, /videofind (alias), /macroaddsource (admin), /macrolist (admin)
Deep links: /start ms_<username> or vf_<username>
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
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.services.model_search_engine import (
    build_model_search_url,
    derive_username_template_from_search_url,
    extract_video_links_from_html,
    new_custom_site_id,
    validate_custom_source_url,
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
    """Probe all macro sources; return hits with video links or labeled probe-only rows."""
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
) -> None:
    msg = update.effective_message
    if not msg:
        return
    if not hits:
        await msg.reply_text(
            f"No macro hits on {scanned} source(s) for <b>@{html.escape(username)}</b>.",
            parse_mode="HTML",
        )
        return
    link_hits = sum(1 for h in hits if h.get("kind") == "links")
    probe_hits = sum(1 for h in hits if h.get("kind") == "probe")
    await msg.reply_text(
        f"Macro search: <b>{len(hits)}</b> hit(s) for <b>@{html.escape(username)}</b> "
        f"({link_hits} with video URLs, {probe_hits} probe-only)",
        parse_mode="HTML",
    )
    for h in hits:
        name = html.escape(str(h.get("name") or h.get("site_id") or "source"))
        links = h.get("links") or []
        if links:
            lines = [f"• {html.escape(u)}" for u in links]
            body = f"🎬 <b>{name}</b> ({len(links)} link(s))\n" + "\n".join(lines)
        else:
            body = (
                f"⚠️ <b>{name}</b> — probe only (~{h.get('count')})\n"
                f"No direct video links parsed from HTML. Open search page:\n"
                f"• {html.escape(str(h.get('search_url') or ''))}"
            )
        await msg.reply_text(body, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_macrosearch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    get_settings: _GetSettings,
) -> None:
    msg = update.effective_message
    if not msg:
        return
    args = context.args or []
    if not args:
        await msg.reply_text(
            "Usage: /macrosearch &lt;username&gt;\n\n"
            "Scans all enabled <b>macro</b> sources (same list as the TBCC extension), "
            "then sends video URLs from sites with hits.\n\n"
            "Add sources: /macroaddsource (admin)",
            parse_mode="HTML",
        )
        return
    username = normalize_macro_username(" ".join(args))
    if not username:
        await msg.reply_text("Please provide a valid username (letters/numbers/._-).")
        return
    st = await get_settings()
    if not bool(st.get("video_finder_enabled", True)):
        await msg.reply_text("Macro search is disabled in bot settings.")
        return
    sources = st.get("macro_search_sources") or []
    if not sources:
        await msg.reply_text("No macro search sources are configured.")
        return
    max_links = int(st.get("video_finder_max_links_per_source") or 8)
    await msg.reply_text(
        f"🔎 Macro search for <b>@{html.escape(username)}</b> — {len(sources)} source(s)…",
        parse_mode="HTML",
    )
    hits = await run_macro_search(username, sources, max_links)
    await send_macro_search_results(update, username, hits, len(sources))
    if hits:
        await msg.reply_text(
            f"Done. {len(hits)} site(s) with hits for @{username}.",
            disable_web_page_preview=True,
        )


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
    username = normalize_macro_username(" ".join(args))
    if not username:
        await msg.reply_text("Invalid username.")
        return
    st = await get_settings()
    sources = st.get("macro_search_sources") or []
    max_links = int(st.get("video_finder_max_links_per_source") or 8)
    await msg.reply_text(f"Debug scan for @{username} — {len(sources)} sources…")
    sem = asyncio.Semaphore(MACRO_SEARCH_CONCURRENCY)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    lines: list[str] = []

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
        tag = "custom" if s.get("id", "").startswith("custom_") else "builtin"
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

    async def name_step(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
        return await macroadd_got_name(u, c, get_settings=get_settings, patch_custom=_patch)

    conv = ConversationHandler(
        entry_points=[CommandHandler("macroaddsource", macroadd_start, filters=command_filters)],
        states={
            MS_ADD_URL: [MessageHandler((command_filters or filters.ALL) & filters.TEXT & ~filters.COMMAND, macroadd_got_url)],
            MS_ADD_USER: [MessageHandler((command_filters or filters.ALL) & filters.TEXT & ~filters.COMMAND, macroadd_got_user)],
            MS_ADD_NAME: [MessageHandler((command_filters or filters.ALL) & filters.TEXT & ~filters.COMMAND, name_step)],
        },
        fallbacks=[CommandHandler("cancel", macroadd_cancel, filters=command_filters)],
        allow_reentry=True,
    )
    return [
        CommandHandler("macrosearch", macrosearch_cmd, filters=command_filters),
        CommandHandler("macrodebug", macrodebug_cmd, filters=command_filters),
        conv,
        CommandHandler("macrolist", macrolist_cmd, filters=command_filters),
    ]
