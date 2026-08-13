"""Tests for Storage Hub lane manual HTML + targets."""

from app.services.storage_hub_lane_manual import (
    format_lane_manual_html,
    lane_manual_targets,
)


def test_format_lane_manual_html_escapes_title():
    html = format_lane_manual_html(topic_title="AOF MILF/GILF STORAGE", network_key="milf_gilf")
    assert "MILF/GILF" in html
    assert "<b>Topic:</b> AOF MILF/GILF STORAGE" in html
    assert "<code>milf_gilf</code>" in html
    assert "📖 Storage Hub" in html


def test_format_lane_manual_qa_master():
    html = format_lane_manual_html(
        topic_title="Q&A | APPROVE / DENY | INTAKE",
        network_key="qa_master",
    )
    assert "Fleet control (you are here)" in html
    assert "/qapanel" in html


def test_lane_manual_targets_include_content_lanes():
    targets = lane_manual_targets()
    keys = {t.get("network_key") for t in targets}
    assert "milf_gilf" in keys or len(keys) >= 5
    assert "qa_master" in keys
    assert "inbox" in keys
    # Forum topics only — no shortcut channel chat id
    assert all(t.get("message_thread_id") is not None for t in targets)
