"""Unified campaign deploy API — Telegram + Buffer + Discord in one call."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.campaign_deploy_service import (
    DeployOptions,
    audit_scheduled_posts,
    deploy_scheduled_post,
    list_recent_deploys,
)

router = APIRouter()


class CampaignDeployBody(BaseModel):
    telegram: bool = True
    buffer: bool | None = Field(None, description="None = use post.buffer_mirror_enabled")
    discord: bool | None = Field(None, description="None = use post.discord_mirror_enabled")
    sync: bool = Field(False, description="Run inline (blocks until Telegram+mirrors finish)")
    reshuffle: bool = False


@router.get("/deploys")
def get_recent_deploys(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    return {"deploys": list_recent_deploys(db, limit=limit)}


@router.get("/audit/schedules")
def audit_schedules(db: Session = Depends(get_db)):
    return {"schedules": audit_scheduled_posts(db)}


@router.post("/deploy/post/{post_id}")
def deploy_post(
    post_id: int,
    body: CampaignDeployBody | None = None,
    db: Session = Depends(get_db),
):
    body = body or CampaignDeployBody()
    try:
        result = deploy_scheduled_post(
            db,
            post_id,
            DeployOptions(
                telegram=body.telegram,
                buffer=body.buffer,
                discord=body.discord,
                sync=body.sync,
                reshuffle_album=body.reshuffle,
                trigger="api",
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return result.to_dict()


@router.post("/deploy/campaign/{campaign_group_id}")
def deploy_campaign_group(
    campaign_group_id: str,
    body: CampaignDeployBody | None = None,
    db: Session = Depends(get_db),
):
    body = body or CampaignDeployBody()
    leader = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.campaign_group_id == campaign_group_id)
        .order_by(ScheduledTextPost.id)
        .first()
    )
    if not leader:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        result = deploy_scheduled_post(
            db,
            int(leader.id),
            DeployOptions(
                telegram=body.telegram,
                buffer=body.buffer,
                discord=body.discord,
                sync=body.sync,
                reshuffle_album=body.reshuffle,
                trigger="api_campaign",
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return result.to_dict()
