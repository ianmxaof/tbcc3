"""Traffic beacon secretary message formatting."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.admin_inbox import _format_event_body_html
from app.services.traffic_beacon_notify import (
    format_traffic_beacon_body_html,
    parse_beacon_placement,
    placement_hub_url,
)


def test_parse_beacon_placement_from_label():
    assert parse_beacon_placement(label="DrawAI · x_buffer", slug="aff-drawai-x-buffer") == "x_buffer"
    assert parse_beacon_placement(label="Hot Dreams Bot · loot_roll", slug=None) == "loot_roll"


def test_parse_beacon_placement_from_slug():
    assert parse_beacon_placement(label="", slug="aff-satisfactory-r-x-buffer") == "x_buffer"


def test_placement_hub_url_x_buffer():
    assert placement_hub_url("x_buffer") == "https://publish.buffer.com/"


def test_placement_hub_url_loot_roll():
    assert "aof_lootgod_bot" in (placement_hub_url("loot_roll") or "")


def test_format_traffic_beacon_body_html_includes_links():
    html_out = format_traffic_beacon_body_html(
        {
            "slug": "aff-drawai-x-buffer",
            "hit_count": 3,
            "link_label": "DrawAI · x_buffer",
            "placement": "x_buffer",
            "destination_url": "https://t.me/luciddreams?start=foo",
            "beacon_url": "https://api.powercore.app/r/aff-drawai-x-buffer",
            "referer": "https://t.co/abc",
            "ip": "1.2.3.4",
            "country": "US",
            "source_ref": "src_aff_drawai_x_buffer",
        }
    )
    assert "aff-drawai-x-buffer" in html_out
    assert 'href="https://t.me/luciddreams' in html_out
    assert 'href="https://api.powercore.app/r/aff-drawai-x-buffer"' in html_out
    assert 'href="https://publish.buffer.com/"' in html_out
    assert 'href="https://t.co/abc"' in html_out
    assert "1.2.3.4" in html_out


def test_admin_inbox_traffic_beacon_formatter():
    body = _format_event_body_html(
        {
            "category": "traffic",
            "body": "slug=old hits=1",
            "meta": {
                "pulse_event_type": "beacon",
                "slug": "aff-hot-dreams-bot-x-buffer",
                "hit_count": 2,
                "link_label": "Hot Dreams Bot · x_buffer",
                "placement": "x_buffer",
                "destination_url": "https://t.me/HotDreamsBot?start=1",
                "beacon_url": "https://api.powercore.app/r/aff-hot-dreams-bot-x-buffer",
            },
        }
    )
    assert "Hot Dreams" not in body  # label is in title not body
    assert "aff-hot-dreams-bot-x-buffer" in body
    assert 'href="https://t.me/HotDreamsBot' in body


def test_beacon_pulse_meta_from_orm_shapes():
    from app.services.traffic_beacon_notify import beacon_pulse_meta

    link = MagicMock()
    link.label = "Satisfactory (Randi123) · x_buffer"
    link.slug = "aff-satisfactory-r-x-buffer"
    link.source_ref = "src_aff_satisfactory_r_x_buffer"
    link.hit_count = 4
    link.destination_url = "https://satisfactory.studio/r/ref_7787282561"

    hit = MagicMock()
    hit.referer = "https://x.com/user/status/123"
    hit.ip = "9.9.9.9"
    hit.country = "US"
    hit.campaign_id = None
    hit.user_agent = "Mozilla/5.0"

    meta = beacon_pulse_meta(link, hit)
    assert meta["placement"] == "x_buffer"
    assert meta["beacon_url"].endswith("/r/aff-satisfactory-r-x-buffer")
    assert meta["referer"].startswith("https://x.com/")
