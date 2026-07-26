"""Loot goblin claim + revoke API (loot bot deep-link grants)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.goblin_service import claim_goblin_drop, revoke_goblin_drop

router = APIRouter()


class GoblinClaimBody(BaseModel):
    token: str = Field(..., min_length=4, max_length=64)
    telegram_user_id: int = Field(..., ge=1)


class GoblinRevokeBody(BaseModel):
    token: str = Field(..., min_length=4, max_length=64)


@router.post("/claim")
def goblin_claim(body: GoblinClaimBody, db: Session = Depends(get_db)):
    result = claim_goblin_drop(
        db,
        token=body.token.strip(),
        telegram_user_id=int(body.telegram_user_id),
    )
    if not result.get("ok"):
        reason = str(result.get("reason") or "claim_failed")
        if reason in ("exhausted", "revoked"):
            raise HTTPException(status_code=410, detail=result)
        if reason == "already_claimed":
            raise HTTPException(status_code=409, detail=result)
        if reason == "not_found":
            raise HTTPException(status_code=404, detail=result)
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/revoke")
def goblin_revoke(body: GoblinRevokeBody, db: Session = Depends(get_db)):
    result = revoke_goblin_drop(db, token=body.token.strip())
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result)
    return result
