"""scripts/tbcc_cli.py cmd_llm_ask: regression coverage for a real bug caught
by the advisor before ship — the original implementation drove the
chain-walking complete_chat_text_with_fallback() and, on failure, blamed
whatever `primary` happened to be even though any hop in the chain could have
raised. Fixed to call exactly one provider per attempt (complete_chat_text_sync
with an explicit runtime) so record_failure() always attributes the failure to
the provider that was actually tried. No real network — everything imported
inside cmd_llm_ask (function-local imports) is monkeypatched by dotted path."""

from __future__ import annotations

from argparse import Namespace

import pytest

from app.services.llm_completions import TextLlmRuntime
from scripts.tbcc_cli import cmd_llm_ask


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_LLM_INDEX_DB", str(tmp_path / "cli_ask_test.sqlite3"))


def _args(**overrides):
    base = dict(
        prompt="hi", system="", provider="", model="", max_tokens=100,
        temperature=0.7, timeout=10.0, json=False, prefer_uncensored=False,
    )
    base.update(overrides)
    return Namespace(**base)


def test_failure_is_attributed_to_the_provider_actually_tried(monkeypatch):
    rt = TextLlmRuntime(provider="deepinfra", api_key="k", model="dolphin")
    monkeypatch.setattr("app.services.llm_model_index.resolve_text_llm_runtime", lambda provider, model=None: rt)
    monkeypatch.setattr(
        "app.services.llm_completions.complete_chat_text_sync",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM error 429: rate limited")),
    )
    monkeypatch.setattr("app.services.llm_model_index.get_sticky", lambda: {"provider": "deepinfra"})
    monkeypatch.setattr("app.services.llm_model_index.advance_to_next", lambda: None)

    recorded = []
    monkeypatch.setattr(
        "app.services.llm_model_index.record_failure",
        lambda provider, model, exc: recorded.append((provider, model)) or "quota",
    )

    rc = cmd_llm_ask(_args())
    assert rc == 1
    assert recorded == [("deepinfra", "dolphin")]


def test_cycles_to_next_provider_on_quota_and_succeeds(monkeypatch):
    rt_a = TextLlmRuntime(provider="deepinfra", api_key="k1", model="dolphin")
    rt_b = TextLlmRuntime(provider="groq", api_key="k2", model="gpt-oss-120b")

    def _resolve(provider, model=None):
        return {"deepinfra": rt_a, "groq": rt_b}[provider]

    monkeypatch.setattr("app.services.llm_model_index.resolve_text_llm_runtime", _resolve)

    calls: list[str] = []

    def _complete(messages, *, model, max_tokens, temperature, timeout, runtime):
        calls.append(runtime.provider)
        if runtime.provider == "deepinfra":
            raise RuntimeError("LLM error 429: rate limited")
        return "ok reply"

    monkeypatch.setattr("app.services.llm_completions.complete_chat_text_sync", _complete)
    monkeypatch.setattr("app.services.llm_model_index.get_sticky", lambda: {"provider": "deepinfra"})
    monkeypatch.setattr("app.services.llm_model_index.record_failure", lambda p, m, e: "quota")
    monkeypatch.setattr("app.services.llm_model_index.advance_to_next", lambda: {"provider": "groq"})

    sticky_calls = []
    monkeypatch.setattr(
        "app.services.llm_model_index.set_sticky", lambda p, m: sticky_calls.append((p, m))
    )

    rc = cmd_llm_ask(_args())
    assert rc == 0
    assert calls == ["deepinfra", "groq"]
    assert sticky_calls == [("groq", "gpt-oss-120b")]


def test_falls_back_to_ranking_when_sticky_provider_unresolvable(monkeypatch, capsys):
    rt = TextLlmRuntime(provider="mistral", api_key="k", model="mistral-small")

    def _resolve(provider, model=None):
        if provider == "deepinfra":
            raise RuntimeError("Set TBCC_DEEPINFRA_API_KEY")
        return rt

    monkeypatch.setattr("app.services.llm_model_index.resolve_text_llm_runtime", _resolve)
    monkeypatch.setattr("app.services.llm_completions.complete_chat_text_sync", lambda *a, **k: "ok")
    monkeypatch.setattr("app.services.llm_model_index.get_sticky", lambda: {"provider": "deepinfra"})
    monkeypatch.setattr(
        "app.services.llm_model_index.rank_providers_for_cycle", lambda: [{"provider": "mistral"}]
    )
    monkeypatch.setattr("app.services.llm_model_index.set_sticky", lambda p, m: None)

    rc = cmd_llm_ask(_args())
    assert rc == 0
    assert "no longer configured" in capsys.readouterr().err


def test_no_provider_available_anywhere_errors_cleanly(monkeypatch, capsys):
    def _resolve(provider, model=None):
        raise RuntimeError("Set TBCC_API_KEY")

    monkeypatch.setattr("app.services.llm_model_index.resolve_text_llm_runtime", _resolve)
    monkeypatch.setattr("app.services.llm_model_index.get_sticky", lambda: None)
    monkeypatch.setattr("app.services.llm_model_index.rank_providers_for_cycle", lambda: [])

    rc = cmd_llm_ask(_args())
    assert rc == 1
    assert "No configured provider available" in capsys.readouterr().err
