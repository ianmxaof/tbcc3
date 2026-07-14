"""Phase 3a — read-only /zeus/v1 facade (no Telethon, no process Start)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ops_stack, zeus_v1


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(ops_stack.router)
    app.include_router(zeus_v1.router)
    return TestClient(app)


def test_zeus_stack_status_unavailable(monkeypatch):
    monkeypatch.setattr(ops_stack, "stack_control_available", lambda: False)
    r = _client().get("/zeus/v1/stack/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["available"] is False
    assert "tray" in (body.get("error") or "").lower()


def test_zeus_stack_status_matches_ops_shape(monkeypatch):
    sample = {
        "ok": True,
        "enabled_up": 3,
        "enabled": 5,
        "services": [{"id": "backend", "up": True}],
    }

    monkeypatch.setattr(ops_stack, "stack_control_available", lambda: True)
    monkeypatch.setattr(ops_stack, "get_stack_status", lambda: dict(sample))

    client = _client()
    zeus = client.get("/zeus/v1/stack/status")
    ops = client.get("/ops/stack-status")
    assert zeus.status_code == 200
    assert ops.status_code == 200
    assert zeus.json() == ops.json()
    assert zeus.json()["available"] is True
    assert zeus.json()["enabled_up"] == 3


def test_zeus_v1_has_no_start_routes():
    """Read-only facade: no process lifecycle verbs under /zeus/v1."""
    paths = {getattr(r, "path", "") for r in zeus_v1.router.routes}
    joined = " ".join(sorted(paths)).lower()
    for banned in ("/start", "/stop", "/restart"):
        assert banned not in joined
