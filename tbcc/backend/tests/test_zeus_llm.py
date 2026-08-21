"""Zeus v1 — LLM ask endpoint (agent/CLI-facing wrapper over the fallback chain).
No real network calls: every provider/fallback function is monkeypatched."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import zeus_llm


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(zeus_llm.router)
    return TestClient(app)


def test_ask_providers_lists_configured_and_unconfigured(monkeypatch):
    from app.services.llm_completions import TextLlmRuntime

    def fake_try_resolve(pid):
        if pid == "openrouter":
            return TextLlmRuntime(provider="openrouter", api_key="k", model="some-model")
        return None

    monkeypatch.setattr("app.services.llm_provider_fallback.try_resolve_provider", fake_try_resolve)
    r = _client().get("/zeus/v1/ask/providers")
    assert r.status_code == 200
    rows = {row["provider"]: row for row in r.json()["providers"]}
    assert rows["openrouter"]["configured"] is True
    assert rows["openrouter"]["model"] == "some-model"
    assert rows["mistral"]["configured"] is False


def test_ask_uses_fallback_chain_by_default(monkeypatch):
    calls = []

    async def fake_fallback(messages, *, primary, model, max_tokens, temperature):
        calls.append({"messages": messages, "primary": primary, "model": model})
        return "hello back"

    monkeypatch.setattr("app.services.llm_provider_fallback.complete_chat_text_with_fallback", fake_fallback)
    r = _client().post("/zeus/v1/ask", json={"prompt": "hi there"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "provider": "auto", "reply": "hello back"}
    assert calls[0]["primary"] is None
    assert calls[0]["messages"][-1] == {"role": "user", "content": "hi there"}


def test_ask_with_system_prompt_prepends_system_message(monkeypatch):
    seen = {}

    async def fake_fallback(messages, *, primary, model, max_tokens, temperature):
        seen["messages"] = messages
        return "ok"

    monkeypatch.setattr("app.services.llm_provider_fallback.complete_chat_text_with_fallback", fake_fallback)
    r = _client().post("/zeus/v1/ask", json={"prompt": "hi", "system": "be terse"})
    assert r.status_code == 200
    assert seen["messages"][0] == {"role": "system", "content": "be terse"}


def test_ask_unresolvable_provider_returns_400(monkeypatch):
    def fake_resolve(*, provider, model):
        raise RuntimeError(f"Set TBCC_{provider.upper()}_API_KEY")

    monkeypatch.setattr("app.services.llm_completions.resolve_text_llm_runtime", fake_resolve)
    r = _client().post("/zeus/v1/ask", json={"prompt": "hi", "provider": "mistral"})
    assert r.status_code == 400


def test_ask_all_providers_fail_returns_502(monkeypatch):
    async def fake_fallback(messages, *, primary, model, max_tokens, temperature):
        raise RuntimeError("all providers refused")

    monkeypatch.setattr("app.services.llm_provider_fallback.complete_chat_text_with_fallback", fake_fallback)
    r = _client().post("/zeus/v1/ask", json={"prompt": "hi"})
    assert r.status_code == 502


def test_ask_no_fallback_uses_single_provider_sync_path(monkeypatch):
    def fake_sync(messages, *, model, max_tokens, temperature, runtime):
        return "single-provider reply"

    monkeypatch.setattr("app.services.llm_completions.complete_chat_text_sync", fake_sync)
    r = _client().post("/zeus/v1/ask", json={"prompt": "hi", "no_fallback": True})
    assert r.status_code == 200
    assert r.json()["reply"] == "single-provider reply"


def test_zeus_llm_has_no_start_routes():
    """Read-only-except-ask facade: no process lifecycle verbs under /zeus/v1/ask*."""
    paths = {getattr(r, "path", "") for r in zeus_llm.router.routes}
    joined = " ".join(sorted(paths)).lower()
    for banned in ("/start", "/stop", "/restart"):
        assert banned not in joined
