"""Global internal API key middleware helpers."""

from __future__ import annotations

from app.middleware.internal_api_auth import api_require_internal_enabled, path_is_public


def test_path_is_public_health_and_webhooks() -> None:
    assert path_is_public("/health", "GET")
    assert path_is_public("/health/db", "GET")
    assert path_is_public("/webhooks/gumroad", "POST")
    assert path_is_public("/docs", "GET")
    assert path_is_public("/media/foo.jpg", "GET")
    assert path_is_public("/r/promoSlug", "GET")
    assert not path_is_public("/media/export", "GET")
    assert not path_is_public("/media/foo.jpg", "POST")
    assert not path_is_public("/import/zip-flywheel", "POST")
    assert not path_is_public("/channels", "GET")


def test_require_flag(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_API_REQUIRE_INTERNAL", "1")
    assert api_require_internal_enabled() is True
    monkeypatch.setenv("TBCC_API_REQUIRE_INTERNAL", "0")
    assert api_require_internal_enabled() is False
