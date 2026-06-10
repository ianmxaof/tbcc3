"""
Forum topic integration for macro_search_bot — Erome/Bunkr Links bridge to TBCC inbox + model search.

Env:
  TBCC_MACRO_SEARCH_FORUM_CHAT_ID — supergroup chat id (-100…)
  TBCC_MACRO_SEARCH_FORUM_THREAD_ID — forum topic id (message_thread_id)
  TBCC_MACRO_SEARCH_FORUM_POST_WELCOME=1 — post pinned intro on startup (once per process)
"""

from __future__ import annotations

import html
import logging
import os
import re
from typing import Any, Awaitable, Callable

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bots.macro_search_telegram import (
    MS_ADD_NAME,
    MS_ADD_URL,
    MS_ADD_USER,
    _GetSettings,
    _PatchCustomSources,
    cmd_macrosearch,
    is_admin,
    macroadd_cancel,
    macroadd_got_name,
    macroadd_got_url,
    macroadd_got_user,
    normalize_macro_username,
)
from app.services.model_search_engine import derive_username_template_from_search_url

logger = logging.getLogger(__name__)

API_BASE = os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")

_EROME_BUNKR_RE = re.compile(
    r"https?://(?:[\w.-]+\.)?(?:erome\.com|bunkr\.(?:su|cr|la|fi|is|cat|si|pk|black|red|org|site|fans)|bunkrr\.su)/[^\s<>\"']+",
    re.I,
)
_HTTP_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

(SS_ADD_URL, SS_ADD_USER, SS_ADD_NAME) = range(10, 13)


def forum_chat_id() -> int | None:
    raw = (
        os.getenv("TBCC_MACRO_SEARCH_FORUM_CHAT_ID")
        or os.getenv("TBCC_LOOT_AOF_GROUP_CHAT_ID")
        or ""
    ).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def forum_thread_id() -> int | None:
    raw = os.getenv("TBCC_MACRO_SEARCH_FORUM_THREAD_ID", "").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def forum_enabled() -> bool:
    return forum_chat_id() is not None and forum_thread_id() is not None


class ForumTopicFilter(filters.MessageFilter):
    """Only messages in the configured forum topic (or DMs when forum not configured)."""

    def filter(self, message) -> bool:  # type: ignore[override]
        if not message or not message.chat:
            return False
        cid = forum_chat_id()
        tid = forum_thread_id()
        if cid is None or tid is None:
            return message.chat.type == "private"
        if message.chat_id != cid:
            return False
        return getattr(message, "message_thread_id", None) == tid


FORUM_TOPIC = ForumTopicFilter()

FORUM_OR_DM = filters.ChatType.PRIVATE | (filters.ChatType.GROUPS & FORUM_TOPIC)


def _user_id(update: Update) -> str:
    u = update.effective_user
    return str(u.id) if u else ""


def _host_tags(url: str) -> str:
    low = url.lower()
    tags = ["community", "telegram"]
    if "erome.com" in low:
        tags.append("erome")
    if "bunkr" in low:
        tags.append("bunkr")
    return ",".join(tags)


def _extract_erome_bunkr_urls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _EROME_BUNKR_RE.finditer(text or ""):
        u = m.group(0).rstrip(").,;")
        k = u.lower()
        if k not in seen:
            seen.add(k)
            out.append(u)
    return out


async def _api_submit_url(
    url: str,
    *,
    submitted_by: str,
    auto_approve: bool,
    tags: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    payload = {
        "value": url,
        "source": "telegram_admin" if auto_approve else "telegram_community",
        "origin": "telegram",
        "tags": tags or _host_tags(url),
        "submitted_by": submitted_by,
        "auto_approve": auto_approve,
        "note": note,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{API_BASE}/archive/entries/submit", json=payload, timeout=15.0)
        if r.is_success:
            return r.json()
        return {"ok": False, "error": r.text[:200]}


async def _api_submit_macro_source(
    *,
    name: str,
    url_template: str,
    sample_username: str | None,
    sample_search_url: str | None,
    submitted_by: str,
) -> dict[str, Any]:
    payload = {
        "name": name,
        "url_template": url_template,
        "sample_username": sample_username,
        "sample_search_url": sample_search_url,
        "submitted_by": submitted_by,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{API_BASE}/macro-search/source-submissions", json=payload, timeout=15.0)
        if r.is_success:
            return r.json()
        return {"ok": False, "error": r.text[:200]}


async def _api_govern_url(entry_id: int, status: str, reviewed_by: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API_BASE}/archive/entries/{entry_id}/governance",
            json={"status": status, "reviewed_by": reviewed_by},
            timeout=15.0,
        )
        if r.is_success:
            return r.json()
        return {"ok": False, "error": r.text[:200]}


async def _api_pending_urls() -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_BASE}/archive/governance/pending", timeout=15.0)
        if r.is_success:
            return (r.json() or {}).get("items") or []
    return []


async def _api_pending_sources() -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_BASE}/macro-search/source-submissions", timeout=15.0)
        if r.is_success:
            return (r.json() or {}).get("items") or []
    return []


async def _api_approve_source(submission_id: int, reviewed_by: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API_BASE}/macro-search/source-submissions/{submission_id}/approve",
            json={"reviewed_by": reviewed_by},
            timeout=15.0,
        )
        if r.is_success:
            return r.json()
        return {"ok": False, "error": r.text[:200]}


async def _api_reject_source(submission_id: int, reviewed_by: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API_BASE}/macro-search/source-submissions/{submission_id}/reject",
            json={"reviewed_by": reviewed_by},
            timeout=15.0,
        )
        if r.is_success:
            return r.json()
        return {"ok": False, "error": r.text[:200]}


def forum_welcome_html() -> str:
    return (
        "<b>Erome / Bunkr → TBCC</b>\n\n"
        "Share your favorite <b>erome.com</b> and <b>bunkr</b> galleries here. "
        "This topic is wired to the TBCC master archive and macro model search.\n\n"
        "<b>Commands</b>\n"
        "• /macrosearch &lt;username&gt; — scan macro sources, get video URLs\n"
        "• /videofind — same as /macrosearch\n"
        "• /inbox &lt;url&gt; — queue a gallery link for TBCC review\n"
        "• /suggestsource — suggest a new macro search site (URL template wizard)\n"
        "• /help — this summary\n\n"
        "<b>Governance</b>\n"
        "Community links stay <i>pending</i> until an admin approves them in TBCC. "
        "After approval they enter the master archive (loot modifier / AOF import pipeline).\n\n"
        "Paste a gallery URL in chat and tap the button to queue it, or DM this bot anytime."
    )


async def cmd_forum_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    await msg.reply_text(forum_welcome_html(), parse_mode="HTML")


async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    args = context.args or []
    text = " ".join(args).strip()
    if not text and msg.reply_to_message and msg.reply_to_message.text:
        text = msg.reply_to_message.text
    urls = _extract_erome_bunkr_urls(text) or [
        u.rstrip(").,;") for u in _HTTP_URL_RE.findall(text) if u.startswith("http")
    ]
    if not urls:
        await msg.reply_text(
            "Usage: /inbox &lt;gallery URL&gt;\n\n"
            "Example: <code>/inbox https://erome.com/a/abc123</code>\n"
            "Or reply to a message containing a link.",
            parse_mode="HTML",
        )
        return
    admin = is_admin(user.id)
    lines: list[str] = []
    for url in urls[:5]:
        r = await _api_submit_url(
            url,
            submitted_by=_user_id(update),
            auto_approve=admin,
            tags=_host_tags(url),
        )
        if not r.get("ok"):
            lines.append(f"❌ {html.escape(url[:80])} — {html.escape(str(r.get('error') or 'failed'))}")
            continue
        st = r.get("status") or "pending"
        eid = (r.get("entry") or {}).get("id")
        if r.get("duplicate"):
            lines.append(f"ℹ️ Already queued (#{eid}) — {html.escape(url[:80])}")
        elif admin or st == "approved":
            lines.append(f"✅ Added to master archive — {html.escape(url[:80])}")
        else:
            lines.append(f"📥 Pending review (#{eid}) — {html.escape(url[:80])}")
    await msg.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


async def on_forum_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text or msg.text.startswith("/"):
        return
    urls = _extract_erome_bunkr_urls(msg.text)
    if not urls:
        return
    url = urls[0]
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📥 Queue for TBCC inbox", callback_data=f"ms:inbox:{msg.message_id}")]]
    )
    await msg.reply_text(
        f"Gallery link detected — queue for TBCC review?\n<code>{html.escape(url[:200])}</code>",
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True,
        reply_to_message_id=msg.message_id,
    )


async def on_inbox_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("ms:inbox:"):
        return
    await q.answer()
    msg = q.message
    user = update.effective_user
    if not msg or not user:
        return
    try:
        mid = int(q.data.split(":")[-1])
    except ValueError:
        return
    chat_id = msg.chat_id
    text = ""
    if msg.reply_to_message:
        text = msg.reply_to_message.text or ""
    if not text:
        await q.edit_message_text("Could not read the original link. Use /inbox &lt;url&gt; instead.", parse_mode="HTML")
        return
    urls = _extract_erome_bunkr_urls(text)
    if not urls:
        await q.edit_message_text("No erome/bunkr URL found in that message.")
        return
    admin = is_admin(user.id)
    r = await _api_submit_url(
        urls[0],
        submitted_by=_user_id(update),
        auto_approve=admin,
        tags=_host_tags(urls[0]),
    )
    if not r.get("ok"):
        await q.edit_message_text(f"Failed: {html.escape(str(r.get('error') or 'error'))}", parse_mode="HTML")
        return
    st = r.get("status") or "pending"
    eid = (r.get("entry") or {}).get("id")
    if admin or st == "approved":
        note = f"✅ Added to master archive (#{eid})."
    else:
        note = f"📥 Queued for admin review (#{eid}). You'll see it in TBCC after approval."
    await q.edit_message_text(note, parse_mode="HTML")


async def suggestsource_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    if not msg:
        return ConversationHandler.END
    context.user_data["macro_suggest"] = {}
    await msg.reply_text(
        "<b>Suggest a macro search source</b>\n\n"
        "1) Run a manual username search on the site in your browser.\n"
        "2) Paste the <b>full address bar URL</b> here (after the search).\n\n"
        "Admins can use /macroaddsource to add immediately; "
        "your suggestion goes to a review queue.\n\n"
        "Send /cancel to abort.",
        parse_mode="HTML",
    )
    return SS_ADD_URL


async def suggestsource_got_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    if not msg or not msg.text:
        return SS_ADD_URL
    raw = msg.text.strip()
    if not raw.startswith(("http://", "https://")):
        await msg.reply_text("Send a valid http(s) URL from the address bar after searching.")
        return SS_ADD_URL
    context.user_data.setdefault("macro_suggest", {})["search_url"] = raw
    await msg.reply_text(
        "What <b>username</b> did you use in that search? (no @)\n\n"
        "TBCC will suggest a <code>{username}</code> template from your answer.",
        parse_mode="HTML",
    )
    return SS_ADD_USER


async def suggestsource_got_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    if not msg or not msg.text:
        return SS_ADD_USER
    username = normalize_macro_username(msg.text)
    if not username:
        await msg.reply_text("Enter a valid username (letters/numbers/._-).")
        return SS_ADD_USER
    data = context.user_data.setdefault("macro_suggest", {})
    data["username"] = username
    tpl = derive_username_template_from_search_url(data.get("search_url") or "", username)
    if not tpl:
        await msg.reply_text(
            "Could not find that username in the URL. "
            "Paste the exact address bar URL from after you searched, then try /suggestsource again."
        )
        return ConversationHandler.END
    data["template"] = tpl
    await msg.reply_text(
        "Suggested search URL template:\n"
        f"<code>{html.escape(tpl)}</code>\n\n"
        "Reply with the <b>display name</b> for this source "
        "(e.g. <code>Erome search</code>).",
        parse_mode="HTML",
    )
    return SS_ADD_NAME


async def suggestsource_got_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    get_settings: _GetSettings | None = None,
    patch_custom: _PatchCustomSources | None = None,
) -> int:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not msg.text or not user:
        return SS_ADD_NAME
    name = msg.text.strip()[:128]
    if not name:
        await msg.reply_text("Enter a display name for the source.")
        return SS_ADD_NAME
    data = context.user_data.get("macro_suggest") or {}
    tpl = data.get("template")
    search_url = data.get("search_url")
    username = data.get("username")
    if not tpl:
        await msg.reply_text("Session expired. Run /suggestsource again.")
        return ConversationHandler.END

    if is_admin(user.id) and get_settings and patch_custom:
        context.user_data["macro_add"] = {
            "search_url": search_url,
            "username": username,
            "template": tpl,
        }
        context.user_data.pop("macro_suggest", None)
        return await macroadd_got_name(
            update,
            context,
            get_settings=get_settings,
            patch_custom=patch_custom,
        )

    r = await _api_submit_macro_source(
        name=name,
        url_template=tpl,
        sample_username=username,
        sample_search_url=search_url,
        submitted_by=_user_id(update),
    )
    context.user_data.pop("macro_suggest", None)
    if not r.get("ok"):
        await msg.reply_text(f"Failed to save suggestion: {html.escape(str(r.get('error') or 'error'))}", parse_mode="HTML")
        return ConversationHandler.END
    sid = (r.get("submission") or {}).get("id")
    if r.get("duplicate"):
        await msg.reply_text(f"That template is already pending review (#{sid}).")
    else:
        await msg.reply_text(
            f"✅ Source suggestion submitted (#{sid})\n"
            f"<b>{html.escape(name)}</b>\n"
            f"<code>{html.escape(tpl)}</code>\n\n"
            "An admin will review it for /macrosearch.",
            parse_mode="HTML",
        )
    return ConversationHandler.END


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not is_admin(user.id):
        if msg:
            await msg.reply_text("Admin only.")
        return
    urls = await _api_pending_urls()
    sources = await _api_pending_sources()
    lines = ["<b>Pending archive URLs</b>"]
    if not urls:
        lines.append("• (none)")
    for e in urls[:15]:
        lines.append(f"• #{e.get('id')} {html.escape(str(e.get('value') or '')[:70])}")
    if len(urls) > 15:
        lines.append(f"… +{len(urls) - 15} more")
    lines.append("\n<b>Pending macro sources</b>")
    if not sources:
        lines.append("• (none)")
    for s in sources[:15]:
        lines.append(f"• #{s.get('id')} {html.escape(str(s.get('name') or ''))}")
    lines.append("\nApprove: /approveurl &lt;id&gt; · /approvesource &lt;id&gt;")
    await msg.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


async def cmd_approveurl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not is_admin(user.id):
        if msg:
            await msg.reply_text("Admin only.")
        return
    args = context.args or []
    if not args:
        await msg.reply_text("Usage: /approveurl &lt;entry id&gt;", parse_mode="HTML")
        return
    try:
        eid = int(args[0])
    except ValueError:
        await msg.reply_text("Entry id must be a number.")
        return
    r = await _api_govern_url(eid, "approved", _user_id(update))
    if not r.get("ok"):
        await msg.reply_text(f"Failed: {html.escape(str(r.get('error') or 'error'))}", parse_mode="HTML")
        return
    val = (r.get("entry") or {}).get("value") or ""
    await msg.reply_text(f"✅ Approved #{eid} — now in master archive.\n{html.escape(val[:200])}", parse_mode="HTML")


async def cmd_rejecturl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not is_admin(user.id):
        if msg:
            await msg.reply_text("Admin only.")
        return
    args = context.args or []
    if not args:
        await msg.reply_text("Usage: /rejecturl &lt;entry id&gt;", parse_mode="HTML")
        return
    try:
        eid = int(args[0])
    except ValueError:
        await msg.reply_text("Entry id must be a number.")
        return
    r = await _api_govern_url(eid, "rejected", _user_id(update))
    if not r.get("ok"):
        await msg.reply_text(f"Failed: {html.escape(str(r.get('error') or 'error'))}", parse_mode="HTML")
        return
    await msg.reply_text(f"Rejected archive entry #{eid}.")


async def cmd_approvesource(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not is_admin(user.id):
        if msg:
            await msg.reply_text("Admin only.")
        return
    args = context.args or []
    if not args:
        await msg.reply_text("Usage: /approvesource &lt;submission id&gt;", parse_mode="HTML")
        return
    try:
        sid = int(args[0])
    except ValueError:
        await msg.reply_text("Submission id must be a number.")
        return
    r = await _api_approve_source(sid, _user_id(update))
    if not r.get("ok"):
        await msg.reply_text(f"Failed: {html.escape(str(r.get('error') or 'error'))}", parse_mode="HTML")
        return
    name = (r.get("submission") or {}).get("name") or (r.get("site") or {}).get("name") or ""
    await msg.reply_text(f"✅ Macro source #{sid} approved — {html.escape(name)}", parse_mode="HTML")


async def cmd_rejectsource(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not is_admin(user.id):
        if msg:
            await msg.reply_text("Admin only.")
        return
    args = context.args or []
    if not args:
        await msg.reply_text("Usage: /rejectsource &lt;submission id&gt;", parse_mode="HTML")
        return
    try:
        sid = int(args[0])
    except ValueError:
        await msg.reply_text("Submission id must be a number.")
        return
    r = await _api_reject_source(sid, _user_id(update))
    if not r.get("ok"):
        await msg.reply_text(f"Failed: {html.escape(str(r.get('error') or 'error'))}", parse_mode="HTML")
        return
    await msg.reply_text(f"Rejected macro source submission #{sid}.")


async def post_forum_welcome(application) -> None:
    if os.getenv("TBCC_MACRO_SEARCH_FORUM_POST_WELCOME", "1").strip().lower() in ("0", "false", "no"):
        return
    cid = forum_chat_id()
    tid = forum_thread_id()
    if cid is None or tid is None:
        logger.info("Forum welcome skipped — set TBCC_MACRO_SEARCH_FORUM_CHAT_ID + TBCC_MACRO_SEARCH_FORUM_THREAD_ID")
        return
    try:
        await application.bot.send_message(
            chat_id=cid,
            message_thread_id=tid,
            text=forum_welcome_html(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logger.info("Posted macro search forum welcome to chat=%s thread=%s", cid, tid)
    except Exception as e:
        logger.warning("forum welcome post failed: %s", e)


def build_forum_handlers(
    get_settings: _GetSettings,
    patch_custom: _PatchCustomSources,
) -> list:
    async def macrosearch_forum(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        await cmd_macrosearch(u, c, get_settings=get_settings)

    async def videofind_forum(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        await cmd_macrosearch(u, c, get_settings=get_settings)

    async def suggest_name_step(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
        return await suggestsource_got_name(u, c, get_settings=get_settings, patch_custom=patch_custom)

    suggest_conv = ConversationHandler(
        entry_points=[CommandHandler("suggestsource", suggestsource_start, filters=FORUM_OR_DM)],
        states={
            SS_ADD_URL: [MessageHandler(FORUM_OR_DM & filters.TEXT & ~filters.COMMAND, suggestsource_got_url)],
            SS_ADD_USER: [MessageHandler(FORUM_OR_DM & filters.TEXT & ~filters.COMMAND, suggestsource_got_user)],
            SS_ADD_NAME: [MessageHandler(FORUM_OR_DM & filters.TEXT & ~filters.COMMAND, suggest_name_step)],
        },
        fallbacks=[CommandHandler("cancel", macroadd_cancel, filters=FORUM_OR_DM)],
        allow_reentry=True,
        name="macro_suggest_source",
    )

    scope = FORUM_OR_DM
    return [
        CommandHandler("help", cmd_forum_help, filters=scope),
        CommandHandler("inbox", cmd_inbox, filters=scope),
        CommandHandler("macrosearch", macrosearch_forum, filters=scope),
        CommandHandler("videofind", videofind_forum, filters=scope),
        CommandHandler("pending", cmd_pending, filters=scope),
        CommandHandler("approveurl", cmd_approveurl, filters=scope),
        CommandHandler("rejecturl", cmd_rejecturl, filters=scope),
        CommandHandler("approvesource", cmd_approvesource, filters=scope),
        CommandHandler("rejectsource", cmd_rejectsource, filters=scope),
        suggest_conv,
        CallbackQueryHandler(on_inbox_callback, pattern=r"^ms:inbox:"),
        MessageHandler(scope & filters.TEXT & ~filters.COMMAND, on_forum_url_message),
    ]
