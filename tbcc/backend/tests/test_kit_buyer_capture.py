"""Kit buyer email capture."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.kit_buyer_capture import (
    capture_buyer_email_on_purchase,
    normalize_buyer_email,
)


def test_normalize_buyer_email() -> None:
    assert normalize_buyer_email(" Buyer@Example.COM ") == "buyer@example.com"
    assert normalize_buyer_email("not-an-email") is None


@patch("app.services.kit_buyer_capture.httpx.post")
def test_capture_skips_when_disabled(mock_post: MagicMock, monkeypatch) -> None:
    monkeypatch.setenv("TBCC_KIT_CAPTURE_ENABLED", "0")
    out = capture_buyer_email_on_purchase("buyer@example.com", telegram_user_id=1)
    assert out["skipped"] == "disabled"
    mock_post.assert_not_called()


@patch("app.services.kit_buyer_capture.httpx.post")
def test_capture_posts_when_enabled(mock_post: MagicMock, monkeypatch) -> None:
    monkeypatch.setenv("TBCC_KIT_CAPTURE_ENABLED", "1")
    monkeypatch.setenv("TBCC_KIT_API_SECRET", "test-secret")
    mock_post.return_value = MagicMock(status_code=201, text="{}")
    out = capture_buyer_email_on_purchase(
        "buyer@example.com",
        telegram_user_id=123,
        plan_name="AOF VIP — 1 Month",
        payment_method="gumroad",
    )
    assert out["ok"] is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["email_address"] == "buyer@example.com"
