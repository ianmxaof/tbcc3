"""Tests for promo affiliate rotation."""

from __future__ import annotations

import json

from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.promo_affiliate_rotation import (
    build_sponsor_link_html,
    list_candidates,
    pick_affiliate,
    preview_affiliates,
    row_placements,
)


def _add_row(
    db,
    *,
    label: str,
    url: str,
    placements: list[str],
    network_keys: list[str] | None = None,
    priority: int = 10,
):
    row = PromoAffiliateLink(
        label=label,
        url=url,
        payout_kind="other",
        priority_tier=priority,
        active=True,
        placements_json=json.dumps(placements),
        network_keys_json=json.dumps(network_keys or []),
        copy_template="💰 {link}",
    )
    db.add(row)
    db.flush()
    return row


def test_row_placements_defaults_manual_only(db):
    row = PromoAffiliateLink(label="x", url="https://example.com/a")
    assert row_placements(row) == ["manual_only"]


def test_list_candidates_filters_placement_and_network(db):
    _add_row(
        db,
        label="Musebox",
        url="https://musebox.ai/?ref=test",
        placements=["telegram_footer", "x_buffer"],
        network_keys=["ai"],
        priority=1,
    )
    _add_row(
        db,
        label="Manual",
        url="https://example.com/manual",
        placements=["manual_only"],
        priority=2,
    )
    ai_rows = list_candidates(db, "telegram_footer", network_key="ai")
    assert len(ai_rows) == 1
    assert ai_rows[0].label == "Musebox"
    assert list_candidates(db, "telegram_footer", network_key="bop") == []


def test_pick_affiliate_round_robin(db):
    _add_row(db, label="A", url="https://a.test/1", placements=["x_buffer"], priority=1)
    _add_row(db, label="B", url="https://b.test/1", placements=["x_buffer"], priority=2)
    first = pick_affiliate(db, "x_buffer", advance=True)
    second = pick_affiliate(db, "x_buffer", advance=True)
    third = pick_affiliate(db, "x_buffer", advance=False)
    assert first and second and third
    assert first.row.label == "A"
    assert second.row.label == "B"
    assert third.row.label == "A"


def test_build_sponsor_link_html(db):
    row = _add_row(
        db,
        label="Musebox",
        url="https://musebox.ai/?ref=x",
        placements=["links_hub"],
    )
    html = build_sponsor_link_html(row)
    assert "musebox.ai" in html
    assert "href=" in html


def test_preview_affiliates_order(db):
    _add_row(db, label="A", url="https://a.test/2", placements=["links_hub"], priority=1)
    _add_row(db, label="B", url="https://b.test/2", placements=["links_hub"], priority=2)
    picks = preview_affiliates(db, "links_hub", count=2)
    assert [p["label"] for p in picks] == ["A", "B"]
