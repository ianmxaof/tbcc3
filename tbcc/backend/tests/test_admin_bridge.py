"""Unit tests for dashboard ↔ forum admin bridge tokens."""

from __future__ import annotations

import time

import pytest

from app.services import admin_bridge


def test_mint_verify_roundtrip(monkeypatch):
    monkeypatch.setenv("TBCC_ADMIN_BRIDGE_SECRET", "unit-test-bridge-secret")
    token = admin_bridge.mint_bridge_token(audience="forum_admin", next_path="/admin")
    payload = admin_bridge.verify_bridge_token(token, expected_audience="forum_admin")
    assert payload["aud"] == "forum_admin"
    assert payload["next"] == "/admin"
    assert int(payload["exp"]) > int(time.time())


def test_wrong_audience_rejected(monkeypatch):
    monkeypatch.setenv("TBCC_ADMIN_BRIDGE_SECRET", "unit-test-bridge-secret")
    token = admin_bridge.mint_bridge_token(audience="forum_admin", next_path="/admin")
    with pytest.raises(ValueError, match="wrong_audience"):
        admin_bridge.verify_bridge_token(token, expected_audience="dashboard")


def test_tamper_rejected(monkeypatch):
    monkeypatch.setenv("TBCC_ADMIN_BRIDGE_SECRET", "unit-test-bridge-secret")
    token = admin_bridge.mint_bridge_token(audience="dashboard", next_path="/")
    body, sig = token.rsplit(".", 1)
    bad = f"{body}.{('0' if sig[0] != '0' else '1') + sig[1:]}"
    with pytest.raises(ValueError, match="bad_signature"):
        admin_bridge.verify_bridge_token(bad, expected_audience="dashboard")


def test_expired_rejected(monkeypatch):
    monkeypatch.setenv("TBCC_ADMIN_BRIDGE_SECRET", "unit-test-bridge-secret")
    token = admin_bridge.mint_bridge_token(audience="dashboard", next_path="/", ttl_seconds=30)
    # Force expiry by rewriting payload exp into the past via mint internals
    import base64
    import hashlib
    import hmac
    import json

    body, _ = token.rsplit(".", 1)
    pad = "=" * (-len(body) % 4)
    payload = json.loads(base64.urlsafe_b64decode(body + pad))
    payload["exp"] = int(time.time()) - 5
    new_body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    sig = hmac.new(b"unit-test-bridge-secret", new_body.encode(), hashlib.sha256).hexdigest()
    expired = f"{new_body}.{sig}"
    with pytest.raises(ValueError, match="expired"):
        admin_bridge.verify_bridge_token(expired, expected_audience="dashboard")


def test_build_urls(monkeypatch):
    monkeypatch.setenv("TBCC_ADMIN_BRIDGE_SECRET", "unit-test-bridge-secret")
    monkeypatch.setenv("TBCC_FORUM_PUBLIC_URL", "https://forum.example")
    monkeypatch.setenv("TBCC_DASHBOARD_PUBLIC_URL", "https://dash.example")
    forum_url = admin_bridge.build_forum_bridge_url(next_path="/admin")
    dash_url = admin_bridge.build_dashboard_bridge_url(next_path="/bots")
    assert forum_url.startswith("https://forum.example/auth/bridge?t=")
    assert dash_url.startswith("https://dash.example/?bridge=")
    assert "next=%2Fbots" in dash_url or "next=/bots" in dash_url
