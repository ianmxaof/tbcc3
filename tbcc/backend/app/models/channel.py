from sqlalchemy import Column, Integer, String

from .base import Base


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    identifier = Column(String, nullable=False)  # @username or -100xxxxxxxxxx
    invite_link = Column(String, nullable=True)  # t.me/joinchat/xxx or t.me/channel for public
