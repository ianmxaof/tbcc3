from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.source import Source

router = APIRouter()


class SourceCreate(BaseModel):
    name: str
    source_type: str = "telegram_channel"
    identifier: str
    pool_id: int
    active: bool = True


@router.get("/")
def list_sources(db: Session = Depends(get_db)):
    return [orm_to_dict(s) for s in db.query(Source).all()]


@router.get("/{source_id}")
def get_source(source_id: int, db: Session = Depends(get_db)):
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        return {"error": "Not found"}
    return orm_to_dict(s)


@router.post("/", status_code=201)
def create_source(body: SourceCreate, db: Session = Depends(get_db)):
    src = Source(
        name=body.name,
        source_type=body.source_type,
        identifier=body.identifier,
        pool_id=body.pool_id,
        active=body.active,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return orm_to_dict(src)
