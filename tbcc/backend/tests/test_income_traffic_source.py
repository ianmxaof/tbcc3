"""Income ledger traffic attribution — source ref stamping and revenue rollup."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.models.income_entry import IncomeEntry
from app.services.income_ledger import (
    SOURCE_COMPANION_STARS,
    SOURCE_LINKVERTISE,
    SOURCE_SUBSCRIPTION_STARS,
    _resolve_traffic_source_ref,
)
from app.services.traffic_attribution import revenue_by_source


def _entry(source: str, usd_cents: int, *, ref: str | None, currency: str = "USD", minor: int | None = None):
    return IncomeEntry(
        idempotency_key=f"k{usd_cents}{source}{ref}",
        source=source,
        amount_minor=minor if minor is not None else usd_cents,
        currency=currency,
        amount_usd_cents=usd_cents,
        traffic_source_ref=ref,
        created_at=datetime.utcnow(),
    )


def test_resolve_traffic_source_ref_prefers_explicit():
    db = MagicMock()
    assert _resolve_traffic_source_ref(db, telegram_user_id=5, explicit="src_lv_ass_wk31") == "src_lv_ass_wk31"
    db.query.assert_not_called()


def test_resolve_traffic_source_ref_falls_back_to_touch(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.traffic_attribution.resolve_attribution_for_user",
        lambda _db, _uid: {"traffic_source_ref": "src_bait_loot", "traffic_entry_payload": "bait_loot"},
    )
    assert _resolve_traffic_source_ref(db, telegram_user_id=5, explicit=None) == "src_bait_loot"


def test_resolve_traffic_source_ref_none_without_user():
    db = MagicMock()
    assert _resolve_traffic_source_ref(db, telegram_user_id=None, explicit=None) is None


def test_revenue_by_source_spans_all_skus():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        _entry(SOURCE_SUBSCRIPTION_STARS, 1800, ref="src_lv_ass_wk31", currency="XTR", minor=1500),
        _entry(SOURCE_COMPANION_STARS, 30, ref="src_lv_ass_wk31", currency="XTR", minor=25),
        _entry(SOURCE_LINKVERTISE, 500, ref="src_lv_ass_wk31"),
        _entry(SOURCE_SUBSCRIPTION_STARS, 600, ref="src_bait_vip", currency="XTR", minor=500),
        _entry(SOURCE_LINKVERTISE, 900, ref=None),
    ]

    out = revenue_by_source(db, days=30)
    rows = out["revenue_by_source"]

    assert len(rows) == 2
    top = rows[0]
    assert top["source_ref"] == "src_lv_ass_wk31"
    # Subscription + companion + gate revshare all roll into one lane.
    assert top["usd_cents"] == 2330
    assert top["stars"] == 1525
    assert top["entries"] == 3
    assert {s["source"] for s in top["by_income_source"]} == {
        SOURCE_SUBSCRIPTION_STARS,
        SOURCE_COMPANION_STARS,
        SOURCE_LINKVERTISE,
    }

    assert out["unattributed_usd"] == 9.0
    assert out["unattributed_entries"] == 1
    assert out["total_usd"] == 38.3
    assert out["attributed_revenue_pct"] == 76.5


def test_revenue_by_source_empty_ledger():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    out = revenue_by_source(db, days=7)
    assert out["revenue_by_source"] == []
    assert out["attributed_revenue_pct"] == 0.0
    assert out["total_usd"] == 0.0
