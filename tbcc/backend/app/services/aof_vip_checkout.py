"""AOF VIP broadcast channel — native Stars subscription checkout on network posts."""

from __future__ import annotations

import html
import logging
import os
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.data.aof_network import AOF_VIP_IDENT, AOF_VIP_INVITE_PRIMARY
from app.models.subscription_plan import SubscriptionPlan
from app.services.telegram_stars_invoice import (
    create_stars_invoice_link,
    plan_to_invoice_link_dict,
    use_invoice_link_checkout,
)

logger = logging.getLogger(__name__)

SUBSCRIPTION_PERIOD_SECONDS = 2_592_000  # 30 days — only value Telegram allows today
BOT_FALLBACK_LABEL = "Crypto & main group →"
CHECKOUT_CAPTION_LABEL_DEFAULT = "VIP checkout — Stars · crypto · card"
# Retired pre-Gumroad monthly plan id (AOF Main — 500⭐); map to active VIP ladder at send time.
LEGACY_CHECKOUT_PLAN_IDS = frozenset({6})
CHECKOUT_CAPTION_MARKERS = (
    "Subscribe to AOF VIP",
    "Start payment for group access",
    "Pay for group access with Stars",
    CHECKOUT_CAPTION_LABEL_DEFAULT,
)
_CHECKOUT_CAPTION_LINE_RE = re.compile(
    r"\n?💳\s*<a\s+href=\"[^\"]+\">[^<]+</a>",
    re.I,
)
_BARE_VIP_FOOTER_BIT_RE = re.compile(
    r'\s*·\s*⭐\s*<a\s+href="[^"]+">AOF VIP</a>',
    re.I,
)
_BARE_VIP_ANCHOR_RE = re.compile(
    r'<a\s+href="https://t\.me/\+[^"]+">(?:AOF VIP|subscribe)</a>',
    re.I,
)


def checkout_multi_album_followup_enabled() -> bool:
    raw = (os.getenv("TBCC_CHECKOUT_MULTI_ALBUM_FOLLOWUP") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def main_group_checkout_every_n() -> int:
    """Main group: attach Stars checkout on every Nth send (1 = every post)."""
    raw = (os.getenv("TBCC_MAIN_GROUP_CHECKOUT_EVERY_N") or "1").strip()
    try:
        return max(1, min(6, int(raw)))
    except ValueError:
        return 2


def checkout_blocked_for_telegram_identifier(channel_identifier: str | Any) -> bool:
    """Operator-only chats — never attach monetization checkout (Storage & Bot Hangar)."""
    from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
    from app.utils.telegram_peer import normalize_telethon_peer_identifier

    ident = normalize_telethon_peer_identifier(channel_identifier)
    if not ident or not isinstance(ident, str):
        return False
    try:
        return int(ident) == int(STORAGE_HUB_IDENT)
    except (ValueError, TypeError):
        return ident == STORAGE_HUB_IDENT


def checkout_active_for_send(
    post: Any,
    channel_identifier: str,
    *,
    caption_slot_index: int,
) -> bool:
    """Whether this send should include Stars checkout (main group uses every-N cadence)."""
    if not getattr(post, "checkout_stars_enabled", False) or not getattr(post, "checkout_stars_plan_id", None):
        return False
    from app.data.aof_network import MAIN_GROUP_IDENT

    ident = str(channel_identifier or "").strip()
    if checkout_blocked_for_telegram_identifier(ident):
        return False
    try:
        is_main = int(ident) == int(MAIN_GROUP_IDENT)
    except ValueError:
        is_main = ident == MAIN_GROUP_IDENT
    if not is_main:
        return True
    n = main_group_checkout_every_n()
    if n <= 1:
        return True
    return (int(caption_slot_index) % n) == 0


def vip_channel_ident() -> str:
    return (os.getenv("TBCC_AOF_VIP_CHANNEL_IDENT") or AOF_VIP_IDENT).strip()


def vip_primary_invite_url() -> str:
    return (os.getenv("TBCC_AOF_VIP_INVITE_URL") or AOF_VIP_INVITE_PRIMARY).strip()


def vip_subscription_invite_url() -> str:
    """Stars subscription invite link (createChatSubscriptionInviteLink) — not a regular admin invite."""
    return (os.getenv("TBCC_AOF_VIP_SUBSCRIPTION_INVITE_URL") or "").strip()


def use_vip_star_subscription() -> bool:
    """Native channel subscription invite — provisioning only; not used on network post checkout."""
    raw = (os.getenv("TBCC_CHECKOUT_USE_VIP_STAR_SUBSCRIPTION") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return bool(vip_subscription_invite_url())


def is_bare_vip_invite_url(url: str) -> bool:
    """True for raw AOF VIP channel/subscription invites (must not appear on paywalled posts)."""
    u = (url or "").strip().lower().rstrip("/")
    if not u:
        return False
    for candidate in (vip_subscription_invite_url(), vip_primary_invite_url()):
        c = (candidate or "").strip().lower().rstrip("/")
        if c and u == c:
            return True
    return False


def _payment_bot_username() -> str:
    return (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")


def checkout_deep_link_payload(
    plan_id: int,
    referral_code: str | None,
    *,
    menu: bool = False,
) -> str | None:
    """Telegram /start payload must stay within 64 bytes (UTF-8)."""
    code = (referral_code or "").strip().upper()
    prefix = f"cm{int(plan_id)}" if menu else f"c{int(plan_id)}"
    if code:
        if not re.match(r"^[A-Z0-9]{1,16}$", code):
            return None
        raw = f"{prefix}_{code}"
    else:
        raw = prefix
    if len(raw.encode("utf-8")) > 64:
        return None
    return raw


def checkout_caption_label() -> str:
    return (os.getenv("TBCC_CHECKOUT_CAPTION_LABEL") or CHECKOUT_CAPTION_LABEL_DEFAULT).strip()


def normalize_checkout_plan_id(db: Session, plan_id: int) -> int:
    """Map inactive/legacy checkout plan ids to the live monthly VIP SKU."""
    pid = int(plan_id)
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == pid).first()
    if plan and plan.is_active is not False and int(plan.price_stars or 0) > 0:
        return pid
    from app.services.aof_growth_hub import resolve_group_access_plan_id

    return resolve_group_access_plan_id(db)


def bot_checkout_url(
    plan_id: int,
    referral_code: str | None = None,
    *,
    menu: bool = False,
) -> str | None:
    bot = _payment_bot_username()
    if not bot:
        return None
    payload = checkout_deep_link_payload(int(plan_id), referral_code, menu=menu)
    if not payload:
        return None
    return f"https://t.me/{bot}?start={payload}"


def stars_pay_button_label(plan: SubscriptionPlan) -> str:
    stars = int(plan.price_stars or 0)
    if stars > 0:
        return f"Pay ⭐ {stars}"
    return "Pay with Stars"


def caption_has_checkout(text: str) -> bool:
    body = text or ""
    return any(marker in body for marker in CHECKOUT_CAPTION_MARKERS)


def strip_checkout_caption_lines(text: str) -> str:
    """Remove inline 💳 checkout anchors (idempotent re-sync)."""
    cleaned = _CHECKOUT_CAPTION_LINE_RE.sub("", text or "")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def strip_bare_vip_links_from_caption(text: str) -> str:
    """
    Remove free AOF VIP channel/subscription invite anchors from caption HTML.
    VIP access is sold via inline Pay ⭐ buttons + payment bot — never bare t.me/+ joins.
    """
    body = strip_checkout_caption_lines(text or "")
    body = _BARE_VIP_FOOTER_BIT_RE.sub("", body)
    body = _BARE_VIP_ANCHOR_RE.sub("@aofsubscriptions_bot", body)
    for candidate in (vip_subscription_invite_url(), vip_primary_invite_url()):
        c = (candidate or "").strip()
        if not c:
            continue
        esc = re.escape(c)
        body = re.sub(
            rf'<a\s+href="{esc}"[^>]*>([^<]*)</a>',
            r"@aofsubscriptions_bot",
            body,
            flags=re.I,
        )
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def scrub_caption_for_network_post(text: str) -> str:
    """Full caption sanitizer before send or DB re-sync."""
    return strip_bare_vip_links_from_caption(text)


def dedupe_url_buttons(buttons: list) -> list[dict]:
    """Drop duplicate URL buttons (same url or same label)."""
    out: list[dict] = []
    seen_urls: set[str] = set()
    seen_labels: set[str] = set()
    for btn in buttons or []:
        if not isinstance(btn, dict):
            continue
        text = str(btn.get("text") or "").strip()
        url = str(btn.get("url") or "").strip()
        if not text or not url:
            continue
        key_url = url.lower().rstrip("/")
        key_label = text.lower()
        if key_url in seen_urls or key_label in seen_labels:
            continue
        seen_urls.add(key_url)
        seen_labels.add(key_label)
        out.append({"text": text[:64], "url": url[:512]})
    return out


def resolve_vip_promo_url(db: Session, plan_id: int) -> str:
    """
    Checkout URL for footers/bulletins — subscription invite or payment-bot deep link.
    Never falls back to raw admin channel invites.
    """
    pid = normalize_checkout_plan_id(db, int(plan_id))
    primary, _kind = resolve_primary_checkout_url(db, pid)
    if primary:
        return primary
    bot = bot_checkout_url(pid)
    if bot:
        return bot
    pay = _payment_bot_username() or "aofsubscriptions_bot"
    return f"https://t.me/{pay}?start=subscribe"


def _default_stars_button_label(plan: SubscriptionPlan) -> str:
    stars = int(plan.price_stars or 0)
    name = (plan.name or "Subscribe").strip()[:36]
    if use_vip_star_subscription() and vip_subscription_invite_url():
        return f"⭐ Subscribe — {stars}⭐"
    if stars > 0:
        return f"⭐ {name} — {stars}⭐"
    return "⭐ Subscribe"


def resolve_primary_checkout_url(
    db: Session,
    plan_id: int,
    *,
    referral_code: str | None = None,
) -> tuple[str | None, str]:
    """
    Return (url, kind) where kind is
    'stars_invoice_link' | 'bot_deep_link'.

    Network posts never use bare VIP channel/subscription invites — those skip payment
    for admins and already-subscribed users. One-tap Stars modal uses createInvoiceLink;
    fallback is payment-bot deep link (Stars + crypto menu).
    """
    plan_id = normalize_checkout_plan_id(db, int(plan_id))
    if use_invoice_link_checkout():
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
        if plan and plan.is_active is not False and int(plan.price_stars or 0) > 0:
            link = create_stars_invoice_link(plan_to_invoice_link_dict(plan))
            if link and not is_bare_vip_invite_url(link):
                return link, "stars_invoice_link"

    bot = bot_checkout_url(plan_id, referral_code)
    if bot:
        return bot, "bot_deep_link"
    return bot_checkout_url(plan_id, referral_code, menu=True), "bot_deep_link"


def build_checkout_caption_line(
    db: Session,
    plan_id: int,
    *,
    multi_album_media: bool = False,
    referral_code: str | None = None,
) -> str:
    """
    Caption checkout anchor — only for multi-item albums (Telegram cannot attach URL
    buttons to multi-media albums). Single-image posts use inline Pay ⭐ buttons only.
    """
    if not multi_album_media:
        return ""

    pid = normalize_checkout_plan_id(db, int(plan_id))
    url = bot_checkout_url(int(pid), referral_code, menu=True)
    if not url:
        bot = _payment_bot_username() or "aofsubscriptions_bot"
        url = f"https://t.me/{bot}?start=cm{int(pid)}"
    marker = checkout_caption_label()
    return f"\n💳 <a href=\"{html.escape(url, quote=True)}\">{html.escape(marker)}</a>"


def refresh_checkout_caption_for_send(
    caption: str,
    db: Session,
    plan_id: int,
    *,
    multi_album_media: bool,
    referral_code: str | None = None,
) -> str:
    """At send time: strip stale checkout anchors; add bot deep link only for multi-album."""
    if not caption or not plan_id:
        return caption
    body = strip_checkout_caption_lines(caption)
    if not multi_album_media:
        return body
    pid = normalize_checkout_plan_id(db, int(plan_id))
    line = build_checkout_caption_line(
        db,
        int(pid),
        multi_album_media=True,
        referral_code=referral_code,
    )
    return (body + line) if body else line.lstrip("\n")


def checkout_followup_caption_html(db: Session, plan_id: int) -> str:
    from app.services.aof_vip_deal_copy import build_vip_deal_caption_html

    return build_vip_deal_caption_html(db, int(plan_id), include_urgency=True)


def checkout_bot_followup_enabled() -> bool:
    """Reliable Pay ⭐ delivery: Bot API reply under Telethon-sent posts (all channels/groups)."""
    raw = (os.getenv("TBCC_CHECKOUT_BOT_FOLLOWUP") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


async def deliver_stars_checkout_bot_followup(
    channel_identifier: str,
    db: Session,
    *,
    plan_id: int,
    reply_to_message_id: int,
    message_thread_id: int | None = None,
    checkout_button_label: str | None = None,
    checkout_referral_code: str | None = None,
    include_bot_fallback: bool = True,
) -> int | None:
    """
    Post silent Bot API reply with Pay ⭐ invoice button(s).
    Use after every Telethon scheduled/relay send — editMessageReplyMarkup cannot patch poster-session posts.
    """
    if not checkout_bot_followup_enabled():
        return None
    if not plan_id or not reply_to_message_id:
        return None
    if checkout_blocked_for_telegram_identifier(channel_identifier):
        logger.debug(
            "checkout Bot API follow-up skipped: storage hub chat=%s",
            channel_identifier,
        )
        return None

    from app.utils.telegram_peer import normalize_telethon_peer_identifier
    from app.services.telegram_bot_markup import send_message_with_inline_keyboard

    merged = merge_checkout_buttons(
        [],
        db,
        checkout_stars_enabled=True,
        checkout_stars_plan_id=int(plan_id),
        checkout_button_label=checkout_button_label,
        checkout_referral_code=checkout_referral_code,
        include_bot_fallback=include_bot_fallback,
        allow_inline_checkout=True,
    )
    if not merged:
        return None

    caption = checkout_followup_caption_html(db, int(plan_id))
    chat_id = normalize_telethon_peer_identifier(channel_identifier)
    mid = await send_message_with_inline_keyboard(
        chat_id,
        text=caption,
        buttons_data=merged,
        reply_to_message_id=int(reply_to_message_id),
        message_thread_id=message_thread_id,
        disable_notification=True,
    )
    if mid:
        logger.info(
            "checkout Bot API follow-up chat=%s reply_to=%s msg=%s plan=%s",
            chat_id,
            reply_to_message_id,
            mid,
            plan_id,
        )
    return mid


def merge_checkout_buttons(
    base: list,
    db: Session,
    *,
    checkout_stars_enabled: bool,
    checkout_stars_plan_id: int | None,
    checkout_button_label: str | None = None,
    checkout_referral_code: str | None = None,
    include_bot_fallback: bool = True,
    allow_inline_checkout: bool = True,
) -> list:
    """
    Append checkout URL button(s) to scheduled / relay posts.
    Primary: native VIP Stars subscription link when configured.
    Fallback row: payment bot deep link (Stars invoice + crypto).
    allow_inline_checkout=False skips buttons (multi-item albums — use caption link + follow-up post).
    """
    out = dedupe_url_buttons(list(base) if base else [])
    if not checkout_stars_enabled or not checkout_stars_plan_id:
        return out

    checkout_stars_plan_id = normalize_checkout_plan_id(db, int(checkout_stars_plan_id))
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(checkout_stars_plan_id)).first()
    if not plan or plan.is_active is False or int(plan.price_stars or 0) <= 0:
        logger.warning("checkout: plan %s missing, inactive, or has no Stars price", checkout_stars_plan_id)
        return out

    if not allow_inline_checkout:
        return out

    primary_url, kind = resolve_primary_checkout_url(db, int(checkout_stars_plan_id), referral_code=checkout_referral_code)
    bot_menu = kind == "stars_invoice_link"
    bot_url = bot_checkout_url(
        int(checkout_stars_plan_id),
        checkout_referral_code,
        menu=bot_menu,
    )

    if not primary_url and not bot_url:
        logger.warning("checkout: no invoice URL or payment bot username")
        return out

    if primary_url and is_bare_vip_invite_url(primary_url):
        logger.warning("checkout: blocked bare VIP invite URL on post")
        primary_url = bot_url

    label = (checkout_button_label or "").strip()
    if not label:
        if kind == "stars_invoice_link":
            label = stars_pay_button_label(plan)
        else:
            label = _default_stars_button_label(plan)
    if len(label) > 64:
        label = label[:63] + "…"

    existing_urls = {str(b.get("url") or "").strip().lower().rstrip("/") for b in out}

    if primary_url and primary_url.strip().lower().rstrip("/") not in existing_urls:
        out.append({"text": label, "url": primary_url})
        existing_urls.add(primary_url.strip().lower().rstrip("/"))

    if (
        include_bot_fallback
        and bot_url
        and kind == "stars_invoice_link"
        and bot_url.strip().lower().rstrip("/") not in existing_urls
        and bot_url != primary_url
    ):
        fb = (os.getenv("TBCC_CHECKOUT_BOT_FALLBACK_LABEL") or BOT_FALLBACK_LABEL).strip()[:64]
        out.append({"text": fb, "url": bot_url})

    try:
        from app.services.gumroad_ping import (
            append_vip_checkout_hints,
            gumroad_checkout_enabled,
            product_url_for_plan,
            recurrence_for_plan,
        )

        if gumroad_checkout_enabled():
            gr_base = product_url_for_plan(int(checkout_stars_plan_id))
            if gr_base:
                plan_payload = {
                    "duration_days": int(plan.duration_days or 30),
                    "nowpayments_price_usd": float(plan.nowpayments_price_usd or 0),
                }
                gr_url = append_vip_checkout_hints(
                    gr_base,
                    recurrence=recurrence_for_plan(plan_payload),
                )
                gr_key = gr_url.strip().lower().rstrip("/")
                if gr_key and gr_key not in existing_urls:
                    gr_label = (
                        os.getenv("TBCC_FIAT_CHECKOUT_BUTTON_LABEL")
                        or os.getenv("TBCC_GUMROAD_CHECKOUT_BUTTON_LABEL")
                    )
                    if not gr_label or re.search(r"gumroad", gr_label, re.I):
                        from app.services.fiat_checkout_labels import fiat_checkout_button_label

                        gr_label = fiat_checkout_button_label()
                    out.append({"text": str(gr_label).strip()[:64], "url": gr_url[:512]})
    except Exception:
        logger.debug("checkout: gumroad button skipped", exc_info=True)

    return out


def _bot_token() -> str:
    return (os.getenv("BOT_TOKEN") or os.getenv("TBCC_PAYMENT_BOT_TOKEN") or "").strip()


def create_vip_subscription_invite_link(
    *,
    subscription_price: int,
    name: str = "AOF VIP — network checkout",
    chat_id: str | None = None,
) -> dict[str, Any]:
    """
    Call Telegram createChatSubscriptionInviteLink for AOF VIP.
    Requires payment bot admin on the channel with can_invite_users.
    """
    token = _bot_token()
    if not token:
        return {"ok": False, "error": "BOT_TOKEN unset"}

    stars = int(subscription_price)
    if stars < 1 or stars > 10_000:
        return {"ok": False, "error": f"subscription_price must be 1–10000 Stars, got {stars}"}

    cid = (chat_id or vip_channel_ident()).strip()
    body = {
        "chat_id": cid,
        "subscription_period": SUBSCRIPTION_PERIOD_SECONDS,
        "subscription_price": stars,
        "name": (name or "AOF VIP")[:32],
    }
    url = f"https://api.telegram.org/bot{token}/createChatSubscriptionInviteLink"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, json=body)
            data = r.json()
    except Exception as e:
        logger.exception("createChatSubscriptionInviteLink failed")
        return {"ok": False, "error": str(e)}

    if not data.get("ok"):
        return {"ok": False, "error": data.get("description") or data}

    link = (data.get("result") or {}).get("invite_link")
    return {
        "ok": True,
        "invite_link": link,
        "subscription_price": stars,
        "subscription_period": SUBSCRIPTION_PERIOD_SECONDS,
        "chat_id": cid,
        "raw": data.get("result"),
    }
