"""Leave-message service cleanup helpers."""

from bots.leave_message_cleanup import leave_cleanup_chat_allowlist, leave_cleanup_enabled


def test_leave_cleanup_enabled_default(monkeypatch):
    monkeypatch.delenv("TBCC_CLEAN_LEAVE_MESSAGES", raising=False)
    monkeypatch.delenv("TBCC_SECRETARY_CLEAN_SERVICE_MESSAGES", raising=False)
    assert leave_cleanup_enabled() is True


def test_leave_cleanup_disabled(monkeypatch):
    monkeypatch.setenv("TBCC_CLEAN_LEAVE_MESSAGES", "0")
    assert leave_cleanup_enabled() is False


def test_leave_cleanup_legacy_secretary_env(monkeypatch):
    monkeypatch.delenv("TBCC_CLEAN_LEAVE_MESSAGES", raising=False)
    monkeypatch.setenv("TBCC_SECRETARY_CLEAN_SERVICE_MESSAGES", "false")
    assert leave_cleanup_enabled() is False


def test_leave_cleanup_allowlist(monkeypatch):
    monkeypatch.setenv("TBCC_CLEAN_LEAVE_CHAT_IDS", "-1003927742839, 123")
    assert leave_cleanup_chat_allowlist() == {-1003927742839, 123}


def test_leave_cleanup_allowlist_empty(monkeypatch):
    monkeypatch.delenv("TBCC_CLEAN_LEAVE_CHAT_IDS", raising=False)
    assert leave_cleanup_chat_allowlist() is None
