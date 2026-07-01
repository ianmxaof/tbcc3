"""Post dividers between main-group feed posts (ornamental spacer images)."""

from sqlalchemy import Boolean, Column, Integer, String, Text

from .base import Base


class MainChannelDividerSettings(Base):
    __tablename__ = "main_channel_divider_settings"

    id = Column(Integer, primary_key=True, autoincrement=False, default=1)
    enabled = Column(Boolean, nullable=False, default=False)
    rotate_images = Column(Boolean, nullable=False, default=True)
    apply_in_topics = Column(Boolean, nullable=False, default=False)
    images_json = Column(Text, nullable=True)
    active_image_id = Column(String(64), nullable=True)
