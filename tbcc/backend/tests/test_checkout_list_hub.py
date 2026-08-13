"""Checkout List (@thecheckoutlist) bulletin builder."""

from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.checkout_list_hub import build_checkout_list_bulletin, sync_checkout_list_hub


def _row(label: str, url: str) -> PromoAffiliateLink:
    return PromoAffiliateLink(
        label=label,
        url=url,
        payout_kind="other",
        active=True,
        placements_json='["links_hub_sfw"]',
        copy_template="🛒 {link}",
    )


def test_build_checkout_list_bulletin_groups_categories(db):
    db.add(_row("Cursor referral", "https://cursor.com/referral?code=x"))
    db.add(_row("Rakuten", "https://www.rakuten.com/r/IANMPO3"))
    db.commit()

    html = build_checkout_list_bulletin(db)
    assert "THE CHECKOUT LIST" in html
    assert "DEV & PRODUCTIVITY" in html
    assert "SHOPPING" in html
    assert "cursor.com" in html
    assert "rakuten.com" in html
    assert "temu" not in html.lower()


def test_sync_checkout_list_hub_creates_scheduler(db, monkeypatch):
    monkeypatch.setenv("TBCC_CHECKOUT_LIST_CHANNEL_IDENT", "-1004361597444")
    report = sync_checkout_list_hub(db, execute=True)
    assert report.get("ok") is True
    assert report.get("scheduler_id")
    assert report.get("channel_id")
