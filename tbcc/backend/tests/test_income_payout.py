"""Tests for income payout ledger entries."""

from app.database.session import SessionLocal
from app.models.income_entry import IncomeEntry
from app.services.income_ledger import income_summary, record_income_payout, record_manual_income


def test_payout_reduces_net_external(db):
    record_manual_income(db, source="linkvertise", amount_usd=16.0, period_key="test-earned")
    record_income_payout(db, source="linkvertise", amount_usd=16.0, notes="test bank")
    db.commit()

    summary = income_summary(db, days=None, backfill=False)
    assert summary["totals"]["gross_usd"] >= 16.0
    assert summary["totals"]["payouts_usd"] >= 16.0

    payouts = db.query(IncomeEntry).filter(IncomeEntry.sync_kind == "payout").all()
    assert len(payouts) == 1
    assert int(payouts[0].amount_usd_cents) < 0
