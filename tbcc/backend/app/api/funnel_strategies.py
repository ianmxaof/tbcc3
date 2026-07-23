from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.funnel_strategy import FunnelStrategyEntry
from app.services.funnel_rag import build_funnel_context, search_funnel_strategies, seed_default_funnel_strategies

router = APIRouter()


class FunnelStrategyCreate(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    pattern: str = Field(..., min_length=2, max_length=64)
    surface: str = Field(..., min_length=2, max_length=32)
    copy_template: str | None = None
    visual_notes: str | None = None
    screenshot_ref: str | None = Field(default=None, max_length=512)
    risk_tags: str | None = Field(default=None, max_length=256)


class FunnelStrategyOut(BaseModel):
    id: int
    title: str | None
    pattern: str
    surface: str
    copy_template: str | None
    visual_notes: str | None
    screenshot_ref: str | None
    risk_tags: str | None
    is_active: bool

    class Config:
        from_attributes = True


class FunnelStrategyBulkIn(BaseModel):
    items: list[FunnelStrategyCreate] = Field(..., min_length=1, max_length=200)


@router.get("/", response_model=list[FunnelStrategyOut])
def list_funnel_strategies(
    surface: str | None = Query(None),
    pattern: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = search_funnel_strategies(db, surface=surface, pattern=pattern, query=q, limit=limit)
    return [FunnelStrategyOut.model_validate(r) for r in rows]


@router.get("/context")
def funnel_context(
    surface: str = Query(..., min_length=2),
    goal: str | None = Query(None),
    db: Session = Depends(get_db),
):
    return {"surface": surface, "context": build_funnel_context(db, surface=surface, goal=goal)}


@router.post("/bulk", response_model=dict)
def bulk_create_funnel_strategies(data: FunnelStrategyBulkIn, db: Session = Depends(get_db)):
    n = 0
    for it in data.items:
        db.add(
            FunnelStrategyEntry(
                title=(it.title or "").strip() or None,
                pattern=it.pattern.strip().lower(),
                surface=it.surface.strip().lower(),
                copy_template=(it.copy_template or "").strip() or None,
                visual_notes=(it.visual_notes or "").strip() or None,
                screenshot_ref=(it.screenshot_ref or "").strip() or None,
                risk_tags=(it.risk_tags or "").strip() or None,
                is_active=True,
            )
        )
        n += 1
    db.commit()
    return {"created": n}


@router.post("/seed-defaults", response_model=dict)
def post_seed_defaults(db: Session = Depends(get_db)):
    return {"created": seed_default_funnel_strategies(db)}


@router.delete("/{entry_id}", response_model=dict)
def delete_funnel_strategy(entry_id: int, db: Session = Depends(get_db)):
    row = db.query(FunnelStrategyEntry).filter(FunnelStrategyEntry.id == entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.is_active = False
    db.commit()
    return {"ok": True}
