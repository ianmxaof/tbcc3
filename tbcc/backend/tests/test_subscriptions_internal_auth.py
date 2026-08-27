"""Subscriptions router requires X-TBCC-Internal-Key when TBCC_INTERNAL_API_KEY is set."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

_HEADERS = {"X-TBCC-Internal-Key": "test-internal-key"}


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
        headers=_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["id"] == 1


def test_list_subscriptions_rejects_missing_internal_key(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_INTERNAL_API_KEY", "test-internal-key")
    client = TestClient(app)
    r = client.get("/subscriptions/")
    assert r.status_code == 403


def test_list_subscriptions_accepts_valid_internal_key(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_INTERNAL_API_KEY", "test-internal-key")

    class _FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, n):
            return self

        def all(self):
            return []

    class _FakeDb:
        def query(self, model):
            return _FakeQuery()

    def _fake_get_db():
        yield _FakeDb()

    from app.database.session import get_db

    app.dependency_overrides[get_db] = _fake_get_db
    try:
        client = TestClient(app)
        r = client.get("/subscriptions/", headers=_HEADERS)
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()


def test_get_subscription_rejects_missing_internal_key(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_INTERNAL_API_KEY", "test-internal-key")
    client = TestClient(app)
    r = client.get("/subscriptions/1")
    assert r.status_code == 403


def test_milestone_progress_rejects_missing_internal_key(monkeypatch) -> None:
    monkeypatch.setenv("TBCC_INTERNAL_API_KEY", "test-internal-key")
    client = TestClient(app)
    r = client.get("/subscriptions/milestone-progress")
    assert r.status_code == 403
