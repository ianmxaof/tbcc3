"""Shared pytest fixtures for TBCC backend tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.promo_affiliate_link import PromoAffiliateLink  # noqa: F401
from app.models.promo_affiliate_rotation_cursor import PromoAffiliateRotationCursor  # noqa: F401
from app.models.secretary_pending_draft import SecretaryPendingDraft  # noqa: F401


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
