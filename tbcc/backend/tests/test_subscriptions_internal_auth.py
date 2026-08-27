"""POST /subscriptions/ requires X-TBCC-Internal-Key when TBCC_INTERNAL_API_KEY is set."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_create_subscription_open_when_internal_key_unset(monkeypatch) -> None:
    monkeypatch.delenv("TBCC_INTERNAL_API_KEY", raising=False)
    client = TestClient(app)
    r = client.post("/subscriptions/", json={})
    assert r.status_code == 200
    assert r.json().get("error") == "telegram_user_id and plan_id required"


def test_create_subscription_rejects_missing_internal_key(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_INTERNAL_API_KEY", "test-internal-key")
    client = TestClient(app)
    r = client.post("/subscriptions/", json={"telegram_user_id": 1, "plan_id": 1})
    assert r.status_code == 403
    assert "X-TBCC-Internal-Key" in r.json().get("detail", "")


def test_create_subscription_accepts_valid_internal_key(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_INTERNAL_API_KEY", "test-internal-key")

    def _fake_create(data: dict, db) -> dict:
        return {"id": 1, "telegram_user_id": data["telegram_user_id"]}

    monkeypatch.setattr("app.api.subscriptions.subscription_create_from_payload", _fake_create)
    client = TestClient(app)
    r = client.post(
        "/subscriptions/",
        json={"telegram_user_id": 1, "plan_id": 1},
        headers={"X-TBCC-Internal-Key": "test-internal-key"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == 1
