"""Lifecycle DM outreach — subscription renewal + loot + companion re-engage."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models.loot import LootPlayerStats
from app.models.subscription import Subscription
from app.services.lifecycle_dm_copy import (
    CompanionReengageSegment,
    LootReengageSegment,
    SubscriptionLifecycleSegment,
    build_companion_reengage_message,
    build_loot_reengage_message,
    build_subscription_lifecycle_message,
    renew_checkout_url,
)
from app.services.lifecycle_dm_outreach import (
    LifecycleDmCandidate,
    _dedupe_by_user,
    _subscription_candidates_for_segment,
    collect_lifecycle_candidates,
    send_lifecycle_dm_sync,
)


def test_renew_checkout_url_uses_plan_id():
    with patch.dict("os.environ", {"TBCC_PAYMENT_BOT_USERNAME": "paybot"}, clear=False):
        assert renew_checkout_url(plan_id=10) == "https://t.me/paybot?start=cm10"
        assert renew_checkout_url() == "https://t.me/paybot?start=renew"


def test_subscription_copy_pre_expiry_3d():
    msg = build_subscription_lifecycle_message(
        SubscriptionLifecycleSegment.PRE_EXPIRY_3D,
        plan_name="AOF VIP",
        expires_at=datetime(2026, 8, 10, 12, 0, 0),
        plan_id=10,
    )
    assert "3 days left" in msg.html
    assert "AOF VIP" in msg.html
    assert "god roll" in msg.html.lower()
    assert "Friday mega" in msg.html
    assert "cm10" in msg.button_url


def test_loot_reengage_copy_7d():
    msg = build_loot_reengage_message(LootReengageSegment.INACTIVE_7D)
    assert "week" in msg.html.lower()
    assert "loot_free" in msg.button_url


def test_companion_reengage_copy_7d_user_example():
    msg = build_companion_reengage_message(
        CompanionReengageSegment.INACTIVE_7D,
        telegram_user_id=0,
    )
    assert "Hey baby" in msg.html
    assert "only one I'm here for" in msg.html
    assert "missed_you" in msg.button_url
    assert msg.button_text == "💬 Talk to me"


def test_companion_reengage_copy_rotates_by_user():
    a = build_companion_reengage_message(
        CompanionReengageSegment.INACTIVE_7D,
        telegram_user_id=0,
    )
    b = build_companion_reengage_message(
        CompanionReengageSegment.INACTIVE_7D,
        telegram_user_id=1,
    )
    assert a.html != b.html


def test_subscription_candidates_match_expiry_date():
    today = datetime.utcnow().date()
    target = today + timedelta(days=3)
    db = MagicMock()
    sub_match = Subscription(
        id=1,
        telegram_user_id=111,
        plan_id=10,
        plan="VIP",
        status="active",
        expires_at=datetime(target.year, target.month, target.day, 18, 0, 0),
    )
    sub_other = Subscription(
        id=2,
        telegram_user_id=222,
        plan_id=10,
        plan="VIP",
        status="active",
        expires_at=datetime(target.year, target.month, target.day, 18, 0, 0) + timedelta(days=1),
    )
    db.query.return_value.filter.return_value.all.return_value = [sub_match, sub_other]

    found = _subscription_candidates_for_segment(db, SubscriptionLifecycleSegment.PRE_EXPIRY_3D)
    assert len(found) == 1
    assert found[0].telegram_user_id == 111
    assert found[0].segment == "pre_expiry_3d"


def test_post_expiry_candidate_uses_expired_status():
    today = datetime.utcnow().date()
    target = today - timedelta(days=7)
    db = MagicMock()
    sub = Subscription(
        id=5,
        telegram_user_id=333,
        plan_id=10,
        plan="VIP",
        status="expired",
        expires_at=datetime(target.year, target.month, target.day, 6, 0, 0),
    )
    db.query.return_value.filter.return_value.all.return_value = [sub]

    found = _subscription_candidates_for_segment(db, SubscriptionLifecycleSegment.POST_EXPIRY_7D)
    assert len(found) == 1
    assert found[0].segment == "post_expiry_7d"


def test_dedupe_by_user_keeps_first_segment():
    a = LifecycleDmCandidate(
        kind="subscription",
        segment="pre_expiry_3d",
        telegram_user_id=99,
        entity_id=1,
    )
    b = LifecycleDmCandidate(
        kind="companion",
        segment="companion_inactive_7d",
        telegram_user_id=99,
        entity_id=99,
    )
    out = _dedupe_by_user([a, b])
    assert len(out) == 1
    assert out[0].segment == "pre_expiry_3d"


def test_send_skips_when_already_sent():
    r = MagicMock()
    r.get.side_effect = lambda key: "1" if "lifecycle_dm:sent" in key else None
    db = MagicMock()
    candidate = LifecycleDmCandidate(
        kind="subscription",
        segment="pre_expiry_1d",
        telegram_user_id=42,
        entity_id=7,
        plan_name="VIP",
        expires_at=datetime.utcnow(),
        plan_id=10,
    )
    with patch("app.services.lifecycle_dm_outreach._redis", return_value=r):
        with patch("app.services.lifecycle_dm_outreach.lifecycle_dm_enabled", return_value=True):
            out = send_lifecycle_dm_sync(db, candidate)
    assert out["skipped"] is True
    assert out["reason"] == "already_sent"


def test_collect_returns_empty_when_disabled():
    db = MagicMock()
    with patch("app.services.lifecycle_dm_outreach.subscription_lifecycle_enabled", return_value=False):
        with patch("app.services.lifecycle_dm_outreach.companion_reengage_enabled", return_value=False):
            with patch("app.services.lifecycle_dm_outreach.loot_reengage_enabled", return_value=False):
                assert collect_lifecycle_candidates(db) == []


def test_companion_candidates_from_last_active_zset():
    with patch(
        "app.services.lifecycle_dm_outreach.list_companion_user_ids_active_on_date",
        return_value=[555, 666],
    ):
        with patch(
            "app.services.lifecycle_dm_outreach.companion_had_real_session",
            side_effect=lambda uid: uid == 555,
        ):
            from app.services.lifecycle_dm_copy import CompanionReengageSegment
            from app.services.lifecycle_dm_outreach import _companion_candidates_for_segment

            found = _companion_candidates_for_segment(CompanionReengageSegment.INACTIVE_7D)
    assert len(found) == 1
    assert found[0].telegram_user_id == 555
    assert found[0].kind == "companion"
    assert found[0].segment == "companion_inactive_7d"
