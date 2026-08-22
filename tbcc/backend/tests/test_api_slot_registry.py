"""PC-local API slot registry (app/services/api_slot_registry.py): classify,
parse, CRUD, and the generic REST caller. No real network — httpx.request /
httpx.get are monkeypatched, and every test points TBCC_API_SLOT_DB at a
throwaway tmp_path file."""

from __future__ import annotations

import pytest

from app.services import api_slot_registry as reg


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_API_SLOT_DB", str(tmp_path / "api_slot_registry_test.sqlite3"))


class _FakeResponse:
    def __init__(self, status: int, payload=None, text: str = ""):
        self.status_code = status
        self._payload = payload
        self.text = text or str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


def test_classify_category_llm_from_env_key():
    assert reg.classify_category(auth_env_key="OPENROUTER_API_KEY") == "llm"


def test_classify_category_llm_from_url():
    assert reg.classify_category(auth_env_key="TBCC_FOO_API_KEY", base_url="https://api.anthropic.com") == "llm"


def test_classify_category_generic_default():
    assert reg.classify_category(auth_env_key="TBCC_HTTPBIN_API_KEY", base_url="https://httpbin.org") == "generic-rest"


def test_parse_slot_source_multiline():
    parsed = reg.parse_slot_source("https://api.example.com\nsk-abcdef1234567890")
    assert parsed == {"url": "https://api.example.com", "key": "sk-abcdef1234567890"}


def test_parse_slot_source_curl_bearer():
    parsed = reg.parse_slot_source(
        "curl https://api.example.com/v1/chat -H 'Authorization: Bearer sk-xyz123'"
    )
    assert parsed["key"] == "sk-xyz123"
    assert parsed["url"] == "https://api.example.com/v1/chat"


def test_parse_slot_source_curl_x_api_key():
    parsed = reg.parse_slot_source("curl https://api.example.com -H 'X-Api-Key: abc-999'")
    assert parsed["key"] == "abc-999"


def test_parse_slot_source_key_only():
    parsed = reg.parse_slot_source("sk-or-abcdefghijklmnop")
    assert parsed == {"key": "sk-or-abcdefghijklmnop"}


def test_suggest_slot_generates_id_and_category():
    result = reg.suggest_slot("https://api.openrouter.ai\nsk-or-" + ("x" * 24))
    assert result["auth_env_key"] == "OPENROUTER_API_KEY"
    assert result["category"] == "llm"
    assert result["id"] == "openrouter"
    assert result["base_url"] == "https://api.openrouter.ai"


def test_slot_id_from_hint_drops_leading_api_subdomain():
    assert reg._slot_id_from_hint("https://api.openrouter.ai", "OPENROUTER_API_KEY") == "openrouter"


def test_slot_id_from_hint_two_label_host_unchanged():
    assert reg._slot_id_from_hint("https://httpbin.org", "TBCC_HTTPBIN_API_KEY") == "httpbin"


def test_slot_id_from_hint_strips_www_then_api_subdomain():
    assert reg._slot_id_from_hint("https://www.api.example.com", "TBCC_FOO_API_KEY") == "example"


def test_fallback_env_key_shares_the_same_host_heuristic():
    result = reg.suggest_slot("https://api.foo.com\nsk-abcdefghijklmnopqrstuvwx")
    assert result["auth_env_key"] == "TBCC_FOO_API_KEY"
    assert result["id"] == "foo"


def test_suggest_slot_unknown_key_falls_back_to_host_env_key():
    result = reg.suggest_slot("https://httpbin.org\nsome-random-token-value-12345")
    assert result["auth_env_key"] == "TBCC_HTTPBIN_API_KEY"
    assert result["category"] == "generic-rest"
    assert result["id"] == "httpbin"


def test_suggest_slot_id_override():
    result = reg.suggest_slot("sometoken1234567890", id_override="My Slot")
    assert result["id"] == "my-slot"


def test_add_slot_and_get_slot_roundtrip():
    added = reg.add_slot(
        auth_env_key="tbcc httpbin api key",
        base_url="https://httpbin.org/",
        category="generic-rest",
        method="post",
        path_template="/post",
    )
    assert added["id"] == "httpbin"
    assert added["auth_env_key"] == "TBCC_HTTPBIN_API_KEY"
    assert added["base_url"] == "https://httpbin.org"
    assert added["method"] == "POST"

    fetched = reg.get_slot("httpbin")
    assert fetched == added

    listed = reg.list_slots()
    assert [s["id"] for s in listed] == ["httpbin"]


def test_add_slot_id_collision_suffix():
    reg.add_slot(auth_env_key="TBCC_HTTPBIN_API_KEY", base_url="https://httpbin.org", slot_id="dup")
    second = reg.add_slot(auth_env_key="TBCC_OTHER_API_KEY", base_url="https://other.example.com", slot_id="dup")
    assert second["id"] == "dup-2"


def test_add_slot_invalid_auth_style_raises():
    with pytest.raises(ValueError):
        reg.add_slot(auth_env_key="TBCC_FOO_API_KEY", auth_style="basic")  # type: ignore[arg-type]


def test_add_slot_openapi_failure_registers_with_warning(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("HTTP 404")

    monkeypatch.setattr(reg.httpx, "get", _boom)
    result = reg.add_slot(
        auth_env_key="TBCC_FOO_API_KEY",
        base_url="https://api.foo.com",
        openapi_url="https://api.foo.com/openapi.json",
    )
    assert result["warning"] is not None
    assert result["base_url"] == "https://api.foo.com"


def test_add_slot_openapi_picks_first_post_path(monkeypatch):
    spec = {"paths": {"/v1/ping": {"get": {}}, "/v1/echo": {"post": {}}}}
    monkeypatch.setattr(reg.httpx, "get", lambda *a, **k: _FakeResponse(200, spec))
    result = reg.add_slot(
        auth_env_key="TBCC_FOO_API_KEY",
        base_url="https://api.foo.com",
        openapi_url="https://api.foo.com/openapi.json",
    )
    assert result["path_template"] == "/v1/echo"
    assert result["method"] == "POST"
    assert "warning" not in result


def test_remove_slot():
    reg.add_slot(auth_env_key="TBCC_FOO_API_KEY", base_url="https://api.foo.com", slot_id="foo")
    assert reg.remove_slot("foo") is True
    assert reg.get_slot("foo") is None
    assert reg.remove_slot("foo") is False


def test_call_slot_not_found():
    result = reg.call_slot("does-not-exist")
    assert result == {"ok": False, "error": "slot 'does-not-exist' not found"}


def test_call_slot_missing_env_var():
    reg.add_slot(auth_env_key="TBCC_MISSING_API_KEY", base_url="https://api.foo.com", slot_id="foo")
    result = reg.call_slot("foo")
    assert result["ok"] is False
    assert "TBCC_MISSING_API_KEY" in result["error"]


def test_call_slot_success_bearer(monkeypatch):
    reg.add_slot(
        auth_env_key="TBCC_SMOKE_API_KEY",
        base_url="https://httpbin.org",
        slot_id="smoke",
        method="POST",
        path_template="/post",
    )
    monkeypatch.setenv("TBCC_SMOKE_API_KEY", "sk-test-123")

    captured = {}

    def _fake_request(method, url, *, headers=None, params=None, json=None, timeout=None):
        captured.update(method=method, url=url, headers=headers, params=params, json=json)
        return _FakeResponse(200, {"echo": json})

    monkeypatch.setattr(reg.httpx, "request", _fake_request)
    result = reg.call_slot("smoke", body={"hello": "pocket"})

    assert result == {"ok": True, "status": 200, "body": {"echo": {"hello": "pocket"}}}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://httpbin.org/post"
    assert captured["headers"]["Authorization"] == "Bearer sk-test-123"


def test_call_slot_query_auth_style(monkeypatch):
    reg.add_slot(
        auth_env_key="TBCC_QUERYAUTH_API_KEY",
        base_url="https://api.example.com",
        slot_id="qa",
        auth_style="query",
        path_template="/v1/data",
    )
    monkeypatch.setenv("TBCC_QUERYAUTH_API_KEY", "qkey")

    captured = {}

    def _fake_request(method, url, *, headers=None, params=None, json=None, timeout=None):
        captured.update(headers=headers, params=params)
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(reg.httpx, "request", _fake_request)
    result = reg.call_slot("qa")

    assert result["ok"] is True
    assert captured["params"] == {"api_key": "qkey"}
    assert "Authorization" not in captured["headers"]


def test_call_slot_http_error(monkeypatch):
    reg.add_slot(auth_env_key="TBCC_FAIL_API_KEY", base_url="https://api.foo.com", slot_id="fail")
    monkeypatch.setenv("TBCC_FAIL_API_KEY", "k")

    def _boom(*a, **k):
        raise reg.httpx.ConnectError("connection refused")

    monkeypatch.setattr(reg.httpx, "request", _boom)
    result = reg.call_slot("fail")
    assert result["ok"] is False
    assert "connection refused" in result["error"]


def test_call_slot_non_json_body(monkeypatch):
    reg.add_slot(auth_env_key="TBCC_TEXT_API_KEY", base_url="https://api.foo.com", slot_id="textslot")
    monkeypatch.setenv("TBCC_TEXT_API_KEY", "k")
    monkeypatch.setattr(reg.httpx, "request", lambda *a, **k: _FakeResponse(200, None, text="plain text"))
    result = reg.call_slot("textslot")
    assert result == {"ok": True, "status": 200, "body": "plain text"}
