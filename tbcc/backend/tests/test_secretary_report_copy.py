"""Secretary operator report copy — human source_refs + Telegram HTML."""

from __future__ import annotations

from app.services.secretary_report_copy import (
    format_draft_fail_html,
    format_flywheel_card_html,
    format_heuristic_brief_html,
    format_pulse_digest_html,
    format_surge_card_html,
    humanize_pulse_kind,
    humanize_source_ref,
)


def test_humanize_affiliate_footer_refs():
    row = humanize_source_ref("src_aff_undress_ai_bot_telegram_footer")
    assert row["label"] == "Undress AI"
    assert "footer" in row["surface"].lower()
    assert "src_aff" not in row["display"]

    honey = humanize_source_ref("src_aff_honeypot_telegram_footer")
    assert honey["label"] == "Honeypot"

    goblin = humanize_source_ref("src_aff_loot_goblin_channel_fomo_telegram_footer")
    assert "Loot Goblin" in goblin["label"]


def test_pulse_digest_is_plain_language_not_raw_keys():
    html = format_pulse_digest_html(
        {"affiliate_served": 4, "post_ok": 1},
        {
            "src_aff_undress_ai_bot_telegram_footer": 1,
            "src_aff_honeypot_telegram_footer": 1,
        },
    )
    assert html is not None
    assert "affiliate_served" not in html
    assert "Top source_ref" not in html
    assert "sponsor" in html.lower()
    assert "Undress AI" in html
    assert "Honeypot" in html
    assert "<blockquote>" in html
    assert "<u>" in html
    assert "Do this now" in html
    assert "&lt;" not in html


def test_pulse_kind_human():
    assert "sponsor" in humanize_pulse_kind("affiliate_served")
    assert "failed" in humanize_pulse_kind("post_fail")


def test_heuristic_brief_uses_numbers_and_actions():
    html = format_heuristic_brief_html(
        {
            "income_usd": 0,
            "income_stars": 0,
            "companion_photos_sold": 0,
            "blockers": [
                {
                    "id": "revenue_stall",
                    "what": "No new ledger income since 2026-07-01",
                    "why": "Ops cost continues without conversion.",
                }
            ],
            "undress_spike": {},
            "growth_proposals": [],
        }
    )
    assert "Daily revenue brief" in html
    assert "$0.00" in html
    assert "Companion photos sold" in html
    assert "No new ledger income" in html
    assert "<blockquote>" in html
    assert "/loot" in html or "VIP" in html
    assert "&lt;b&gt;" not in html


def test_draft_fail_quotes_customer():
    html = format_draft_fail_html(who="Ethan_90", customer_text="Can you buy links?")
    assert "Ethan_90" in html
    assert "Can you buy links?" in html
    assert "<blockquote>" in html
    assert "silence" in html.lower()
    assert "/config" in html


def test_surge_card_has_read_and_action():
    html = format_surge_card_html(
        state={"hits_in_window": 12, "threshold": 8, "spike_active": True},
        result={"ok": True, "queued": ["job-1"]},
    )
    assert "Undress surge" in html
    assert "12/8" in html
    assert "<blockquote>" in html
    assert "/inbox" in html
    assert "&lt;" not in html


def test_flywheel_card_pending_asks_approve():
    html = format_flywheel_card_html(
        status={"enabled": True, "approval": True, "registry_codes": ["restart"]},
        pending=[{"id": "fw1", "code": "restart_worker", "label": "Restart celery"}],
    )
    assert "Ops flywheel" in html
    assert "restart_worker" in html
    assert "Approve" in html
    assert "<blockquote>" in html
