"""OpenRouter request-level plugins (response-healing) for the vision classify call.
Plugins are OpenRouter-specific — must never be sent on the plain OpenAI call path."""

from __future__ import annotations

import pytest

from app.services.vision_llm import _openrouter_vision_plugins


def test_default_plugins_is_response_healing_only(monkeypatch):
    monkeypatch.delenv("TBCC_OPENROUTER_VISION_PLUGINS", raising=False)
    assert _openrouter_vision_plugins() == [{"id": "response-healing"}]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("response-healing", [{"id": "response-healing"}]),
        ("response-healing,context-compression", [{"id": "response-healing"}, {"id": "context-compression"}]),
        # Empty string falls back to the default, same "or default" convention
        # used everywhere else in this codebase — not a way to disable all plugins.
        ("", [{"id": "response-healing"}]),
        (" response-healing , context-compression ", [{"id": "response-healing"}, {"id": "context-compression"}]),
    ],
)
def test_plugins_parsed_from_env(monkeypatch, raw, expected):
    monkeypatch.setenv("TBCC_OPENROUTER_VISION_PLUGINS", raw)
    assert _openrouter_vision_plugins() == expected


def test_openai_call_never_receives_plugins_field(monkeypatch):
    """_vision_openai_compatible is shared with the real OpenAI provider —
    plugins is an OpenRouter-only extension and must be omitted, not just empty,
    when the caller doesn't pass openrouter_plugins."""
    import httpx

    from app.services import vision_llm

    captured = {}

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    monkeypatch.setattr(vision_llm, "_vision_model", lambda: "gpt-4o")

    vision_llm._vision_openai_compatible(
        "https://api.openai.com/v1/chat/completions",
        "sk-test",
        "prompt",
        "data:image/jpeg;base64,x",
        timeout=5.0,
    )

    assert "plugins" not in captured["json"]


def test_openrouter_call_includes_plugins_field(monkeypatch):
    import httpx

    from app.services import vision_llm

    captured = {}

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    monkeypatch.setattr(vision_llm, "_vision_model", lambda: "qwen/qwen3-vl-235b-a22b-instruct")

    vision_llm._vision_openai_compatible(
        "https://openrouter.ai/api/v1/chat/completions",
        "sk-test",
        "prompt",
        "data:image/jpeg;base64,x",
        timeout=5.0,
        openrouter_plugins=[{"id": "response-healing"}],
    )

    assert captured["json"]["plugins"] == [{"id": "response-healing"}]
