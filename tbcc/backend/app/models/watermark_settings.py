"""Dashboard-editable promo watermark settings (merged with tbcc/.env)."""

from sqlalchemy import Boolean, Column, Float, Integer, String

from .base import Base


class WatermarkSettings(Base):
    __tablename__ = "watermark_settings"

    id = Column(Integer, primary_key=True, autoincrement=False, default=1)
    enabled = Column(Boolean, nullable=True)
    text_primary = Column(String(120), nullable=True)
    text_secondary = Column(String(120), nullable=True)
    text_tertiary = Column(String(120), nullable=True)
    opacity = Column(Float, nullable=True)
    color = Column(String(16), nullable=True)
    strip_previous = Column(Boolean, nullable=True)
    apply_on_saved_import = Column(Boolean, nullable=False, default=False)
    apply_on_album_composer = Column(Boolean, nullable=False, default=True)
