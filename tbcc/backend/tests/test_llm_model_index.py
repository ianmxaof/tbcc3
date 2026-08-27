"""Local devops LLM index (app/services/llm_model_index.py): failure
classification, refresh, exhaustion tracking, ranking, sticky cursor.
No real network — httpx.get and resolve_text_llm_runtime are monkeypatched,
and every test points TBCC_LLM_INDEX_DB at a throwaway tmp_path file."""

from __future__ import annotations

import json

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
    monkeypatch.setattr(idx, "resolve_text_llm_runtime", lambda provider, model=None: TextLlmRuntime(
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
    def _raise(provider, model=None):
        raise RuntimeError(f"Set TBCC_{provider.upper()}_API_KEY")

    monkeypatch.setattr(idx, "resolve_text_llm_runtime", _raise)
    result = idx.refresh_provider_models("mistral")
    assert result["configured"] is False
    assert result["ok"] is False
    status = idx.provider_status("mistral")
    assert status["configured"] == 0
    assert status["key_source"] == "none"


def test_refresh_provider_models_success_inserts_models(monkeypatch):
    monkeypatch.setattr(idx, "resolve_text_llm_runtime", lambda provider, model=None: TextLlmRuntime(
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
    monkeypatch.setattr(idx, "resolve_text_llm_runtime", lambda provider, model=None: TextLlmRuntime(
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
    """rank_providers_for_cycle checks live resolvability via
    resolve_runtime_for_rotator -> (no stored credential in these tests) ->
    resolve_text_llm_runtime for builtins. Stub that env-based layer
    deterministically so these tests don't depend on real API keys in the
    test environment."""
    def _fake(provider, model=None):
        if provider in unresolvable:
            raise RuntimeError(f"Set TBCC_{provider.upper()}_API_KEY")
        return TextLlmRuntime(provider=provider, api_key="k", model=model or "x")

    monkeypatch.setattr(idx, "resolve_text_llm_runtime", _fake)


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
    monkeypatch.setattr(idx, "resolve_text_llm_runtime", lambda provider, model=None: TextLlmRuntime(
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


# --- credentials / custom providers -----------------------------------------


def test_credentials_never_expose_the_key_value():
    idx.set_credential("groq", "gsk-super-secret")
    rows = idx.list_credentials()
    assert rows == [{"provider": "groq", "base_url": None, "added_at": rows[0]["added_at"]}]
    assert "gsk-super-secret" not in str(rows)


def test_stored_key_wins_over_env_for_a_builtin(monkeypatch):
    calls = []

    def _fake(provider, model=None, api_key=None):
        calls.append(api_key)
        return TextLlmRuntime(provider=provider, api_key=api_key or "env-key", model="x")

    monkeypatch.setattr(idx, "resolve_text_llm_runtime", _fake)
    idx.set_credential("groq", "stored-key")

    rt = idx.resolve_runtime_for_rotator("groq")
    assert rt.api_key == "stored-key"
    assert calls == ["stored-key"]


def test_falls_back_to_env_when_no_stored_key(monkeypatch):
    monkeypatch.setattr(
        idx, "resolve_text_llm_runtime",
        lambda provider, model=None: TextLlmRuntime(provider=provider, api_key="env-key", model="x"),
    )
    rt = idx.resolve_runtime_for_rotator("groq")
    assert rt.api_key == "env-key"


def test_custom_provider_registration_and_resolution():
    idx.set_credential("huggingface", "hf_secret", base_url="https://api-inference.huggingface.co/v1")
    assert "huggingface" in idx.custom_provider_ids()
    assert "huggingface" in idx.all_provider_ids()
    assert idx.is_builtin_provider("huggingface") is False

    rt = idx.resolve_runtime_for_rotator("huggingface", model="meta-llama/Llama-3-8b")
    assert rt.provider == "huggingface"
    assert rt.api_key == "hf_secret"
    assert rt.base_url == "https://api-inference.huggingface.co/v1"
    assert rt.model == "meta-llama/Llama-3-8b"


def test_unregistered_unknown_provider_does_not_resolve():
    assert idx.resolve_runtime_for_rotator("totally-made-up") is None


def test_remove_credential_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(
        idx, "resolve_text_llm_runtime",
        lambda provider, model=None, api_key=None: TextLlmRuntime(
            provider=provider, api_key=api_key or "env-key", model="x"
        ),
    )
    idx.set_credential("groq", "stored-key")
    assert idx.resolve_runtime_for_rotator("groq").api_key == "stored-key"

    assert idx.remove_credential("groq") is True
    assert idx.remove_credential("groq") is False  # already gone
    assert idx.resolve_runtime_for_rotator("groq").api_key == "env-key"


def test_key_source_reports_stored_env_or_none(monkeypatch):
    monkeypatch.setattr(idx, "resolve_text_llm_runtime", lambda provider, model=None: (_ for _ in ()).throw(
        RuntimeError("no key")
    ))
    assert idx.key_source("groq") == "none"
    idx.set_credential("groq", "k")
    assert idx.key_source("groq") == "stored"


# --- pricing / modality / model picking --------------------------------------


def test_extract_modality_openrouter_architecture():
    raw = {"architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}}
    assert idx._extract_modality(raw) == "text+image->text"


def test_extract_modality_deepinfra_tags():
    assert idx._extract_modality({"metadata": {"tags": ["tts"]}}) == "tts"


def test_extract_modality_defaults_to_text():
    assert idx._extract_modality({}) == "text"


def test_extract_pricing_standard_per_token_keys():
    raw = {"pricing": {"prompt": "0.0000008", "completion": "0.0000016"}}
    price = idx._extract_pricing(raw)
    assert price == pytest.approx((0.8, 1.6))


def test_extract_pricing_ignores_non_token_shapes():
    # DeepInfra TTS pricing: input_characters, not prompt/completion — must not
    # be misread as per-token pricing.
    assert idx._extract_pricing({"pricing": {"input_characters": 5.0}}) is None
    assert idx._extract_pricing({}) is None


def test_extract_is_free_openrouter_free_suffix():
    assert idx._extract_is_free("meta-llama/llama-3:free", None) is True


def test_extract_is_free_zero_priced():
    assert idx._extract_is_free("some/model", (0.0, 0.0)) is True
    assert idx._extract_is_free("some/model", (1.0, 2.0)) is False


def _seed_models(provider: str, models: list[dict]):
    now = idx._now_iso()
    with idx.closing(idx._connect()) as conn:
        for m in models:
            conn.execute(
                "INSERT INTO models (provider, model_id, raw_json, stale, fetched_at) VALUES (?, ?, ?, 0, ?)",
                (provider, m["id"], json.dumps(m), now),
            )
        conn.commit()


def test_pick_best_model_prefers_free_then_cheapest():
    _seed_models("openrouter", [
        {"id": "paid/expensive", "pricing": {"prompt": "0.00001", "completion": "0.00002"}},
        {"id": "paid/cheap", "pricing": {"prompt": "0.0000001", "completion": "0.0000002"}},
        {"id": "free/model:free", "pricing": {"prompt": "0", "completion": "0"}},
    ])
    assert idx.pick_best_model_for_provider("openrouter") == "free/model:free"


def test_pick_best_model_excludes_prompt_guard_and_whisper_even_when_cheapest():
    """Real bug hit in practice: Groq's catalog has meta-llama/llama-prompt-
    guard-2-22m (a prompt-injection classifier that returns a bare
    probability score, not a chat reply) priced at $0.03/M — cheaper than
    every actual chat model in the same catalog. "hi" got answered with
    "0.0014354782178997993". Name-pattern exclusion is the fix since these
    catalogs don't expose a real task/capability field."""
    _seed_models("groq", [
        {"id": "meta-llama/llama-prompt-guard-2-22m", "pricing": {"prompt": "0.00000003", "completion": "0.00000003"}},
        {"id": "whisper-large-v3", "pricing": {"prompt": "0.00000001", "completion": "0.00000001"}},
        {"id": "openai/gpt-oss-20b", "pricing": {"prompt": "0.000000075", "completion": "0.000000075"}},
    ])
    assert idx.pick_best_model_for_provider("groq") == "openai/gpt-oss-20b"


def test_pick_best_model_cheapest_when_none_free():
    _seed_models("openrouter", [
        {"id": "paid/expensive", "pricing": {"prompt": "0.00001", "completion": "0.00002"}},
        {"id": "paid/cheap", "pricing": {"prompt": "0.0000001", "completion": "0.0000002"}},
    ])
    assert idx.pick_best_model_for_provider("openrouter") == "paid/cheap"


def test_pick_best_model_returns_none_without_pricing_data():
    _seed_models("mistral", [{"id": "mistral-small"}, {"id": "codestral"}])
    assert idx.pick_best_model_for_provider("mistral") is None


def test_pick_best_model_prefer_uncensored_biases_selection():
    _seed_models("deepinfra", [
        {"id": "org/plain-model", "metadata": {"pricing": {"input_characters": 1}}},
        {"id": "NousResearch/Hermes-3-Llama", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
        {"id": "some/other-cheap", "pricing": {"prompt": "0.0000001", "completion": "0.0000002"}},
    ])
    # without the flag, the plain cheap model wins on price
    assert idx.pick_best_model_for_provider("deepinfra") == "some/other-cheap"
    # with it, the uncensored-flavored model wins even though it's pricier
    assert idx.pick_best_model_for_provider("deepinfra", prefer_uncensored=True) == "NousResearch/Hermes-3-Llama"


# --- ask_with_rotation (2026-08-25: operator hit both real failure shapes) --


def test_ask_with_rotation_retries_once_on_model_not_found_with_a_different_model(monkeypatch):
    """record_failure() already marked the 404'd model stale; ask_with_rotation
    should re-resolve the same provider (picker now skips it) and retry once,
    rather than failing outright on a model the caller never explicitly asked for."""
    pick_calls = {"n": 0}

    def _pick(pid, *, prefer_uncensored=False):
        pick_calls["n"] += 1
        return "dolphin-old" if pick_calls["n"] == 1 else "fresh-model"

    def _resolve(provider, model=None):
        return TextLlmRuntime(provider=provider, api_key="k", model=model)

    complete_calls: list[str] = []

    def _complete(messages, *, model, max_tokens, temperature, timeout, runtime):
        complete_calls.append(runtime.model)
        if runtime.model == "dolphin-old":
            raise RuntimeError("LLM error 404: model not found")
        return "ok reply"

    monkeypatch.setattr("app.services.llm_model_index.pick_best_model_for_provider", _pick)
    monkeypatch.setattr("app.services.llm_model_index.resolve_text_llm_runtime", _resolve)
    monkeypatch.setattr("app.services.llm_completions.complete_chat_text_sync", _complete)
    monkeypatch.setattr("app.services.llm_model_index.get_sticky", lambda: {"provider": "deepinfra"})
    monkeypatch.setattr("app.services.llm_model_index.set_sticky", lambda p, m: None)

    result = idx.ask_with_rotation("hello")
    assert result["ok"] is True
    assert result["reply"] == "ok reply"
    assert complete_calls == ["dolphin-old", "fresh-model"]
    assert any("model not found" in n for n in result["notices"])


def test_ask_with_rotation_does_not_repick_model_when_caller_pinned_one(monkeypatch):
    """--model was explicit — a 404 there is a real error to surface, not
    something to silently paper over with a different model."""
    rt = TextLlmRuntime(provider="deepinfra", api_key="k", model="pinned-model")
    monkeypatch.setattr("app.services.llm_model_index.resolve_text_llm_runtime", lambda provider, model=None: rt)
    monkeypatch.setattr("app.services.llm_model_index.get_sticky", lambda: {"provider": "deepinfra"})
    monkeypatch.setattr(
        "app.services.llm_completions.complete_chat_text_sync",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM error 404: model not found")),
    )

    result = idx.ask_with_rotation("hello", model="pinned-model")
    assert result["ok"] is False
    assert "model_not_found" in result["error"]


def test_ask_with_rotation_cycles_provider_when_repick_yields_no_better_model(monkeypatch):
    """Real bug hit in practice: a provider's cached catalog can be 100+ rows
    with none usable (no pricing/free data) — pick_best_model_for_provider
    returns None, the runtime layer falls back to a hardcoded per-provider
    default model, and that default can itself be the same dead model that
    404'd. Re-picking on the same provider then just returns the identical
    model again. Confirms this now cycles to a different provider instead of
    surfacing the original stale-model error forever."""
    pick_calls = {"n": 0}

    def _pick(pid, *, prefer_uncensored=False):
        pick_calls["n"] += 1
        return None  # simulates an exhausted/unusable local catalog

    def _resolve(provider, model=None):
        # deepinfra always resolves to the same hardcoded-default model
        # (model=None -> the runtime layer's own dead default), groq gets a
        # real model once cycled to.
        if provider == "deepinfra":
            return TextLlmRuntime(provider="deepinfra", api_key="k1", model="dead-hardcoded-default")
        return TextLlmRuntime(provider="groq", api_key="k2", model="a-real-model")

    complete_calls: list[str] = []

    def _complete(messages, *, model, max_tokens, temperature, timeout, runtime):
        complete_calls.append(runtime.provider)
        if runtime.provider == "deepinfra":
            raise RuntimeError("LLM error 404: model not found")
        return "ok reply"

    monkeypatch.setattr("app.services.llm_model_index.pick_best_model_for_provider", _pick)
    monkeypatch.setattr("app.services.llm_model_index.resolve_text_llm_runtime", _resolve)
    monkeypatch.setattr("app.services.llm_completions.complete_chat_text_sync", _complete)
    monkeypatch.setattr("app.services.llm_model_index.get_sticky", lambda: {"provider": "deepinfra"})
    monkeypatch.setattr("app.services.llm_model_index.advance_to_next", lambda: {"provider": "groq"})
    monkeypatch.setattr("app.services.llm_model_index.set_sticky", lambda p, m: None)

    result = idx.ask_with_rotation("hello")
    assert result["ok"] is True
    assert result["provider"] == "groq"
    assert complete_calls == ["deepinfra", "groq"]
    assert any("cycling to next provider" in n for n in result["notices"])


def test_ask_with_rotation_retries_with_provider_stated_max_tokens_cap(monkeypatch):
    """Real bug: a model whose output cap is below the 600-token default (hit
    on a Cerebras model) gets classified 'transient' by classify_failure()
    and — correctly, for genuine transient errors — never auto-retried. This
    path specifically parses the provider's stated cap out of the error and
    retries once with it, instead of failing the same way forever."""
    rt = TextLlmRuntime(provider="cerebras", api_key="k", model="some-model")
    monkeypatch.setattr("app.services.llm_model_index.resolve_text_llm_runtime", lambda provider, model=None: rt)
    monkeypatch.setattr("app.services.llm_model_index.get_sticky", lambda: {"provider": "cerebras"})
    monkeypatch.setattr("app.services.llm_model_index.set_sticky", lambda p, m: None)

    calls: list[int] = []

    def _complete(messages, *, model, max_tokens, temperature, timeout, runtime):
        calls.append(max_tokens)
        if max_tokens > 512:
            raise RuntimeError(
                'LLM error 400: {"error":{"message":"`max_tokens` must be less than or equal to `512`, '
                'the maximum value for `max_tokens` is less than the `context_window` for this model",'
                '"type":"invalid_request_error","param":"max_tokens"}}'
            )
        return "ok reply"

    monkeypatch.setattr("app.services.llm_completions.complete_chat_text_sync", _complete)

    result = idx.ask_with_rotation("hello", max_tokens=600)
    assert result["ok"] is True
    assert calls == [600, 512]
    assert any("max_tokens capped at 512" in n for n in result["notices"])
