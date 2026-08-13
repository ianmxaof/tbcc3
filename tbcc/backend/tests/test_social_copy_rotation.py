"""Tests for social copy rotation."""

from __future__ import annotations

from app.models.social_copy_template import SocialCopyTemplate
from app.services.social_copy_rotation import mark_template_used, pick_social_copy_template


def test_demote_after_two_uses(db):
    row = SocialCopyTemplate(
        category="lootgod",
        surface="x_buffer",
        body="test {hub}",
        max_uses_before_demote=2,
        sort_order=0,
        is_active=True,
    )
    db.add(row)
    db.commit()

    picked = pick_social_copy_template(db, category="lootgod")
    assert picked is not None
    assert picked.use_count == 1

    picked2 = pick_social_copy_template(db, category="lootgod")
    assert picked2.use_count == 0
    assert picked2.sort_order >= 1


def test_pick_lowest_use_count_first(db):
    a = SocialCopyTemplate(category="spicy", surface="x_buffer", body="a {spicy}", use_count=2, sort_order=0)
    b = SocialCopyTemplate(category="spicy", surface="x_buffer", body="b {spicy}", use_count=0, sort_order=1)
    db.add_all([a, b])
    db.commit()
    picked = pick_social_copy_template(db, category="spicy")
    assert picked.body.startswith("b")
