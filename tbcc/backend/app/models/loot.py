"""Loot room orchestration: sessions, drops, modifier pools, eligibility, dedupe.

JSON columns use Text + JSON strings for SQLite/Postgres parity (same pattern as subscription_plans).
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from datetime import datetime

from .base import Base


class LootPoolEligibility(Base):
    """Maps content_pools rows that the loot engine may draw from (with optional tier bounds)."""

    __tablename__ = "loot_pool_eligibility"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_pool_id = Column(Integer, ForeignKey("content_pools.id", ondelete="CASCADE"), nullable=False)
    loot_enabled = Column(Boolean, nullable=False, default=True)
    min_rarity_tier = Column(Integer, nullable=True)  # NULL = any; else tier >= this (1..10)
    max_rarity_tier = Column(Integer, nullable=True)  # NULL = any
    base_weight = Column(Float, nullable=False, default=1.0)

    __table_args__ = (UniqueConstraint("content_pool_id", name="uq_loot_pool_eligibility_pool"),)


class LootGameConfig(Base):
    """Singleton tunables (single row; app loads ORDER BY id LIMIT 1). Seeded by Alembic."""

    __tablename__ = "loot_game_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # JSON array length 4: P(0), P(1), P(2), P(3) modifier slots — sums to 1.0 in application
    p_modifier_slots_json = Column(Text, nullable=False)
    tag_affinity_exponent = Column(Float, nullable=False, default=1.35)
    tag_weight_floor = Column(Float, nullable=False, default=0.35)
    tag_weight_ceiling = Column(Float, nullable=False, default=3.5)
    max_dup_media_per_session = Column(Integer, nullable=False, default=0)
    pity_steps_json = Column(Text, nullable=True)  # optional JSON for pity / streak tuning
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LootIntervalTier(Base):
    """Drop cadence product tier (e.g. 60m vs 15m + bonus draws + rarity shift)."""

    __tablename__ = "loot_interval_tiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(16), unique=True, nullable=False)  # m60, m45, m30, m15
    drop_interval_seconds = Column(Integer, nullable=False)
    bonus_album_draws = Column(Integer, nullable=False, default=0)
    rarity_shift = Column(Integer, nullable=False, default=0)  # added to rolled tier before clamp 1..10


class LootCreatorSubmission(Base):
    """Self-serve creator promo applications — pending operator review before modifier pool."""

    __tablename__ = "loot_creator_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    submitted_url = Column(Text, nullable=False)
    normalized_url = Column(Text, nullable=False)
    platform_key = Column(String(32), nullable=False)
    platform_label = Column(String(32), nullable=False)
    path_handle = Column(String(64), nullable=False)
    display_name = Column(String(64), nullable=True)
    label = Column(String(256), nullable=False)
    status = Column(String(16), nullable=False, default="pending")  # pending | approved | rejected
    review_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(BigInteger, nullable=True)
    modifier_id = Column(Integer, ForeignKey("loot_modifiers.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LootModifier(Base):
    """Mega packs, Telegram groups/channels, internal routes — rolled as caption modifiers."""

    __tablename__ = "loot_modifiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(24), nullable=False)  # mega_pack | telegram_group | telegram_channel | internal_route | other
    label = Column(String(256), nullable=True)
    target_url = Column(Text, nullable=True)
    telegram_chat_id = Column(BigInteger, nullable=True)
    weight_base = Column(Float, nullable=False, default=1.0)
    rarity_focus = Column(Float, nullable=False, default=1.0)
    min_rarity_tier = Column(Integer, nullable=True)  # NULL = any; zip packs often 7+
    bypass_vip = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    source_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LootModifierTagWeight(Base):
    """Per-tag weight multiplier for a modifier when user prefs include that tbcc_tags row."""

    __tablename__ = "loot_modifier_tag_weights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    modifier_id = Column(Integer, ForeignKey("loot_modifiers.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(Integer, ForeignKey("tbcc_tags.id", ondelete="CASCADE"), nullable=False)
    multiplier = Column(Float, nullable=False, default=1.5)

    __table_args__ = (UniqueConstraint("modifier_id", "tag_id", name="uq_loot_modifier_tag_weight"),)


class LootSession(Base):
    """One paid loot run for a Telegram user."""

    __tablename__ = "loot_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    telegram_chat_id = Column(BigInteger, nullable=True)
    started_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    interval_tier_id = Column(Integer, ForeignKey("loot_interval_tiers.id"), nullable=False)
    # JSON: [{"slug":"milf","priority":1.0}, ...]
    preference_tags_json = Column(Text, nullable=False, default="[]")
    state = Column(String(24), nullable=False, default="active")  # active | expired | cancelled
    external_ref = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LootDropEvent(Base):
    """Planned or completed drop (album + modifiers)."""

    __tablename__ = "loot_drop_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("loot_sessions.id", ondelete="CASCADE"), nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    rarity_tier = Column(Integer, nullable=False)  # 1..10 = album size
    media_ids_json = Column(Text, nullable=False)  # JSON list of media.id in order
    modifier_ids_json = Column(Text, nullable=False, default="[]")
    modifier_slot_count = Column(Integer, nullable=False, default=0)
    tag_bias_snapshot_json = Column(Text, nullable=True)
    delivery_status = Column(String(16), nullable=False, default="pending")  # pending | sent | failed
    telegram_message_ids_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LootPlayerStats(Base):
    """Lifetime roll counter per Telegram user (preview + live)."""

    __tablename__ = "loot_player_stats"

    telegram_user_id = Column(BigInteger, primary_key=True)
    roll_count = Column(Integer, nullable=False, default=0)
    free_pulls_used = Column(Integer, nullable=False, default=0)
    bonus_free_pulls = Column(Integer, nullable=False, default=0)
    vip_daily_pull_at = Column(DateTime, nullable=True)
    daily_pull_at = Column(DateTime, nullable=True)
    daily_streak_days = Column(Integer, nullable=False, default=0)
    daily_streak_best = Column(Integer, nullable=False, default=0)
    first_roll_at = Column(DateTime, nullable=True)
    last_roll_at = Column(DateTime, nullable=True)


class LootReferralTracking(Base):
    """Loot-game referral: referrer earns bonus free pulls when referred user uses a pull."""

    __tablename__ = "loot_referral_tracking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    referred_user_id = Column(BigInteger, nullable=False, unique=True)
    referrer_user_id = Column(BigInteger, nullable=False, index=True)
    credited = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LootPlayerMediaSeen(Base):
    """Dedupe: media already shown to this user in loot."""

    __tablename__ = "loot_player_media_seen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    media_id = Column(Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    session_id = Column(Integer, ForeignKey("loot_sessions.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (UniqueConstraint("telegram_user_id", "media_id", name="uq_loot_player_media_seen"),)


class LootPlayerModifierSeen(Base):
    """Soft dedupe / analytics for modifiers per user."""

    __tablename__ = "loot_player_modifier_seen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    modifier_id = Column(Integer, ForeignKey("loot_modifiers.id", ondelete="CASCADE"), nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    seen_count = Column(Integer, nullable=False, default=1)

    __table_args__ = (UniqueConstraint("telegram_user_id", "modifier_id", name="uq_loot_player_modifier_seen"),)
