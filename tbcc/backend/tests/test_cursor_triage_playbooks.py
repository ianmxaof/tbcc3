"""Cursor triage playbooks and auto-fix gating."""

from __future__ import annotations

import os

import pytest

from app.services.cursor_triage import (
    _build_agent_prompt,
    auto_fix_allowed_for_event,
)
from app.services.cursor_triage_playbooks import playbook_for_code


def test_playbook_session_sqlite_lock_mentions_admin_bot():
    text = playbook_for_code("session_sqlite_lock")
    assert "admin_bot.session" in text
    assert "telegram_relief" in text


def test_auto_fix_allowed_only_for_allowlisted_code(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TBCC_CURSOR_TRIAGE_AUTO_FIX", "1")
    monkeypatch.setenv("TBCC_CURSOR_TRIAGE_AUTO_FIX_ALLOWLIST", "session_sqlite_lock")
    ev = {"meta": {"code": "session_sqlite_lock"}}
    assert auto_fix_allowed_for_event(ev) is True
    ev2 = {"meta": {"code": "worker_crash"}}
    assert auto_fix_allowed_for_event(ev2) is False


def test_build_prompt_includes_playbook_and_pr_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TBCC_CURSOR_TRIAGE_AUTO_FIX", "1")
    monkeypatch.setenv("TBCC_CURSOR_TRIAGE_PR_ONLY", "1")
    monkeypatch.setenv("TBCC_CURSOR_TRIAGE_AUTO_FIX_ALLOWLIST", "session_sqlite_lock")
    ev = {"meta": {"code": "session_sqlite_lock"}, "message": "lock"}
    prompt = _build_agent_prompt(ev)
    assert "admin_bot.session" in prompt
    assert "NEVER push to main" in prompt
