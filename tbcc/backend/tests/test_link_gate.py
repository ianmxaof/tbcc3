"""Tests for link gate unwrap + provider helpers."""

from __future__ import annotations

from app.services.link_gate_provider import (
    _admaven_link_from_response,
    is_gate_host,
    pick_gate_provider,
    wrap_linkvertise_url,
)
from app.services.link_gate_unwrap import (
    linkvertise_publisher_id_from_url,
    unwrap_linkvertise_dynamic,
)


def test_unwrap_linkvertise_dynamic_roundtrip() -> None:
    dest = "https://t.me/+hMQzGsBFjF02MDkx"
    wrapped = wrap_linkvertise_url(1367336, dest)
    assert unwrap_linkvertise_dynamic(wrapped) == dest


def test_linkvertise_publisher_id_from_path() -> None:
    url = "https://link-center.net/1367336/irj3uxd3iYFV"
    assert linkvertise_publisher_id_from_url(url) == "1367336"


def test_is_gate_host() -> None:
    assert is_gate_host("https://link-center.net/1367336/foo")
    assert is_gate_host("https://work.ink/abc/test")
    assert is_gate_host("https://speedy-links.com/s?hUqNoHb6")
    assert not is_gate_host("https://t.me/+abc")


def test_admaven_link_from_response() -> None:
    listed = {
        "type": "created",
        "message": [
            {
                "short": "hUqNoHb6",
                "full_short": "https://speedy-links.com/s?hUqNoHb6",
                "destination_url": "https://t.me/+test",
            }
        ],
    }
    assert _admaven_link_from_response(listed) == "https://speedy-links.com/s?hUqNoHb6"
    documented = {
        "type": "created",
        "message": {
            "title": "AOF",
            "url": "https://t.me/+test",
            "short": "abcd",
            "desturl": "https://onepiecered.co/s?abcd",
        },
    }
    assert _admaven_link_from_response(documented) == "https://onepiecered.co/s?abcd"


def test_pick_gate_provider_first_prefers_admaven(monkeypatch) -> None:
    import os

    monkeypatch.setenv("TBCC_ADMAVEN_API_TOKEN", "test-token")
    monkeypatch.setenv("TBCC_LINKVERTISE_PUBLISHER_ID", "1367336")
    monkeypatch.setenv("TBCC_WORKINK_BASE_LINK", "https://work.ink/test/slug")
    monkeypatch.setenv("TBCC_LINK_GATE_PROVIDERS", "admaven,workink,linkvertise")
    monkeypatch.setenv("TBCC_LINK_GATE_ROTATION", "first")
    assert pick_gate_provider(seed="https://t.me/+seed") == "admaven"


def test_pick_gate_provider_seeded_stable(monkeypatch=None) -> None:
    import os

    os.environ["TBCC_LINKVERTISE_PUBLISHER_ID"] = "1367336"
    os.environ["TBCC_LINK_GATE_PROVIDERS"] = "linkvertise"
    a = pick_gate_provider(seed="https://t.me/+test")
    b = pick_gate_provider(seed="https://t.me/+test")
    assert a == b
