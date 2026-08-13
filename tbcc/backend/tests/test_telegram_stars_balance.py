"""Unit tests for Telegram Stars Bot API reconcile helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.telegram_stars_balance import (
    fetch_bot_stars_balance,
    fetch_star_transactions,
    telegram_stars_reconcile_snapshot,
)


def test_fetch_balance_missing_token(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("TBCC_PAYMENT_BOT_TOKEN", raising=False)
    out = fetch_bot_stars_balance()
    assert out["ok"] is False
    assert "unset" in (out.get("error") or "")


def test_fetch_balance_ok(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "result": {"amount": 420, "nanostar_amount": 0}}

    with patch("app.services.telegram_stars_balance.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = mock_resp
        out = fetch_bot_stars_balance()

    assert out["ok"] is True
    assert out["amount_stars"] == 420


def test_fetch_transactions_ok(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": {
            "transactions": [
                {
                    "id": "tx1",
                    "amount": {"amount": 100},
                    "date": 1700000000,
                    "source": {"invoice": {}},
                }
            ]
        },
    }
    with patch("app.services.telegram_stars_balance.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = mock_resp
        out = fetch_star_transactions(limit=5)

    assert out["ok"] is True
    assert out["count"] == 1


def test_reconcile_snapshot_shape(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "result": {"amount": 10}}
    with patch("app.services.telegram_stars_balance.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = mock_resp
        snap = telegram_stars_reconcile_snapshot(transaction_limit=5)
    assert snap["balance"]["ok"] is True
    assert "transactions" in snap
    assert "note" in snap
