"""Macro search source submissions — community suggestions with admin governance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.archive_governance import (
    approve_macro_source_submission,
    create_macro_source_submission,
    list_macro_source_submissions,
    reject_macro_source_submission,
)

router = APIRouter(prefix="/macro-search", tags=["macro-search"])


class MacroSourceSubmitBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    url_template: str = Field(..., min_length=8, max_length=1024)
    sample_username: str | None = Field(None, max_length=64)
    sample_search_url: str | None = Field(None, max_length=2000)
    submitted_by: str | None = Field(None, max_length=32)


class MacroSourceReviewBody(BaseModel):
    reviewed_by: str | None = Field(None, max_length=32)
    review_note: str | None = Field(None, max_length=400)


@router.post("/source-submissions")
def submit_macro_source(body: MacroSourceSubmitBody, db: Session = Depends(get_db)):
    result = create_macro_source_submission(
        db,
        name=body.name,
        url_template=body.url_template,
        sample_username=body.sample_username,
        sample_search_url=body.sample_search_url,
        submitted_by=body.submitted_by,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "submit_failed")
    return result


@router.get("/source-submissions")
def list_submissions(
    status: str | None = Query("pending"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    items = list_macro_source_submissions(db, status=status or None, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/source-submissions/{submission_id}/approve")
def approve_submission(
    submission_id: int,
    body: MacroSourceReviewBody,
    db: Session = Depends(get_db),
):
    from app.services.archive_governance import append_custom_macro_source

    def _patch(site: dict[str, str], *, merge: bool = True) -> bool:
        return append_custom_macro_source(db, site)

    result = approve_macro_source_submission(
        db,
        submission_id,
        reviewed_by=body.reviewed_by,
        review_note=body.review_note,
        patch_custom_sources=_patch,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "not_found")
    return result


@router.post("/source-submissions/{submission_id}/reject")
def reject_submission(
    submission_id: int,
    body: MacroSourceReviewBody,
    db: Session = Depends(get_db),
):
    result = reject_macro_source_submission(
        db,
        submission_id,
        reviewed_by=body.reviewed_by,
        review_note=body.review_note,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "not_found")
    return result
