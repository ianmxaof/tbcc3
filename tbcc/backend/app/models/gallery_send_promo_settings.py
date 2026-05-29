"""Global settings: promo image(s) appended to the end of gallery batch sends."""

from sqlalchemy import Boolean, Column, Integer, String, Text

from .base import Base


class GallerySendPromoSettings(Base):
    __tablename__ = "gallery_send_promo_settings"

    id = Column(Integer, primary_key=True, autoincrement=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    images_json = Column(Text, nullable=True)
    active_image_id = Column(String(64), nullable=True)
