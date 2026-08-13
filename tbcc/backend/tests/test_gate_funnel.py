"""Gate funnel — source_ref join across beacon clicks, touches and revenue."""

from datetime import datetime
from unittest.mock import MagicMock

from app.models.click_link import ClickLink, ClickLinkHit
from app.models.user_funnel_touch import UserFunnelTouch
from app.services.click_beacon import derive_source_ref
from app.services.gate_funnel import gate_funnel_report


def test_derive_source_ref_from_destination():
    assert (
        derive_source_ref("https://telegram.me/aof_lootgod_bot?start=src_lv_loot_wk31")
        == "src_lv_loot_wk31"
    )
    assert derive_source_ref("https://telegram.me/+abc123") is None
    assert derive_source_ref("") is None


def _wire(db, *, links, hits, touches, revenue_rows, monkeypatch):
    def _query(model):
        q = MagicMock()
        if model is ClickLink:
            q.filter.return_value.all.return_value = links
        elif model is ClickLinkHit:
            q.filter.return_value.all.return_value = hits
        elif model is UserFunnelTouch:
            q.filter.return_value.all.return_value = touches
        return q

    db.query.side_effect = _query
    monkeypatch.setattr(
        "app.services.traffic_attribution.revenue_by_source",
        lambda _db, days=30: {"revenue_by_source": revenue_rows},
    )


def test_gate_funnel_joins_clicks_touches_revenue(monkeypatch):
    db = MagicMock()
    link = ClickLink(
        id=1,
        slug="wk31-lv-loot",
        source_ref="src_lv_loot_wk31",
        destination_url="https://telegram.me/aof_lootgod_bot?start=src_lv_loot_wk31",
    )
    hits = [
        ClickLinkHit(link_id=1, user_agent="Mozilla/5.0", country="US", created_at=datetime.utcnow()),
        ClickLinkHit(link_id=1, user_agent="Mozilla/5.0", country="US", created_at=datetime.utcnow()),
        ClickLinkHit(link_id=1, user_agent="Mozilla/5.0", country="DE", created_at=datetime.utcnow()),
        # Crawler must not count as a click.
        ClickLinkHit(link_id=1, user_agent="TelegramBot (like TwitterBot)", created_at=datetime.utcnow()),
    ]
    touches = [
        UserFunnelTouch(telegram_user_id=1, first_source_ref="src_lv_loot_wk31", first_seen_at=datetime.utcnow()),
    ]
    _wire(
        db,
        links=[link],
        hits=hits,
        touches=touches,
        revenue_rows=[{"source_ref": "src_lv_loot_wk31", "usd_cents": 1800}],
        monkeypatch=monkeypatch,
    )

    out = gate_funnel_report(db, days=30)
    row = out["gate_funnel"][0]

    assert row["source_ref"] == "src_lv_loot_wk31"
    assert row["clicks"] == 3
    assert row["bot_clicks"] == 1
    assert row["touches"] == 1
    assert row["revenue_usd"] == 18.0
    assert row["click_to_touch_pct"] == 33.3
    assert row["usd_per_1k_clicks"] == 6000.0
    assert row["usd_per_touch"] == 18.0
    assert row["top_countries"][0] == {"country": "US", "clicks": 2}
    assert row["expects_touch"] is True
    assert out["totals"]["clicks"] == 3
    assert out["totals"]["bot_clicks"] == 1


def test_gate_funnel_flags_clicks_without_touches(monkeypatch):
    db = MagicMock()
    link = ClickLink(
        id=2,
        slug="wk31-lv-ass",
        source_ref="src_lv_ass_wk31",
        destination_url="https://telegram.me/aof_lootgod_bot?start=src_lv_ass_wk31",
    )
    hits = [ClickLinkHit(link_id=2, user_agent="Mozilla/5.0", created_at=datetime.utcnow())]
    _wire(db, links=[link], hits=hits, touches=[], revenue_rows=[], monkeypatch=monkeypatch)

    out = gate_funnel_report(db, days=30)
    assert out["clicks_without_touches"] == ["src_lv_ass_wk31"]
    assert out["gate_funnel"][0]["click_to_touch_pct"] == 0.0
    assert out["gate_funnel"][0]["expects_touch"] is True


def test_gate_funnel_affiliate_outbound_excluded_from_broken_list(monkeypatch):
    """P9/P10: web-vpapi-*/web-live-* beacons point off-Telegram and can never
    produce a touch by design — they must not be flagged as broken."""
    db = MagicMock()
    link = ClickLink(
        id=3,
        slug="web-vpapi-big-tits",
        source_ref="src_web_vpapi_big_tits",
        destination_url="https://www.awempire.com/",
    )
    hits = [ClickLinkHit(link_id=3, user_agent="Mozilla/5.0", created_at=datetime.utcnow())]
    _wire(db, links=[link], hits=hits, touches=[], revenue_rows=[], monkeypatch=monkeypatch)

    out = gate_funnel_report(db, days=30)
    row = out["gate_funnel"][0]
    assert row["source_ref"] == "src_web_vpapi_big_tits"
    assert row["clicks"] == 1
    assert row["touches"] == 0
    assert row["expects_touch"] is False
    # The whole point: present in the row data (so a dashboard can label it),
    # absent from the "broken" list.
    assert out["clicks_without_touches"] == []


def test_gate_funnel_bare_bot_link_excluded_from_broken_list(monkeypatch):
    """Boundary case: a Telegram destination with no ?start= payload (e.g.
    web-vip -> https://t.me/aofsubscriptions_bot) is on-Telegram but still
    structurally cannot produce a touch — same treatment as an affiliate
    link, for a different reason. Must not be flagged as broken either."""
    db = MagicMock()
    link = ClickLink(
        id=4,
        slug="web-vip",
        source_ref="src_web_hub_vip",
        destination_url="https://t.me/aofsubscriptions_bot",
    )
    hits = [ClickLinkHit(link_id=4, user_agent="Mozilla/5.0", created_at=datetime.utcnow())]
    _wire(db, links=[link], hits=hits, touches=[], revenue_rows=[], monkeypatch=monkeypatch)

    out = gate_funnel_report(db, days=30)
    row = out["gate_funnel"][0]
    assert row["expects_touch"] is False
    assert out["clicks_without_touches"] == []


def test_gate_funnel_flags_unbeaconed_earning_refs(monkeypatch):
    db = MagicMock()
    _wire(
        db,
        links=[],
        hits=[],
        touches=[],
        revenue_rows=[{"source_ref": "src_bait_vip", "usd_cents": 500}],
        monkeypatch=monkeypatch,
    )

    out = gate_funnel_report(db, days=30)
    assert out["unbeaconed_earning_refs"] == ["src_bait_vip"]
    assert out["totals"]["beaconed_source_refs"] == 0


def test_gate_funnel_empty(monkeypatch):
    db = MagicMock()
    _wire(db, links=[], hits=[], touches=[], revenue_rows=[], monkeypatch=monkeypatch)
    out = gate_funnel_report(db, days=7)
    assert out["gate_funnel"] == []
    assert out["totals"]["click_to_touch_pct"] is None
