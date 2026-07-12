from pathlib import Path

import pytest

from app.services import tbcc_env_secret_store as store


def test_suggest_env_key_cloudflare_account_id():
    key = store.suggest_env_key(value="a1b2c3d4e5f6789012345678abcdef01", page_url="https://dash.cloudflare.com/")
    assert key == "TBCC_R2_ACCOUNT_ID"


def test_suggest_env_key_account_id_without_url():
    # Desktop/notepad path — no browser URL. Must NOT map to ImgBB.
    assert store.suggest_env_key(value="a1b2c3d4e5f6789012345678abcdef01") == "TBCC_R2_ACCOUNT_ID"


def test_suggest_r2_public_and_s3_urls():
    assert (
        store.suggest_env_key(value="https://pub-abcdef0123456789abcdef0123456789.r2.dev")
        == "TBCC_R2_PUBLIC_BASE_URL"
    )
    assert (
        store.suggest_env_key(value="https://abc123.r2.cloudflarestorage.com")
        == "TBCC_R2_S3_ENDPOINT"
    )
    assert (
        store.suggest_env_key(value="https://abc123.r2.cloudflarestorage.com/aof-x-promo")
        == "TBCC_R2_S3_ENDPOINT"
    )


def test_normalize_s3_endpoint_strips_bucket_path():
    raw = "https://abc123.r2.cloudflarestorage.com/aof-x-promo"
    assert store.normalize_secret_value("TBCC_R2_S3_ENDPOINT", raw) == "https://abc123.r2.cloudflarestorage.com"
    assert store.looks_like_api_key(raw)


def test_normalize_env_key_aliases():
    assert store.normalize_env_key("TBCC GEMINI KEY") == "TBCC_GEMINI_API_KEY"
    assert store.normalize_env_key("tbcc-cloudflare-token") == "TBCC_CF_API_TOKEN"
    assert store.normalize_env_key("Account ID") == "TBCC_R2_ACCOUNT_ID"


def test_looks_like_api_key():
    assert store.looks_like_api_key("a" * 32)
    assert store.looks_like_api_key("tskey-auth-abcdefghijklmnopqrstuvwxyz")
    assert store.looks_like_api_key("sk-or-" + ("x" * 20))
    assert store.looks_like_api_key("https://pub-abcdef0123456789abcdef0123456789.r2.dev")
    assert store.looks_like_api_key("https://abc123.r2.cloudflarestorage.com")
    assert not store.looks_like_api_key("short")


def test_suggest_env_key_tailscale_and_openrouter():
    assert store.suggest_env_key(value="tskey-auth-abcdefghijklmnopqrstuvwxyz") == "TBCC_TAILSCALE_AUTHKEY"
    assert store.suggest_env_key(value="sk-or-" + ("x" * 24)) == "OPENROUTER_API_KEY"


def test_write_env_secret_roundtrip(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TBCC_FOO=old\n", encoding="utf-8")
    monkeypatch.setattr(store, "env_file_path", lambda: env_file)
    store.write_env_secret("TBCC_FOO", "newvalue")
    store.write_env_secret("TBCC_BAR", "baz")
    text = env_file.read_text(encoding="utf-8")
    assert "TBCC_FOO=newvalue" in text
    assert "TBCC_BAR=baz" in text
