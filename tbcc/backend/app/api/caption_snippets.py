from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.caption_snippet import CaptionSnippet
from app.services import aof_copy_swipe as swipe_svc

router = APIRouter()


class CaptionSnippetCreate(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    body: str = Field(..., min_length=1)


class CaptionSnippetUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    body: str | None = Field(default=None, min_length=1)


class CaptionSnippetOut(BaseModel):
    id: int
    title: str | None
    body: str

    class Config:
        from_attributes = True


class CaptionSnippetBulkIn(BaseModel):
    items: list[CaptionSnippetCreate] = Field(..., min_length=1, max_length=500)


@router.get("/", response_model=list[CaptionSnippetOut])
def list_caption_snippets(db: Session = Depends(get_db)):
    rows = db.query(CaptionSnippet).order_by(CaptionSnippet.id.desc()).all()
    return [CaptionSnippetOut.model_validate(r) for r in rows]


@router.post("/bulk", response_model=dict)
def bulk_create_caption_snippets(data: CaptionSnippetBulkIn, db: Session = Depends(get_db)):
    n = 0
    for it in data.items:
        body = (it.body or "").strip()
        if not body:
            continue
        title = (it.title or "").strip() or None
        db.add(CaptionSnippet(title=title, body=body[:16000]))
        n += 1
    db.commit()
    return {"created": n}


@router.post("/", response_model=CaptionSnippetOut)
def create_caption_snippet(data: CaptionSnippetCreate, db: Session = Depends(get_db)):
    body = (data.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    title = (data.title or "").strip() or None
    row = CaptionSnippet(title=title, body=body[:16000])
    db.add(row)
    db.commit()
    db.refresh(row)
    return CaptionSnippetOut.model_validate(row)


@router.patch("/{snippet_id}", response_model=CaptionSnippetOut)
def update_caption_snippet(
    snippet_id: int, data: CaptionSnippetUpdate, db: Session = Depends(get_db)
):
    row = db.query(CaptionSnippet).filter(CaptionSnippet.id == snippet_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if data.title is not None:
        title = (data.title or "").strip() or None
        row.title = title[:256] if title else None
    if data.body is not None:
        body = (data.body or "").strip()
        if not body:
            raise HTTPException(status_code=400, detail="body required")
        row.body = body[:16000]
    db.commit()
    db.refresh(row)
    return CaptionSnippetOut.model_validate(row)


@router.delete("/{snippet_id}")
def delete_caption_snippet(snippet_id: int, db: Session = Depends(get_db)):
    row = db.query(CaptionSnippet).filter(CaptionSnippet.id == snippet_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": snippet_id}


@router.post("/migrate-local")
def migrate_local_captions(data: dict = Body(default={}), db: Session = Depends(get_db)):
    """
    One-shot: import `{ "items": [ { "title", "body" }, ... ] }` from dashboard localStorage migration.
    """
    items = data.get("items") or []
    if not isinstance(items, list):
        return {"imported": 0, "error": "items must be a list"}
    n = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        body = str(it.get("body") or "").strip()
        if not body:
            continue
        title = str(it.get("title") or "").strip() or None
        db.add(CaptionSnippet(title=title[:256] if title else None, body=body[:16000]))
        n += 1
    db.commit()
    return {"imported": n}


class SwipeIngestIn(BaseModel):
    body: str = Field(..., min_length=1)
    source: str = Field(default="dashboard_paste", max_length=128)
    format: str = Field(default="telegram_promo", max_length=64)
    tags: list[str] = Field(default_factory=list)
    tactics: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)
    swipe_id: str | None = Field(default=None, max_length=128)


class SwipeAdaptIn(BaseModel):
    lane: str = Field(..., min_length=1, max_length=64)
    promote: bool = False
    required_urls: list[str] = Field(default_factory=list)
    extra_facts: dict[str, str] = Field(default_factory=dict)


@router.get("/swipes")
def list_copy_swipes():
    return swipe_svc.list_swipes()


@router.post("/swipes/ingest")
def ingest_copy_swipe(data: SwipeIngestIn):
    try:
        entry = swipe_svc.ingest_swipe_raw(
            data.body,
            source=data.source,
            format=data.format,
            tags=data.tags,
            tactics=data.tactics,
            notes=data.notes,
            swipe_id=data.swipe_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return entry


@router.post("/swipes/{swipe_id}/adapt")
def adapt_copy_swipe(swipe_id: str, data: SwipeAdaptIn, db: Session = Depends(get_db)):
    if data.promote:
        try:
            return swipe_svc.promote_adapted_to_caption_snippets(
                db,
                swipe_id,
                data.lane,
                extra_facts=data.extra_facts or None,
                required_urls=data.required_urls or None,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        body = swipe_svc.adapt_swipe_sync(
            swipe_id,
            data.lane,
            extra_facts=data.extra_facts or None,
            required_urls=data.required_urls or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"swipe_id": swipe_id, "lane": data.lane, "body": body}
