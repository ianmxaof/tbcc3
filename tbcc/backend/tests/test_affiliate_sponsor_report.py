"""Affiliate sponsor admin report for secretary /sponsors."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models.click_link import ClickLink
from app.models.income_entry import IncomeEntry
from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.affiliate_sponsor_report import (
    build_affiliate_sponsor_report,
    collect_affiliate_sponsor_rows,
    format_affiliate_sponsor_report_html,
)


def test_collect_rows_with_clicks_and_revenue(db):
    row = PromoAffiliateLink(
        label="Cloud Farm Wallet",
        url="https://t.me/CloudFarmWalletBot/cloud?startapp=7787282561",
        payout_kind="cpa",
        payout_detail="usd_cash",
        priority_tier=0,
        active=True,
        placements_json='["x_buffer","links_hub_sfw"]',
        copy_template="☁️ {link} — $2 USDT per referral",
    )
    db.add(row)
    db.flush()

    beacon = ClickLink(
        slug="aff-cloud-farm-wall-x-buffer",
        destination_url=row.url,
        label="Cloud Farm Wallet · x_buffer",
        source_ref="src_aff_cloud_farm_wallet_x_buffer",
        active=1,
        hit_count=42,
    )
    db.add(beacon)
    db.add(
        IncomeEntry(
            idempotency_key="test-cloud-farm-1",
            source="external_affiliate",
            amount_usd_cents=200,
            currency="USD",
            amount_minor=0,
            traffic_source_ref="src_aff_cloud_farm_wallet_x_buffer",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db.commit()

    rows = collect_affiliate_sponsor_rows(db, revenue_days=30)
    assert len(rows) >= 1
    cloud = next(r for r in rows if r["label"] == "Cloud Farm Wallet")
    assert cloud["clicks"] == 42
    assert cloud["url"].startswith("https://t.me/CloudFarmWalletBot")
    assert cloud["priority_tier"] == 0
    assert cloud["payout_rail"] == "cash"
    assert cloud["attributed_usd"] == 2.0
    assert "links_hub_sfw" in cloud["placements"]

    report = build_affiliate_sponsor_report(db, revenue_days=30)
    assert report["ok"] is True
    assert report["count"] >= 1
    assert any("Cloud Farm" in m for m in report["messages"])
    assert any("42" in m for m in report["messages"])


def test_format_chunks_include_disclaimer():
    rows = [
        {
            "id": 1,
            "label": "Demo",
            "url": "https://example.com/r",
            "short_url": None,
            "active": True,
            "priority_tier": 1,
            "payout_kind": "cpa",
            "payout_detail": "usd_cash",
            "payout_rail": "cash",
            "placements": ["x_buffer"],
            "network_keys": [],
            "copy_template": None,
            "expires_at": None,
            "clicks": 3,
            "beacon_links": [],
            "attributed_usd": 0.0,
            "attributed_usd_cents": 0,
            "attributed_entries": 0,
            "attributed_source_refs": [],
            "revenue_days": 30,
        }
    ]
    msgs = format_affiliate_sponsor_report_html(rows)
    assert msgs
    assert "not the affiliate program" in msgs[0].lower() or "dashboard" in msgs[0].lower()
    assert "Demo" in msgs[0]
