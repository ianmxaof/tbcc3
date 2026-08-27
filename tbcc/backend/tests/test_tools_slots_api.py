"""FastAPI /tools/slots router (app/api/tools_slots.py): thin wrapper over
api_slot_registry — register (write_env_secret + CredMan + add_slot), list,
suggest, show, call, remove. Also bridges "llm"-category registrations into
the rotator's own credential store (llm_model_index.set_credential) so a key
registered here is immediately usable via `llm ask` / the operator TUI's Ask
pane, not just `slots call`. No real network, no real Credential Manager, no
real .env: TBCC_API_SLOT_DB and TBCC_LLM_INDEX_DB both point at throwaway
tmp_path files, the env-file writer is monkeypatched at the store module, and
CredMan backup is stubbed out entirely (a test run must never touch the real
Windows Credential Manager)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import tools_slots
from app.main import app
from app.services import api_slot_registry as reg
from app.services import llm_model_index as idx
from app.services import tbcc_env_secret_store as store


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_API_SLOT_DB", str(tmp_path / "api_slot_registry_api_test.sqlite3"))
    monkeypatch.setenv("TBCC_LLM_INDEX_DB", str(tmp_path / "llm_index_api_test.sqlite3"))
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
    assert data["llm_provider_registered"] is False  # generic-rest, not an LLM hint match
    assert "TBCC_HTTPBIN_API_KEY=some-random-token-value-12345" in _isolated.read_text(encoding="utf-8")

    show = client.get("/tools/slots/httpbin")
    assert show.status_code == 200
    assert show.json()["auth_env_key"] == "TBCC_HTTPBIN_API_KEY"

    listed = client.get("/tools/slots")
    assert [s["id"] for s in listed.json()["slots"]] == ["httpbin"]
    assert idx._get_credential("httpbin") is None  # bridge must not fire for non-LLM slots


def test_register_llm_slot_bridges_into_rotator_credentials(client):
    """The real gap this closes: registering an LLM API here used to be
    invisible to `llm ask` / the operator TUI's Ask pane — callable only via
    `slots call`, never via the rotator. venice.ai matches the VENICE env-key
    hint (already in _LLM_ENV_HINTS); orcarouter.ai needed a new URL hint,
    added alongside this bridge."""
    r = client.post("/tools/slots", json={"value": "https://api.orcarouter.ai/v1\nsk-orca-abcdefghijklmnop"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["llm_provider_registered"] is True

    cred = idx._get_credential(data["id"])
    assert cred is not None
    assert cred["api_key"] == "sk-orca-abcdefghijklmnop"
    assert cred["base_url"] == "https://api.orcarouter.ai/v1"
    assert data["id"] in idx.custom_provider_ids()


def test_register_moonshot_llm_slot_bridges_into_rotator_credentials(client):
    r = client.post(
        "/tools/slots",
        json={"value": "https://api.moonshot.ai/v1\nsk-moonshot-abcdefghijklmnop"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["llm_provider_registered"] is True
    assert data["id"] == "moonshot"
    cred = idx._get_credential("moonshot")
    assert cred is not None
    assert cred["base_url"] == "https://api.moonshot.ai/v1"


def test_register_llm_slot_without_base_url_does_not_bridge(client):
    """A bare key with no URL context (no base_url resolvable) must not
    silently register a broken/incomplete rotator credential."""
    r = client.post("/tools/slots", json={"value": "sk-or-" + "x" * 24})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["llm_provider_registered"] is False
    assert idx._get_credential(data["id"]) is None


def test_register_explicit_overrides_win_over_auto_detection(client, _isolated):
    """id/category/auth_env_key/base_url are all explicit overrides on top of
    auto-detection — this was the operator's actual confusion: no visibility
    into what would be auto-detected and, for auth_env_key specifically, no
    way to override it at all before this."""
    r = client.post(
        "/tools/slots",
        json={
            "value": "sk-whatever-not-a-recognized-prefix-12345",
            "id": "my-custom-id",
            "category": "llm",
            "base_url": "https://example.com/v1",
            "auth_env_key": "MY_CUSTOM_KEY_NAME",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "my-custom-id"
    assert data["key"] == "MY_CUSTOM_KEY_NAME"
    assert data["llm_provider_registered"] is True
    assert "MY_CUSTOM_KEY_NAME=sk-whatever-not-a-recognized-prefix-12345" in _isolated.read_text(encoding="utf-8")

    slot = client.get("/tools/slots/my-custom-id").json()
    assert slot["category"] == "llm"
    assert slot["base_url"] == "https://example.com/v1"
    assert slot["auth_env_key"] == "MY_CUSTOM_KEY_NAME"

    cred = idx._get_credential("my-custom-id")
    assert cred["api_key"] == "sk-whatever-not-a-recognized-prefix-12345"
    assert cred["base_url"] == "https://example.com/v1"


def test_register_auth_env_key_override_with_blank_id_stays_consistent(client):
    """Real bug: pasting a real GitHub token (auto-suggests TBCC_GHCR_TOKEN
    from the ghp_ prefix) while overriding auth_env_key to something else and
    leaving id blank used to derive the id from the RAW auto-detected key,
    not the override — landing a slot whose id said "ghcr" while its actual
    stored auth_env_key said something else entirely. id must now be derived
    from the same override auth_env_key that actually gets stored."""
    r = client.post(
        "/tools/slots",
        json={
            "value": "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            "auth_env_key": "TBCC_GITGIST_TOKEN",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["key"] == "TBCC_GITGIST_TOKEN"
    assert "ghcr" not in data["id"]
    assert "gitgist" in data["id"]

    slot = client.get(f"/tools/slots/{data['id']}").json()
    assert slot["auth_env_key"] == "TBCC_GITGIST_TOKEN"


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
    data = r.json()
    assert data["ok"] is True
    assert data["status"] == 200
    assert data["body"] == {"ok": True}


def test_call_route_slot_not_found_is_structured_not_http_error(client):
    r = client.post("/tools/slots/nope/call", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is False
