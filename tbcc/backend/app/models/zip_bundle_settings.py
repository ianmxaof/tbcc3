"""Single-row settings: optional promo image + links file inside every TBCC-built or uploaded zip."""

from sqlalchemy import Boolean, Column, Integer, String, Text

from .base import Base


class ZipBundleSettings(Base):
    __tablename__ = "zip_bundle_settings"

    id = Column(Integer, primary_key=True, autoincrement=False, default=1)
    enabled = Column(Boolean, nullable=False, default=False)
    include_text_file = Column(Boolean, nullable=False, default=True)
    text_filename = Column(String(128), nullable=False, default="TBCC_README.txt")
    text_body = Column(Text, nullable=True)
    include_image = Column(Boolean, nullable=False, default=True)
    image_filename = Column(String(128), nullable=True)
