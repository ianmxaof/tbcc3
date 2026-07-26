"""Tier card delivery fallbacks and key compensation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_encode_reveal_card_mp4_falls_back_when_celery_empty(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_REVEAL_VIDEO", "1")
    monkeypatch.setenv("TBCC_LOOT_BORDER_REVEAL", "1")
    monkeypatch.setenv("TBCC_LOOT_REVEAL_VIDEO_CELERY", "1")

    fake_mp4 = b"ftyp" + b"x" * 5000

    with patch(
        "app.workers.loot_reveal_video_worker.build_reveal_card_mp4_task.apply_async"
    ) as apply_mock, patch(
        "app.services.loot_preview_delivery.build_reveal_card_mp4",
        return_value=(fake_mp4, "inline"),
    ) as inline_mock:
        apply_mock.return_value.get.return_value = {"ok": False, "reason": "unregistered"}

        from app.services.loot_preview_delivery import _encode_reveal_card_mp4

        mp4, note = asyncio.run(
            _encode_reveal_card_mp4(b"", {"rarity_tier": 4, "seed": 1})
        )

    assert mp4 == fake_mp4
    assert note == "inline"
    inline_mock.assert_called_once()


def test_compensate_loot_key_card_failure_extends_subscription(db):
    from datetime import datetime, timedelta

    from app.models.subscription import Subscription
    from app.models.subscription_plan import SubscriptionPlan
    from app.services.subscription_access import compensate_loot_key_card_failure

    plan = SubscriptionPlan(
        name="Loot 24h",
        product_type="subscription",
        bot_section="loot",
        duration_days=1,
        is_active=True,
    )
    db.add(plan)
    db.flush()
    exp = datetime.utcnow() + timedelta(hours=6)
    sub = Subscription(
        telegram_user_id=424242,
        plan_id=plan.id,
        status="active",
        expires_at=exp,
    )
    db.add(sub)
    db.commit()

    out = compensate_loot_key_card_failure(db, 424242)
    assert out["ok"] is True
    db.refresh(sub)
    assert sub.expires_at > exp + timedelta(hours=23)
