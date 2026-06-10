from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.caption_snippet import CaptionSnippet

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
