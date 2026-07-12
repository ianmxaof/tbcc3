"""Zeus Phase 1 menu helpers — callback aliases, stack HTML, keyboards."""

from __future__ import annotations

from bots.zeus_menu import (
    admin_main_menu_keyboard,
    admin_ops_submenu_keyboard,
    format_stack_status_html,
    loot_bot_username,
    network_submenu_keyboard,
    normalize_menu_callback,
    payment_bot_username,
)


def test_normalize_sec_passthrough():
    assert normalize_menu_callback("sec:menu:home") == "sec:menu:home"
    assert normalize_menu_callback("sec:menu:run:inbox") == "sec:menu:run:inbox"


def test_normalize_zeus_aliases():
    assert normalize_menu_callback("zeus:home") == "sec:menu:home"
    assert normalize_menu_callback("zeus:net:home") == "sec:menu:cat:net"
    assert normalize_menu_callback("zeus:inbox:home") == "sec:menu:cat:inbox"
    assert normalize_menu_callback("zeus:ops:home") == "sec:menu:cat:ops"
    assert normalize_menu_callback("zeus:more:home") == "sec:menu:cat:more"
    assert normalize_menu_callback("zeus:ops:stack") == "sec:menu:run:stack"
    assert normalize_menu_callback("zeus:inbox:full") == "sec:menu:run:inbox"


def test_normalize_rejects_noise():
    assert normalize_menu_callback(None) is None
    assert normalize_menu_callback("") is None
    assert normalize_menu_callback("ops:approve:1") is None


def test_payment_username_avoids_secretary_collision(monkeypatch):
    monkeypatch.setenv("TBCC_SECRETARY_BOT_USERNAME", "aof_secretary_bot")
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aof_secretary_bot")
    monkeypatch.delenv("BOT_USERNAME", raising=False)
    assert payment_bot_username() == "aofsubscriptions_bot"


def test_loot_username_default(monkeypatch):
    monkeypatch.delenv("TBCC_LOOT_BOT_USERNAME", raising=False)
    assert loot_bot_username() == "aof_lootgod_bot"


def test_format_stack_status_unavailable():
    html = format_stack_status_html({"ok": False, "available": False, "error": "no tray"})
    assert "Stack status" in html
    assert "no tray" in html
    assert "tbcc-stack-cli" in html


def test_format_stack_status_rows():
    html = format_stack_status_html(
        {
            "ok": True,
            "available": True,
            "enabled_up": 7,
            "enabled": 8,
            "up": 7,
            "total": 10,
            "profile": "lean",
            "services": [
                {"id": "backend", "status": "up", "running": True, "user_enabled": True},
                {"id": "payment", "status": "down", "running": False, "user_enabled": True},
            ],
        }
    )
    assert "7/8" in html
    assert "lean" in html
    assert "backend" in html
    assert "payment" in html
    assert "tbcc-stack-cli" in html


def test_admin_root_has_four_sections():
    kb = admin_main_menu_keyboard()
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert flat == ["zeus:net:home", "zeus:inbox:home", "zeus:ops:home", "zeus:more:home"]


def test_ops_submenu_includes_stack():
    kb = admin_ops_submenu_keyboard()
    flat = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
    assert "zeus:ops:stack" in flat
    assert "zeus:ops:focus" in flat


def test_network_submenu_has_url_deep_links(monkeypatch):
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "paybot")
    monkeypatch.setenv("TBCC_LOOT_BOT_USERNAME", "lootbot")
    monkeypatch.setenv("TBCC_COMPANION_BOT_USERNAME", "spicy")
    monkeypatch.setenv("TBCC_SECRETARY_BOT_USERNAME", "secbot")
    kb = network_submenu_keyboard()
    urls = [b.url for row in kb.inline_keyboard for b in row if b.url]
    assert any("t.me/paybot?start=subscribe" in u for u in urls)
    assert any("t.me/lootbot?start=loot_free" in u for u in urls)
    assert any("t.me/spicy" in u for u in urls)
