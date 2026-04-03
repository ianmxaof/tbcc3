from sqlalchemy import Column, Integer, String, Boolean

from .base import Base


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    source_type = Column(String)  # telegram_channel | reddit | manual
    identifier = Column(String)  # channel username or URL
    active = Column(Boolean, default=True)
    pool_id = Column(Integer)  # auto-assign scraped content to this pool
