"""Anonymous public sale announce (copy + throttle + queue hook)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.sale_public_announce import (
    build_sale_announce_html,
    build_sale_announce_plain,
    queue_public_sale_announce,
    run_public_sale_announce,
    sale_announce_enabled,
)


def test_build_sale_announce_html_loot_key_no_user_id():
    html = build_sale_announce_html(sale_kind="loot_key", payment_method="stars")
    assert "Loot Room key sold" in html
    assert "via ⭐" in html
    assert "7787282561" not in html
    assert "telegram_user" not in html.lower()
    assert "buyer" not in html.lower()
    plain = build_sale_announce_plain(sale_kind="loot_key", payment_method="stars")
    assert "Loot Room key sold" in plain
    assert "<" not in plain or "http" in plain  # tags stripped; links may remain as text


def test_build_sale_announce_html_subscription_and_pack():
    sub = build_sale_announce_html(sale_kind="subscription", payment_method="nowpayments")
    assert "Subscription sold" in sub
    assert "via crypto" in sub
    pack = build_sale_announce_html(sale_kind="pack", plan_name="VIP Pack A", payment_method="stars")
    assert "Pack sold" in pack
    assert "VIP Pack A" in pack


def test_sale_announce_enabled_default_on(monkeypatch):
    monkeypatch.delenv("TBCC_SALE_ANNOUNCE_ENABLED", raising=False)
    assert sale_announce_enabled() is True
    monkeypatch.setenv("TBCC_SALE_ANNOUNCE_ENABLED", "0")
    assert sale_announce_enabled() is False


def test_queue_public_sale_announce_enqueues_celery(monkeypatch):
    monkeypatch.setenv("TBCC_SALE_ANNOUNCE_ENABLED", "1")
    mock_delay = MagicMock()
    with patch("app.workers.sale_announce_worker.announce_public_sale") as task:
        task.delay = mock_delay
        out = queue_public_sale_announce(
            product_type="subscription",
            bot_section="loot",
            plan_name="Loot Room 24h key",
            payment_method="stars",
        )
    assert out.get("ok") is True
    assert out.get("sale_kind") == "loot_key"
    mock_delay.assert_called_once()
    args = mock_delay.call_args[0]
    assert args[0] == "loot_key"


def test_run_public_sale_announce_disabled(monkeypatch):
    monkeypatch.setenv("TBCC_SALE_ANNOUNCE_ENABLED", "0")
    db = MagicMock()
    out = run_public_sale_announce(db, sale_kind="loot_key")
    assert out.get("skipped") is True
    assert out.get("reason") == "disabled"


def test_run_public_sale_announce_throttled(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TBCC_SALE_ANNOUNCE_ENABLED", "1")
    monkeypatch.setenv("TBCC_SALE_ANNOUNCE_MIN_INTERVAL_S", "3600")
    monkeypatch.setenv("TBCC_SALE_ANNOUNCE_TARGETS", "buffer")
    cooldown = tmp_path / "sale-announce-cooldown.json"
    cooldown.write_text(json.dumps({"loot_key": 9_999_999_999.0, "_any": 9_999_999_999.0}), encoding="utf-8")
    with patch("app.services.sale_public_announce._cooldown_path", return_value=cooldown):
        out = run_public_sale_announce(MagicMock(), sale_kind="loot_key")
    assert out.get("skipped") is True
    assert out.get("reason") == "throttled"


def test_run_public_sale_announce_network_and_buffer(monkeypatch):
    monkeypatch.setenv("TBCC_SALE_ANNOUNCE_ENABLED", "1")
    monkeypatch.setenv("TBCC_SALE_ANNOUNCE_MIN_INTERVAL_S", "0")
    monkeypatch.setenv("TBCC_SALE_ANNOUNCE_TARGETS", "network,buffer")
    db = MagicMock()
    with (
        patch(
            "app.services.sale_public_announce.announce_sale_to_telegram_network",
            return_value={"ok": True, "count": 3},
        ) as net,
        patch(
            "app.services.sale_public_announce.announce_sale_to_buffer",
            return_value={"ok": True},
        ) as buf,
        patch("app.services.sale_public_announce._throttle_ok", return_value=True),
    ):
        out = run_public_sale_announce(
            db, sale_kind="loot_key", payment_method="stars", force=True
        )
    assert out.get("ok") is True
    net.assert_called_once()
    buf.assert_called_once()
    assert "telegram_network" in out
    assert "buffer" in out


def test_notify_sale_fulfilled_queues_public_announce(monkeypatch):
    monkeypatch.setenv("TBCC_PAYMENT_NOTIFY", "0")  # admin off — public still fires
    queued: list[dict] = []

    def _capture(**kwargs):
        queued.append(kwargs)
        return {"ok": True}

    with patch("app.services.sale_public_announce.queue_public_sale_announce", side_effect=_capture):
        from app.services.payment_admin_notify import notify_sale_fulfilled

        notify_sale_fulfilled(
            telegram_user_id=999001,
            plan_name="Loot Room 24h key",
            product_type="subscription",
            payment_method="stars",
            bot_section="loot",
            amount_stars=100,
        )
    assert len(queued) == 1
    assert queued[0]["bot_section"] == "loot"
    assert "999001" not in str(queued[0])
