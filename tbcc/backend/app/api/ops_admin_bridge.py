"""Mint / verify short-lived admin deep-links between TBCC dashboard and AOF Forum."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.external_payment_orders import _require_internal
from app.services import admin_bridge

router = APIRouter(prefix="/ops/admin-bridge", tags=["ops-admin-bridge"])

Destination = Literal["forum", "dashboard"]


class MintBody(BaseModel):
    destination: Destination
    next_path: str = Field(default="/", max_length=512)
    ttl_seconds: int = Field(default=admin_bridge.DEFAULT_TTL_SECONDS, ge=30, le=admin_bridge.MAX_TTL_SECONDS)


class ConsumeBody(BaseModel):
    token: str = Field(min_length=16, max_length=4096)
    expected_audience: Literal["forum_admin", "dashboard"] = "dashboard"


@router.post("/mint")
def mint_admin_bridge(body: MintBody, _: None = Depends(_require_internal)):
    """Return a one-shot URL to open the other admin surface."""
    try:
        if body.destination == "forum":
            next_path = body.next_path if body.next_path.startswith("/") else "/admin"
            if next_path == "/":
                next_path = "/admin"
            url = admin_bridge.build_forum_bridge_url(
                next_path=next_path, ttl_seconds=body.ttl_seconds
            )
            audience = "forum_admin"
        else:
            next_path = body.next_path if body.next_path.startswith("/") else "/"
            url = admin_bridge.build_dashboard_bridge_url(
                next_path=next_path, ttl_seconds=body.ttl_seconds
            )
            audience = "dashboard"
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "destination": body.destination,
        "audience": audience,
        "url": url,
        "ttl_seconds": body.ttl_seconds,
        "forum_public_url": admin_bridge.forum_public_base(),
        "dashboard_public_url": admin_bridge.dashboard_public_base(),
    }


@router.post("/consume")
def consume_admin_bridge(body: ConsumeBody, _: None = Depends(_require_internal)):
    """Validate a bridge token (dashboard landing uses this)."""
    try:
        payload = admin_bridge.verify_bridge_token(
            body.token, expected_audience=body.expected_audience
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "audience": payload.get("aud"),
        "next": payload.get("next") or "/",
        "exp": payload.get("exp"),
    }


@router.get("/config")
def admin_bridge_config(_: None = Depends(_require_internal)):
    """Public bases for UI link labels (no secrets)."""
    secret_set = False
    try:
        admin_bridge._bridge_secret()  # noqa: SLF001
        secret_set = True
    except RuntimeError:
        secret_set = False
    return {
        "ok": True,
        "secret_configured": secret_set,
        "forum_public_url": admin_bridge.forum_public_base(),
        "dashboard_public_url": admin_bridge.dashboard_public_base(),
        "ttl_default": admin_bridge.DEFAULT_TTL_SECONDS,
    }
