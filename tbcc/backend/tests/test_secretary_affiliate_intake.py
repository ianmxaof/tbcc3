"""Secretary affiliate sponsor intake helpers."""

from __future__ import annotations

from app.services.secretary_affiliate_intake import (
    intake_affiliate_sponsor,
    label_from_url,
    parse_affiliate_intake_text,
)


def test_label_from_url_cometapi():
    assert label_from_url("https://www.cometapi.com/console/login?aff=ogsT") == "Cometapi"


def test_parse_bare_url():
    parsed = parse_affiliate_intake_text("https://www.cometapi.com/console/login?aff=ogsT")
    assert parsed is not None
    label, url = parsed
    assert url.startswith("https://www.cometapi.com")
    assert label == "Cometapi"


def test_parse_label_pipe_url():
    parsed = parse_affiliate_intake_text("Comet API|https://www.cometapi.com/?aff=x")
    assert parsed == ("Comet API", "https://www.cometapi.com/?aff=x")


def test_intake_creates_and_syncs(db, monkeypatch):
    sync_calls: list[bool] = []

    def _fake_sync(_db, *, execute=True):
        sync_calls.append(execute)
        return {"ok": True, "channels": []}

    monkeypatch.setattr(
        "app.services.secretary_affiliate_intake.sync_affiliate_network",
        _fake_sync,
    )
    result = intake_affiliate_sponsor(
        db,
        label="Comet API",
        url="https://www.cometapi.com/console/login?aff=ogsT",
        sync=True,
    )
    assert result.ok is True
    assert result.created is True
    assert result.link_id is not None
    assert sync_calls == [True]

    result2 = intake_affiliate_sponsor(
        db,
        label="Comet API",
        url="https://www.cometapi.com/console/login?aff=ogsT",
        sync=False,
    )
    assert result2.ok is True
    assert result2.created is False
