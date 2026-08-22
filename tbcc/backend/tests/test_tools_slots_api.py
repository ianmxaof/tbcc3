"""FastAPI /tools/slots router (app/api/tools_slots.py): thin wrapper over
api_slot_registry — register (write_env_secret + CredMan + add_slot), list,
suggest, show, call, remove. No real network, no real Credential Manager,
no real .env: TBCC_API_SLOT_DB points at a throwaway tmp_path file, the
env-file writer is monkeypatched at the store module, and CredMan backup is
stubbed out entirely (a test run must never touch the real Windows
Credential Manager)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import tools_slots
from app.main import app
from app.services import api_slot_registry as reg
from app.services import tbcc_env_secret_store as store


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_API_SLOT_DB", str(tmp_path / "api_slot_registry_api_test.sqlite3"))
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(store, "env_file_path", lambda: env_file)
    monkeypatch.setattr(tools_slots, "backup_credential_manager", lambda key, value: False)
    return env_file


@pytest.fixture()
def client():
    return TestClient(app)


class _FakeResponse:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_list_empty(client):
    r = client.get("/tools/slots")
    assert r.status_code == 200
    assert r.json() == {"slots": []}


def test_suggest_route(client):
    r = client.post(
        "/tools/slots/suggest",
        json={"text": "sk-or-" + "x" * 24, "page_url": "https://openrouter.ai"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["auth_env_key"] == "OPENROUTER_API_KEY"
    assert data["category"] == "llm"


def test_register_writes_env_and_slot(client, _isolated):
    r = client.post("/tools/slots", json={"value": "https://httpbin.org\nsome-random-token-value-12345"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["id"] == "httpbin"
    assert data["key"] == "TBCC_HTTPBIN_API_KEY"
    assert data["backed_up_credential_manager"] is False
    assert "TBCC_HTTPBIN_API_KEY=some-random-token-value-12345" in _isolated.read_text(encoding="utf-8")

    show = client.get("/tools/slots/httpbin")
    assert show.status_code == 200
    assert show.json()["auth_env_key"] == "TBCC_HTTPBIN_API_KEY"

    listed = client.get("/tools/slots")
    assert [s["id"] for s in listed.json()["slots"]] == ["httpbin"]


def test_register_rejects_non_key_value(client):
    r = client.post("/tools/slots", json={"value": "short"})
    assert r.status_code == 400


def test_get_missing_slot_404(client):
    r = client.get("/tools/slots/does-not-exist")
    assert r.status_code == 404


def test_remove_missing_slot_404(client):
    r = client.delete("/tools/slots/does-not-exist")
    assert r.status_code == 404


def test_register_then_remove(client):
    r = client.post("/tools/slots", json={"value": "https://api.foo.com\nsk-abcdefghijklmnopqrstuvwx"})
    assert r.json()["id"] == "foo"

    removed = client.delete("/tools/slots/foo")
    assert removed.status_code == 200
    assert removed.json() == {"ok": True}
    assert client.get("/tools/slots/foo").status_code == 404


def test_call_route_success(client, monkeypatch):
    reg.add_slot(
        auth_env_key="TBCC_SMOKE_API_KEY",
        base_url="https://httpbin.org",
        slot_id="smoke",
        method="POST",
        path_template="/post",
    )
    monkeypatch.setenv("TBCC_SMOKE_API_KEY", "sk-test")
    monkeypatch.setattr(reg.httpx, "request", lambda *a, **k: _FakeResponse(200, {"ok": True}))

    r = client.post("/tools/slots/smoke/call", json={"body": {"hello": "pocket"}})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "status": 200, "body": {"ok": True}}


def test_call_route_slot_not_found_is_structured_not_http_error(client):
    r = client.post("/tools/slots/nope/call", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is False
