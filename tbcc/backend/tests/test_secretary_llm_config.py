"""Tests for secretary LLM config + live verification helper."""

from unittest.mock import patch

from app.services.llm_completions import TextLlmRuntime
from app.services.secretary_llm_config import (
    normalize_llm_base_url,
    probe_llm_credentials,
    probe_secretary_llm,
)


def test_normalize_llm_base_url_strips_completions_suffix():
    assert (
        normalize_llm_base_url("https://api.example.com/v1/chat/completions")
        == "https://api.example.com/v1"
    )


def test_test_secretary_llm_success():
    runtime = TextLlmRuntime(
        provider="openai",
        api_key="sk-test-key-12345678",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
    )
    fake = {"choices": [{"message": {"content": "TBCC_OK"}}]}
    with patch("app.services.secretary_llm_config.post_chat_completions_sync", return_value=fake):
        out = probe_secretary_llm(runtime=runtime)
    assert out["ok"] is True
    assert out["reply_preview"] == "TBCC_OK"
    assert out["endpoint"] == "https://api.openai.com/v1/chat/completions"


def test_probe_secretary_llm_http_error():
    runtime = TextLlmRuntime(
        provider="openai",
        api_key="sk-test-key-12345678",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
    )

    def _boom(*_a, **_k):
        raise RuntimeError("LLM error 401: invalid_api_key")

    with patch("app.services.secretary_llm_config.post_chat_completions_sync", side_effect=_boom):
        out = probe_secretary_llm(runtime=runtime)
    assert out["ok"] is False
    assert out["stage"] == "http"
    assert "401" in out["message"]


def test_probe_llm_credentials_validation():
    out = probe_llm_credentials(api_key="short", provider="openai")
    assert out["ok"] is False
    assert out["stage"] == "validation"


def test_env_llm_preset_catalog_has_hcnsec_and_openrouter():
    from app.services.secretary_llm_config import env_llm_preset_catalog

    ids = {p["id"] for p in env_llm_preset_catalog()}
    assert ids == {"hcnsec", "openrouter", "openai", "cometapi"}


def test_apply_hcnsec_env_preset(monkeypatch):
    from app.services.secretary_llm_config import apply_hcnsec_env_preset, secretary_llm_status

    monkeypatch.setenv("TBCC_LLM_API_KEY", "sk-hcnsec-test-key-1234567890")
    monkeypatch.setenv("TBCC_LLM_BASE_URL", "https://api.hcnsec.cn/v1")
    monkeypatch.setenv("TBCC_LLM_MODEL", "step-3.5-flash")
    out = apply_hcnsec_env_preset()
    assert out["ok"] is True
    assert out["preset"] == "hcnsec"
    assert out["base_url"] == "https://api.hcnsec.cn/v1"
    assert out["model"] == "step-3.5-flash"
    st = secretary_llm_status()
    assert "hcnsec.cn" in str(st.get("base_url") or "")
    assert st["api_key_override"] is False


def test_apply_openrouter_preset_clears_dashboard_key(monkeypatch):
    from app.database.session import SessionLocal
    from app.services.secretary_llm_config import apply_openrouter_preset, secretary_llm_status
    from app.services.secretary_settings_effective import ensure_settings_row

    monkeypatch.setenv("TBCC_OPENROUTER_API_KEY", "sk-or-v1-test-key-1234567890")
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_api_key = "sk-bad-dashboard-key-12345678"
        db.commit()
    finally:
        db.close()

    out = apply_openrouter_preset()
    assert out["ok"] is True
    assert out["model"] == "openai/gpt-4o-mini"
    st = secretary_llm_status()
    assert st["api_key_override"] is False
    assert st["provider"] == "openrouter"
