"""Local devops LLM index (app/services/llm_model_index.py): failure
classification, refresh, exhaustion tracking, ranking, sticky cursor.
No real network — httpx.get and resolve_text_llm_runtime are monkeypatched,
and every test points TBCC_LLM_INDEX_DB at a throwaway tmp_path file."""

from __future__ import annotations

import pytest

from app.services import llm_model_index as idx
from app.services.llm_completions import TextLlmRuntime


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_LLM_INDEX_DB", str(tmp_path / "llm_index_test.sqlite3"))


def test_classify_failure_404_is_model_not_found():
    assert idx.classify_failure(RuntimeError("LLM error 404: model not found")) == "model_not_found"


def test_classify_failure_429_is_quota():
    assert idx.classify_failure(RuntimeError("LLM error 429: rate limited")) == "quota"


def test_classify_failure_quota_string_hint():
    assert idx.classify_failure(RuntimeError("LLM error 400: insufficient_quota for this key")) == "quota"


def test_classify_failure_auth_errors_are_transient():
    assert idx.classify_failure(RuntimeError("LLM error 401: invalid api key")) == "transient"
    assert idx.classify_failure(RuntimeError("LLM error 403: forbidden")) == "transient"


def test_classify_failure_empty_content_is_transient():
    assert idx.classify_failure(RuntimeError("LLM returned empty content")) == "transient"


def test_record_failure_quota_marks_provider_exhausted():
    kind = idx.record_failure("groq", "openai/gpt-oss-120b", RuntimeError("LLM error 429: rate limited"))
    assert kind == "quota"
    assert idx.is_exhausted("groq") is True
    assert idx.is_exhausted("mistral") is False


def test_record_failure_model_not_found_marks_only_that_model(monkeypatch):
    monkeypatch.setattr(idx, "resolve_text_llm_runtime", lambda provider: TextLlmRuntime(
        provider="deepinfra", api_key="k", model="x", base_url="https://api.deepinfra.com/v1/openai",
    ))
    monkeypatch.setattr(idx, "chat_completions_headers", lambda rt: {})
    fake_response = _FakeResponse(200, {"data": [{"id": "cognitivecomputations/dolphin-2.9-llama3-8b"}]})
    monkeypatch.setattr(idx.httpx, "get", lambda *a, **k: fake_response)
    idx.refresh_provider_models("deepinfra")

    kind = idx.record_failure(
        "deepinfra", "cognitivecomputations/dolphin-2.9-llama3-8b", RuntimeError("LLM error 404: no such model")
    )
    assert kind == "model_not_found"
    assert idx.is_exhausted("deepinfra") is False
    status = idx.provider_status("deepinfra")
    assert status["model_count"] == 0  # the only model got marked stale


class _FakeResponse:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_refresh_provider_models_unconfigured(monkeypatch):
    def _raise(provider):
        raise RuntimeError(f"Set TBCC_{provider.upper()}_API_KEY")

    monkeypatch.setattr(idx, "resolve_text_llm_runtime", _raise)
    result = idx.refresh_provider_models("mistral")
    assert result["configured"] is False
    assert result["ok"] is False
    status = idx.provider_status("mistral")
    assert status["configured"] == 0


def test_refresh_provider_models_success_inserts_models(monkeypatch):
    monkeypatch.setattr(idx, "resolve_text_llm_runtime", lambda provider: TextLlmRuntime(
        provider="openrouter", api_key="k", model="x", base_url="https://openrouter.ai/api/v1",
    ))
    monkeypatch.setattr(idx, "chat_completions_headers", lambda rt: {})
    payload = {"data": [{"id": "model-a"}, {"id": "model-b"}]}
    monkeypatch.setattr(idx.httpx, "get", lambda *a, **k: _FakeResponse(200, payload))

    result = idx.refresh_provider_models("openrouter")
    assert result["ok"] is True
    assert result["model_count"] == 2
    status = idx.provider_status("openrouter")
    assert status["models_endpoint_ok"] == 1
    assert status["model_count"] == 2


def test_refresh_provider_models_http_failure_isolated(monkeypatch):
    monkeypatch.setattr(idx, "resolve_text_llm_runtime", lambda provider: TextLlmRuntime(
        provider="venice", api_key="k", model="x", base_url="https://api.venice.ai/api/v1",
    ))
    monkeypatch.setattr(idx, "chat_completions_headers", lambda rt: {})

    def _boom(*a, **k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(idx.httpx, "get", _boom)
    result = idx.refresh_provider_models("venice")
    assert result["ok"] is False
    assert "connection reset" in result["error"]
    status = idx.provider_status("venice")
    assert status["models_endpoint_ok"] == 0


def _stub_resolvable(monkeypatch, unresolvable: set[str] = frozenset()):
    """rank_providers_for_cycle checks live resolvability via try_resolve_provider,
    not the (possibly stale) `configured` column — stub it deterministically so
    these tests don't depend on real API keys in the test environment."""
    def _fake(pid: str):
        return None if pid in unresolvable else TextLlmRuntime(provider=pid, api_key="k", model="x")

    monkeypatch.setattr(idx, "try_resolve_provider", _fake)


def test_rank_providers_skips_exhausted_and_unresolvable(monkeypatch):
    _stub_resolvable(monkeypatch, unresolvable={"mistral"})
    idx.record_failure("groq", None, RuntimeError("LLM error 429: rate limited"))

    ranked = idx.rank_providers_for_cycle()
    providers = [r["provider"] for r in ranked]
    assert "groq" not in providers
    assert "mistral" not in providers
    assert "zlm" in providers


def test_rank_providers_numeric_usage_sorts_first(monkeypatch):
    _stub_resolvable(monkeypatch)
    with idx.closing(idx._connect()) as conn:
        idx._upsert_provider_state(conn, "openrouter", usage_remaining=5.0)
        idx._upsert_provider_state(conn, "custom", usage_remaining=50.0)
        conn.commit()

    ranked = idx.rank_providers_for_cycle()
    assert ranked[0]["provider"] == "custom"
    assert ranked[1]["provider"] == "openrouter"


def test_rank_providers_zero_usage_remaining_treated_as_exhausted(monkeypatch):
    _stub_resolvable(monkeypatch)
    with idx.closing(idx._connect()) as conn:
        idx._upsert_provider_state(conn, "openrouter", usage_remaining=0.0)
        conn.commit()

    ranked = idx.rank_providers_for_cycle()
    providers = [r["provider"] for r in ranked]
    assert "openrouter" not in providers
    assert "zlm" in providers  # unknown-tier providers still rank fine


def test_quota_reset_window_short_for_bare_rate_limit():
    assert idx._quota_reset_window(RuntimeError("LLM error 429: rate_limit_exceeded")) == idx.timedelta(minutes=5)


def test_quota_reset_window_long_for_credit_exhaustion():
    exc = RuntimeError("LLM error 402: insufficient_quota, please add credits")
    assert idx._quota_reset_window(exc) == idx.timedelta(hours=24)


def test_clear_exhaustion_removes_the_block():
    idx.record_failure("groq", None, RuntimeError("LLM error 429: rate limited"))
    assert idx.is_exhausted("groq") is True
    idx.clear_exhaustion("groq")
    assert idx.is_exhausted("groq") is False


def test_extract_context_length_variants():
    assert idx._extract_context_length({"context_length": 131072}) == 131072
    assert idx._extract_context_length({"context_window": 4096}) == 4096
    assert idx._extract_context_length({"metadata": {"context_length": 8192}}) == 8192
    assert idx._extract_context_length({"metadata": {"context_length": None}}) is None
    assert idx._extract_context_length({}) is None


def test_list_models_joins_provider_state(monkeypatch):
    monkeypatch.setattr(idx, "resolve_text_llm_runtime", lambda provider: TextLlmRuntime(
        provider="openrouter", api_key="k", model="x", base_url="https://openrouter.ai/api/v1",
    ))
    monkeypatch.setattr(idx, "chat_completions_headers", lambda rt: {})
    payload = {"data": [{"id": "some/model", "context_length": 32000, "owned_by": "some-org"}]}
    monkeypatch.setattr(idx.httpx, "get", lambda *a, **k: _FakeResponse(200, payload))
    idx.refresh_provider_models("openrouter")

    with idx.closing(idx._connect()) as conn:
        idx._upsert_provider_state(conn, "openrouter", usage_remaining=12.5, usage_limit=100.0)
        conn.commit()

    rows = idx.list_models()
    assert len(rows) == 1
    row = rows[0]
    assert row["provider"] == "openrouter"
    assert row["model_id"] == "some/model"
    assert row["context_length"] == 32000
    assert row["owned_by"] == "some-org"
    assert row["usage_remaining"] == 12.5
    assert row["stale"] is False
    assert row["exhausted"] is False


def test_sticky_roundtrip_and_advance(monkeypatch):
    _stub_resolvable(monkeypatch)
    assert idx.get_sticky() is None
    idx.set_sticky("zlm", "glm-4.5")
    got = idx.get_sticky()
    assert got["provider"] == "zlm"
    assert got["model_id"] == "glm-4.5"

    nxt = idx.advance_to_next()
    assert nxt is not None
    assert nxt["provider"] != "zlm"
    assert idx.get_sticky()["provider"] == nxt["provider"]
