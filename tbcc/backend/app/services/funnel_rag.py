"""Funnel strategy playbook retrieval — parallel to secretary RAG / caption snippets."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.funnel_strategy import FunnelStrategyEntry

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
_FORBIDDEN_PATTERNS = frozenset({"impersonate_moderation", "fake_abuse_team"})


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def search_funnel_strategies(
    db: Session,
    *,
    surface: str | None = None,
    pattern: str | None = None,
    query: str | None = None,
    limit: int = 5,
) -> list[FunnelStrategyEntry]:
    q = db.query(FunnelStrategyEntry).filter(FunnelStrategyEntry.is_active.is_(True))
    if surface:
        q = q.filter(FunnelStrategyEntry.surface == surface.strip().lower())
    if pattern:
        q = q.filter(FunnelStrategyEntry.pattern == pattern.strip().lower())
    rows = q.order_by(FunnelStrategyEntry.id.desc()).limit(max(1, min(limit * 3, 30))).all()
    if not query:
        return rows[:limit]

    tokens = _tokenize(query)
    if not tokens:
        return rows[:limit]

    scored: list[tuple[float, FunnelStrategyEntry]] = []
    for row in rows:
        if row.pattern in _FORBIDDEN_PATTERNS:
            continue
        hay = " ".join(
            x
            for x in (
                row.title or "",
                row.pattern or "",
                row.surface or "",
                row.copy_template or "",
                row.visual_notes or "",
                row.risk_tags or "",
            )
        )
        hits = len(tokens & _tokenize(hay))
        if hits:
            scored.append((hits, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def build_funnel_context(
    db: Session,
    *,
    surface: str,
    goal: str | None = None,
    limit: int = 3,
) -> str:
    """Compact playbook block for scheduler seeding / growth-hub."""
    rows = search_funnel_strategies(db, surface=surface, query=goal, limit=limit)
    if not rows:
        return ""
    lines = ["Funnel playbook:"]
    for r in rows:
        title = (r.title or r.pattern).strip()
        copy = (r.copy_template or "").strip()
        visual = (r.visual_notes or "").strip()
        chunk = f"- {title}"
        if copy:
            chunk += f": {copy[:280]}"
        if visual:
            chunk += f" [{visual[:120]}]"
        lines.append(chunk)
    return "\n".join(lines)


def seed_default_funnel_strategies(db: Session) -> int:
    """Idempotent seed — returns count created."""
    defaults: list[dict[str, Any]] = [
        {
            "title": "Mainhub single durable CTA",
            "pattern": "pinned_blur_cta",
            "surface": "mainhub",
            "copy_template": "One pinned photo + Pay/Crypto/Card — no duplicate checkout forwards.",
            "visual_notes": "SFW Gemini poster shuffle on liveness pings only.",
            "risk_tags": "placement",
        },
        {
            "title": "Ephemeral pin liveness",
            "pattern": "pin_notify_delete",
            "surface": "mainhub",
            "copy_template": "3x/day PT — pin shuffled poster, delete after 45s. Durable CTA owns conversion.",
            "visual_notes": "Notify subscribers without cluttering channel history.",
            "risk_tags": "liveness",
        },
        {
            "title": "Flash Stars album urgency",
            "pattern": "flash_stars_album",
            "surface": "dm",
            "copy_template": "Blurred preview + single Pay button — urgency copy, not fake moderation.",
            "visual_notes": "Study competitor DM→channel traps; never impersonate Telegram staff.",
            "risk_tags": "urgency,no_impersonation",
        },
        {
            "title": "Bio trap to channel",
            "pattern": "bio_trap",
            "surface": "x",
            "copy_template": "X teaser → gated hub link → mainhub pin CTA. No bare t.me in tweet.",
            "visual_notes": "Affiliate-first preview card when possible.",
            "risk_tags": "x,gate",
        },
        {
            "title": "High-attention lane wrap",
            "pattern": "gate_wrap_required",
            "surface": "bop",
            "copy_template": "BOP/Taboo Buffer mirrors must use Linkvertise gates — bare URLs blocked.",
            "visual_notes": "Pre-mirror content governance for scraped media.",
            "risk_tags": "bop,taboo,compliance",
        },
        {
            "title": "FOMO scarcity copy",
            "pattern": "fomo_scarcity",
            "surface": "hub",
            "copy_template": "Limited drop / ending soon — route to VIP or packs, not dead plan ids.",
            "visual_notes": "Rotate from caption snippet library + funnel RAG.",
            "risk_tags": "conversion",
        },
    ]
    created = 0
    for d in defaults:
        exists = (
            db.query(FunnelStrategyEntry)
            .filter(
                FunnelStrategyEntry.pattern == d["pattern"],
                FunnelStrategyEntry.surface == d["surface"],
            )
            .first()
        )
        if exists:
            continue
        db.add(FunnelStrategyEntry(**d, is_active=True))
        created += 1
    if created:
        db.commit()
    return created


def seed_human_gate_funnel_strategies(db: Session) -> int:
    """Human-gate opt-in ladder — robot button → invite → paced DM list."""
    entries: list[dict[str, Any]] = [
        {
            "title": "Human gate opt-in (robot button)",
            "pattern": "human_gate_opt_in",
            "surface": "payment_bot",
            "copy_template": (
                "Channel/group teaser → payment bot ?start=gate_loot → inline "
                "'I'm not a robot' → unlock invite. Records funnel_dm_consents row; "
                "enables paced DM outreach (Telegram bot-contact surface)."
            ),
            "visual_notes": "One honest tap — not a fake CAPTCHA widget. Loot Room default invite.",
            "risk_tags": "pacing,opt_in,honest_consent,no_impersonation",
        },
        {
            "title": "Paced DM ladder after gate",
            "pattern": "human_gate_dm_ladder",
            "surface": "dm",
            "copy_template": (
                "TBCC_HUMAN_GATE_DM_DELAY_DAYS after ack → stars_bait DM pace tick. "
                "Rotate FOMO / honest deal / VIP / loot key copy. Cooldown per product."
            ),
            "visual_notes": "Email-list analogue; only users who tapped robot ack.",
            "risk_tags": "pacing,outreach,fomo,honest_pricing",
        },
        {
            "title": "Channel teaser → gate handoff",
            "pattern": "human_gate_channel_teaser",
            "surface": "hub",
            "copy_template": (
                "Main/Loot post: 'Free room access — confirm human in bot' + "
                "t.me/payment?start=gate_loot. No bare invite until ack."
            ),
            "visual_notes": "Pairs with stars_bait_channel_pace scheduler; gate before link dump.",
            "risk_tags": "pacing,main_group,conversion",
        },
        {
            "title": "Historic user remarketing",
            "pattern": "human_gate_remarketing",
            "surface": "dm",
            "copy_template": (
                "Users who paid or rolled loot but never gate-acked: optional ?start=gate "
                "before next upsell. Do not DM cold users who never pressed Start."
            ),
            "visual_notes": "Merge consent pool with subscription/loot ids in outreach collector.",
            "risk_tags": "pacing,remarketing,telegram_tos",
        },
    ]
    created = 0
    for d in entries:
        exists = (
            db.query(FunnelStrategyEntry)
            .filter(
                FunnelStrategyEntry.pattern == d["pattern"],
                FunnelStrategyEntry.surface == d["surface"],
            )
            .first()
        )
        if exists:
            continue
        db.add(FunnelStrategyEntry(**d, is_active=True))
        created += 1
    if created:
        db.commit()
    return created


def seed_stars_bait_funnel_strategies(db: Session) -> int:
    """Competitor study + AOF Stars bait patterns (DM / payment bot)."""
    entries: list[dict[str, Any]] = [
        {
            "title": "Stripchat-style welcome trap",
            "pattern": "stars_dm_welcome_trap",
            "surface": "dm",
            "copy_template": (
                "Welcome. All content is here 👇 + single ⭐ Full access ✅ button → "
                "payment bot Stars checkout. Study: @arturmoreirazerozerobot."
            ),
            "visual_notes": "Short hook, one inline URL button, no fake Telegram UI chrome.",
            "risk_tags": "urgency,competitor_study,no_impersonation",
            "screenshot_ref": "competitor/stripchat-bot-welcome-trap",
        },
        {
            "title": "Shock curiosity hook",
            "pattern": "stars_dm_shock_hook",
            "surface": "dm",
            "copy_template": (
                "Hey 👋 you need to see what's going on — shocked 😳 + 👉 Visit button. "
                "Route to bait_loot / bait_day / bait_vip handoffs."
            ),
            "visual_notes": "Emotional curiosity; still honest AOF product on the other side.",
            "risk_tags": "urgency,curiosity,no_impersonation",
        },
        {
            "title": "Discount scarcity FOMO",
            "pattern": "stars_dm_discount_fomo",
            "surface": "dm",
            "copy_template": (
                "🔥 limited window / exclusive drops ⌛ + 📹 Grab deal → Stars invoice. "
                "Use real SKUs (loot key, lane pass, VIP) — no fake % off."
            ),
            "visual_notes": "Timer emoji optional; do not fabricate discounts without a real promo.",
            "risk_tags": "fomo,conversion,honest_pricing",
        },
        {
            "title": "Native subscribe frame copy",
            "pattern": "stars_dm_native_subscribe",
            "surface": "payment_bot",
            "copy_template": (
                "Mirror Telegram's Subscribe to Channel wording in plain text — "
                "Subscribe to {product} for {stars} Stars per month? + real cm{{plan_id}} checkout."
            ),
            "visual_notes": "Never render fake Stars modal; use Bot API invoice / subscription link only.",
            "risk_tags": "stars_checkout,no_fake_ui",
        },
        {
            "title": "Loot key bait handoff",
            "pattern": "stars_bait_loot_key",
            "surface": "payment_bot",
            "copy_template": "start=bait_loot → 24h Loot Room key menu → cm{{loot_plan_id}} Stars.",
            "visual_notes": "Pairs with loot_bot cross-links.",
            "risk_tags": "loot_key,conversion",
        },
        {
            "title": "Lane day pass bait",
            "pattern": "stars_bait_day_pass",
            "surface": "payment_bot",
            "copy_template": "start=bait_day → Lane Pass 24h → cm{{lane_plan_id}}.",
            "visual_notes": "Single-lane one-use invite after pay.",
            "risk_tags": "day_pass,conversion",
        },
        {
            "title": "VIP subscription bait",
            "pattern": "stars_bait_subscription",
            "surface": "payment_bot",
            "copy_template": "start=bait_vip → VIP 1500⭐/30d → native subscription invite or cm10 menu.",
            "visual_notes": "Primary revenue SKU; card/USD + crypto as secondary row.",
            "risk_tags": "subscription,revenue",
        },
        {
            "title": "Paced DM outreach cadence",
            "pattern": "stars_bait_dm_pace",
            "surface": "dm",
            "copy_template": (
                "Celery beat TBCC_STARS_BAIT_DM_INTERVAL_MIN — batch TBCC_STARS_BAIT_DM_BATCH, "
                "cooldown TBCC_STARS_BAIT_DM_COOLDOWN_DAYS. Only users with prior bot contact."
            ),
            "visual_notes": "Rotate product × style matrix from stars_bait_copy.",
            "risk_tags": "pacing,outreach,telegram_tos",
        },
        {
            "title": "Channel bait pace scheduler",
            "pattern": "stars_bait_channel_pace",
            "surface": "hub",
            "copy_template": (
                "Main group scheduler AOF — stars bait channel pace — content_variations "
                "from bait matrix + checkout buttons."
            ),
            "visual_notes": "Silent posts; complements liveness heartbeat.",
            "risk_tags": "pacing,main_group",
        },
    ]
    created = 0
    for d in entries:
        exists = (
            db.query(FunnelStrategyEntry)
            .filter(
                FunnelStrategyEntry.pattern == d["pattern"],
                FunnelStrategyEntry.surface == d["surface"],
            )
            .first()
        )
        if exists:
            continue
        db.add(FunnelStrategyEntry(**d, is_active=True))
        created += 1
    if created:
        db.commit()
    return created

