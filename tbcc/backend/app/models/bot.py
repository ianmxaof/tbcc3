from sqlalchemy import Column, Integer, String, DateTime

from .base import Base


class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    api_id = Column(String)
    api_hash = Column(String)
    session = Column(String)  # Telethon session string
    role = Column(String)  # storage | scraper | poster | admin
    status = Column(String, default="stopped")
    last_seen = Column(DateTime, nullable=True)
