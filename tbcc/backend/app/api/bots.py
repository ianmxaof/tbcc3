from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import orm_to_dict

router = APIRouter()


@router.get("/")
def list_bots(db: Session = Depends(get_db)):
    from app.models.bot import Bot
    return [orm_to_dict(b) for b in db.query(Bot).all()]


@router.get("/{bot_id}")
def get_bot(bot_id: int, db: Session = Depends(get_db)):
    from app.models.bot import Bot
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        return {"error": "Not found"}
    return orm_to_dict(bot)
