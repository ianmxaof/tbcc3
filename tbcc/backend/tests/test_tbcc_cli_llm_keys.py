"""scripts/tbcc_cli.py: `llm keys add/list/remove` and `llm models`. Exercises
the real llm_model_index storage (isolated SQLite per test) — only getpass and
stdout are mocked/captured, so this also proves the key never gets printed."""

from __future__ import annotations

from argparse import Namespace

import pytest

from app.services import llm_model_index as idx
from scripts.tbcc_cli import (
    cmd_llm_keys_add,
    cmd_llm_keys_list,
    cmd_llm_keys_remove,
    cmd_llm_models,
    cmd_llm_sticky_set,
)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_LLM_INDEX_DB", str(tmp_path / "cli_keys_test.sqlite3"))


def test_keys_add_builtin_prompts_hidden_and_stores(monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "secret-key-value")
    rc = cmd_llm_keys_add(Namespace(provider="groq", base_url=""))
    assert rc == 0
    out = capsys.readouterr().out
    assert "secret-key-value" not in out
    assert "stored" in out
    assert idx._get_credential("groq")["api_key"] == "secret-key-value"


def test_keys_add_unknown_provider_requires_base_url(monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "whatever")
    rc = cmd_llm_keys_add(Namespace(provider="huggingface", base_url=""))
    assert rc == 1
    assert "--base-url" in capsys.readouterr().err
    assert idx._get_credential("huggingface") is None


def test_keys_add_custom_provider_with_base_url_registers_it(monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "hf_secret")
    rc = cmd_llm_keys_add(
        Namespace(provider="huggingface", base_url="https://api-inference.huggingface.co/v1")
    )
    assert rc == 0
    assert "registered" in capsys.readouterr().out
    cred = idx._get_credential("huggingface")
    assert cred["api_key"] == "hf_secret"
    assert cred["base_url"] == "https://api-inference.huggingface.co/v1"
    assert "huggingface" in idx.all_provider_ids()


def test_keys_add_empty_key_aborts(monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "   ")
    rc = cmd_llm_keys_add(Namespace(provider="groq", base_url=""))
    assert rc == 1
    assert "No key entered" in capsys.readouterr().err
    assert idx._get_credential("groq") is None


def test_keys_list_never_prints_key_value(monkeypatch, capsys):
    idx.set_credential("groq", "super-secret-value")
    monkeypatch.setattr(
        idx, "resolve_text_llm_runtime",
        lambda provider, model=None: (_ for _ in ()).throw(RuntimeError("no env key")),
    )
    rc = cmd_llm_keys_list(Namespace(json=False))
    assert rc == 0
    out = capsys.readouterr().out
    assert "super-secret-value" not in out
    assert "groq" in out
    assert "stored" in out


def test_keys_remove_reports_success_and_absence(capsys):
    idx.set_credential("groq", "k")
    rc = cmd_llm_keys_remove(Namespace(provider="groq"))
    assert rc == 0
    assert "removed" in capsys.readouterr().out

    rc = cmd_llm_keys_remove(Namespace(provider="groq"))
    assert rc == 1
    assert "no stored key" in capsys.readouterr().err


def test_models_lists_cached_catalog(capsys):
    now = idx._now_iso()
    with idx.closing(idx._connect()) as conn:
        conn.execute(
            "INSERT INTO models (provider, model_id, raw_json, stale, fetched_at) VALUES (?, ?, ?, 0, ?)",
            ("openrouter", "free/thing:free", '{"pricing": {"prompt": "0", "completion": "0"}}', now),
        )
        conn.commit()
    rc = cmd_llm_models(Namespace(provider=None, json=False))
    assert rc == 0
    out = capsys.readouterr().out
    assert "free/thing:free" in out
    assert "free" in out


def test_sticky_set_pins_provider_and_model(capsys):
    idx.set_credential("moonshot", "sk-test", base_url="https://api.moonshot.ai/v1")
    rc = cmd_llm_sticky_set(Namespace(provider="moonshot", model="kimi-k2.7-code", json=False))
    assert rc == 0
    sticky = idx.get_sticky()
    assert sticky["provider"] == "moonshot"
    assert sticky["model_id"] == "kimi-k2.7-code"
    assert "moonshot/kimi-k2.7-code" in capsys.readouterr().out


def test_sticky_set_unknown_provider_fails(capsys):
    rc = cmd_llm_sticky_set(Namespace(provider="not-real", model="", json=False))
    assert rc == 1
    assert "not configured" in capsys.readouterr().err
