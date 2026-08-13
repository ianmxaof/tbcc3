"""Companion unit economics — unknown cost basis, breakeven, below-cost alarm."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.models.income_entry import IncomeEntry
from app.services.companion_cogs import (
    breakeven_stars_per_photo,
    companion_margin_summary,
    companion_unit_economics,
    cost_basis_known,
    estimated_trial_burn_usd,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "TBCC_COMPANION_UNDRESS_USD_PER_CREDIT",
        "TBCC_COMPANION_UNDRESS_CREDITS_PER_PHOTO",
        "TBCC_STARS_PLATFORM_FEE_PCT",
        "TBCC_STARS_USD_PER_STAR",
        "TBCC_COMPANION_STARS_PER_PHOTO",
    ):
        monkeypatch.delenv(key, raising=False)


def test_cost_basis_unknown_by_default():
    assert cost_basis_known() is False
    unit = companion_unit_economics()
    assert unit["cogs_usd_per_photo"] is None
    assert unit["margin_pct"] is None
    assert unit["below_cost"] is False
    assert "TBCC_COMPANION_UNDRESS_USD_PER_CREDIT" in unit["action"]


def test_gross_uses_star_rate():
    unit = companion_unit_economics()
    # 25 stars * $0.012
    assert unit["stars_per_photo"] == 25
    assert unit["gross_usd_per_photo"] == 0.3
    assert unit["net_revenue_usd_per_photo"] == 0.3


def test_platform_fee_reduces_net(monkeypatch):
    monkeypatch.setenv("TBCC_STARS_PLATFORM_FEE_PCT", "30")
    unit = companion_unit_economics()
    assert unit["net_revenue_usd_per_photo"] == 0.21


def test_profitable_configuration(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_UNDRESS_USD_PER_CREDIT", "0.05")
    unit = companion_unit_economics()
    assert unit["cost_basis_known"] is True
    assert unit["cogs_usd_per_photo"] == 0.05
    assert unit["contribution_usd_per_photo"] == 0.25
    assert unit["margin_pct"] == 83.3
    assert unit["below_cost"] is False


def test_below_cost_raises_alarm_and_names_breakeven(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_UNDRESS_USD_PER_CREDIT", "0.20")
    monkeypatch.setenv("TBCC_COMPANION_UNDRESS_CREDITS_PER_PHOTO", "3")
    unit = companion_unit_economics()
    # $0.60 of API burn against $0.30 of revenue.
    assert unit["cogs_usd_per_photo"] == 0.6
    assert unit["below_cost"] is True
    assert unit["contribution_usd_per_photo"] == -0.3
    assert breakeven_stars_per_photo() == 50
    assert "50" in unit["action"]


def test_breakeven_zero_without_cost_basis():
    assert breakeven_stars_per_photo() == 0


def test_breakeven_accounts_for_platform_fee(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_UNDRESS_USD_PER_CREDIT", "0.12")
    assert breakeven_stars_per_photo() == 10
    monkeypatch.setenv("TBCC_STARS_PLATFORM_FEE_PCT", "50")
    assert breakeven_stars_per_photo() == 20


def test_estimated_trial_burn(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_UNDRESS_USD_PER_CREDIT", "0.05")
    assert estimated_trial_burn_usd(100) == 5.0
    assert estimated_trial_burn_usd(0) == 0.0


def test_margin_summary_from_ledger(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_UNDRESS_USD_PER_CREDIT", "0.05")
    db = MagicMock()
    rows = [
        IncomeEntry(
            idempotency_key=f"c{i}",
            source="companion_stars",
            amount_minor=25,
            currency="XTR",
            amount_usd_cents=30,
            created_at=datetime.utcnow(),
        )
        for i in range(4)
    ]
    db.query.return_value.filter.return_value.all.return_value = rows

    out = companion_margin_summary(db, days=30)
    assert out["photos_sold"] == 4
    assert out["stars_collected"] == 100
    assert out["gross_usd"] == 1.2
    assert out["estimated_cogs_usd"] == 0.2
    assert out["estimated_contribution_usd"] == 1.0
    assert out["cost_basis_known"] is True
    assert out["trial_burn_measured"] is False


def test_margin_summary_without_cost_basis():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    out = companion_margin_summary(db, days=30)
    assert out["photos_sold"] == 0
    assert out["estimated_cogs_usd"] is None
    assert out["estimated_contribution_usd"] is None
    assert out["cost_basis_known"] is False
