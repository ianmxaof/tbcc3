"""Tests for creator profile URL normalization and gated submit."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.loot import LootCreatorSubmission, LootModifier
from app.services.loot_creator_platforms import (
    extract_submission_url,
    normalize_creator_url,
)
from app.services.loot_creator_submit import (
    approve_creator_submission,
    reject_creator_submission,
    submit_creator_profile,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LootModifier.__table__,
            LootCreatorSubmission.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_normalize_onlyfans():
    out = normalize_creator_url("https://onlyfans.com/creator_name")
    assert out is not None
    assert out[0] == "https://onlyfans.com/creator_name"
    assert out[2] == "OF"


def test_normalize_extracts_url_from_text():
    out = normalize_creator_url("my page https://fansly.com/handle thanks")
    assert out is not None
    assert out[0] == "https://fansly.com/handle"


def test_normalize_fanvue():
    out = normalize_creator_url("fanvue.com/modelx")
    assert out is not None
    assert out[0] == "https://fanvue.com/modelx"


def test_normalize_privacy_br():
    out = normalize_creator_url("https://privacy.com.br/profile/creatorx")
    assert out is not None
    assert out[0] == "https://privacy.com.br/profile/creatorx"


def test_normalize_telegram():
    out = normalize_creator_url("https://t.me/my_channel")
    assert out is not None
    assert out[0] == "https://t.me/my_channel"


def test_normalize_snapchat():
    out = normalize_creator_url("https://snapchat.com/add/myhandle")
    assert out is not None
    assert out[0] == "https://snapchat.com/add/myhandle"


def test_normalize_kik():
    out = normalize_creator_url("https://kik.me/username")
    assert out is not None
    assert out[0] == "https://kik.me/username"


def test_normalize_sextingfinder():
    out = normalize_creator_url("https://sextingfinder.com/profile/user1")
    assert out is not None
    assert "sextingfinder.com" in out[0]


def test_rejects_link_hub_gate():
    assert normalize_creator_url("https://link-hub.net/1367336/abc") is None


def test_rejects_bitly():
    assert normalize_creator_url("https://bit.ly/abc123") is None


def test_extract_submission_url_plain():
    assert extract_submission_url("onlyfans.com/foo") == "onlyfans.com/foo"
    assert extract_submission_url("check https://boosty.to/creator") == "https://boosty.to/creator"


def test_submit_queues_pending(db):
    result = submit_creator_profile(
        db,
        url="https://onlyfans.com/testcreator",
        telegram_user_id=12345,
    )
    assert result["ok"] is True
    assert result["pending_review"] is True
    row = db.query(LootCreatorSubmission).filter_by(id=result["submission_id"]).first()
    assert row is not None
    assert row.status == "pending"
    assert db.query(LootModifier).count() == 0


def test_approve_creates_modifier(db):
    result = submit_creator_profile(
        db,
        url="https://fansly.com/approved",
        telegram_user_id=99,
    )
    approved = approve_creator_submission(db, result["submission_id"], reviewer_user_id=1)
    assert approved["ok"] is True
    mod = db.query(LootModifier).filter_by(id=approved["modifier_id"]).first()
    assert mod is not None
    assert mod.active is True
    assert mod.target_url == "https://fansly.com/approved"


def test_reject_does_not_create_modifier(db):
    result = submit_creator_profile(
        db,
        url="https://manyvids.com/rejectme",
        telegram_user_id=77,
    )
    rejected = reject_creator_submission(db, result["submission_id"], review_note="spam")
    assert rejected["ok"] is True
    assert db.query(LootModifier).count() == 0
    row = db.query(LootCreatorSubmission).get(result["submission_id"])
    assert row.status == "rejected"
