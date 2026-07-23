"""Lane Drop Checkpoint API — review merchandise before dedicated channel post."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.lane_drop_checkpoint import (
    STATUS_PENDING,
    approve_lane_drop,
    create_lane_drop,
    lane_drop_as_dict,
    list_lane_drops,
    reject_lane_drop,
)

router = APIRouter()


class LaneDropCreateBody(BaseModel):
    network_key: str
    title: str | None = None
    promo_path: str | None = None
    lane_path: str | None = None
    vault_path: str | None = None
    glimpse_paths: list[str] | None = None
    destination_url: str | None = None
    primary_gate_url: str | None = None
    source_note: str | None = None


class LaneDropReviewBody(BaseModel):
    review_note: str | None = Field(default=None, max_length=2000)


@router.get("")
def get_lane_drops(
    status: str | None = STATUS_PENDING,
    network_key: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = list_lane_drops(db, status=status, network_key=network_key, limit=limit)
    return {"items": [lane_drop_as_dict(r) for r in rows], "count": len(rows)}


@router.post("")
def post_lane_drop(body: LaneDropCreateBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        row = create_lane_drop(
            db,
            network_key=body.network_key,
            title=body.title,
            promo_path=body.promo_path,
            lane_path=body.lane_path,
            vault_path=body.vault_path,
            glimpse_paths=body.glimpse_paths,
            destination_url=body.destination_url,
            primary_gate_url=body.primary_gate_url,
            source_note=body.source_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return lane_drop_as_dict(row)


@router.post("/{drop_id}/approve")
def post_approve(
    drop_id: int,
    body: LaneDropReviewBody | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    note = body.review_note if body else None
    try:
        row = approve_lane_drop(db, drop_id, review_note=note)
    except LookupError:
        raise HTTPException(status_code=404, detail="lane_drop_not_found") from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {
        **lane_drop_as_dict(row),
        "detail": "approved — post glimpse to Loot Room subtopic next (not auto in v1)",
    }


@router.post("/{drop_id}/reject")
def post_reject(
    drop_id: int,
    body: LaneDropReviewBody | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    note = body.review_note if body else None
    try:
        row = reject_lane_drop(db, drop_id, review_note=note)
    except LookupError:
        raise HTTPException(status_code=404, detail="lane_drop_not_found") from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {**lane_drop_as_dict(row), "detail": "rejected — stays warehouse / curated pack queue"}
