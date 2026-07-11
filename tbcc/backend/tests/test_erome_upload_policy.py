"""Tests for Erome upload policy + analytics sidecar."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.services import erome_upload_policy as policy
from app.services.erome_upload_analytics import merge_sidecar_params, read_erome_sidecar, EromeUploadParams


def test_scan_title_tos_detects_tme():
    issues = policy.scan_title_for_tos("t.me/aof_lootgod_bot teaser pack")
    assert "tos_advertising:telegram_link_in_title" in issues


def test_policy_blocks_promo_description():
    verdict = policy.check_upload_policy(
        title="Neutral teaser title",
        description="Full pack on https://t.me/+hub",
        file_count=1,
        tags=["milf"],
    )
    assert not verdict.allowed
    assert any("tos_advertising" in b for b in verdict.blocks)


def test_scan_title_spam_detects_handles():
    issues = policy.scan_title_for_spam("20260627 - @AOF_LOOT")
    assert any("spam_pattern" in i for i in issues)


def test_scan_title_clean_taboo_title():
    issues = policy.scan_title_for_spam("Vietnamese MILF jiggly big boobs ready for sex")
    assert "title_all_caps" not in issues
    assert not any("@AOF" in i for i in issues)


def test_policy_blocks_duplicate_title(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "ledger_path", lambda: tmp_path / "ledger.jsonl")
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "ok": True,
                "published_at": datetime.now(timezone.utc).isoformat(),
                "title": "Same Title",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TBCC_EROME_MIN_INTERVAL_MINUTES", "0")
    monkeypatch.setenv("TBCC_EROME_MAX_UPLOADS_PER_DAY", "50")
    verdict = policy.check_upload_policy(title="Same Title", file_count=1, tags=["milf"])
    assert not verdict.allowed
    assert "duplicate_title" in verdict.blocks


def test_policy_force_bypasses_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "ledger_path", lambda: tmp_path / "ledger.jsonl")
    (tmp_path / "ledger.jsonl").write_text(
        json.dumps({"ok": True, "published_at": "2026-06-28T12:00:00Z", "title": "Dup"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TBCC_EROME_MIN_INTERVAL_MINUTES", "0")
    verdict = policy.check_upload_policy(title="Dup", file_count=1, force=True)
    assert verdict.allowed


def test_read_erome_sidecar(tmp_path):
    side = tmp_path / "erome.params.json"
    side.write_text(
        json.dumps({"title": "Teaser", "tags": ["milf", "webcam"], "network_key": "milf"}),
        encoding="utf-8",
    )
    data = read_erome_sidecar(tmp_path)
    assert data["title"] == "Teaser"
    assert "milf" in data["tags"]


def test_parse_erome_caption_tags_line():
    from app.services.erome_upload_analytics import parse_erome_caption

    title, tags, desc = parse_erome_caption(
        "Vietnamese MILF jiggly big boobs\n"
        "tags: milf, webcam, big tits\n"
        "trimmed ~2min camshow"
    )
    assert title.startswith("Vietnamese")
    assert "milf" in tags
    assert desc and "camshow" in desc


def test_merge_sidecar_params(tmp_path):
    side = tmp_path / "erome.params.json"
    side.write_text(json.dumps({"title": "From sidecar", "tags": "big tits, latina"}), encoding="utf-8")
    merged = merge_sidecar_params(
        tmp_path,
        EromeUploadParams(title="CLI title", source="cli", file_count=1),
    )
    assert merged.title == "From sidecar"
    assert "big tits" in merged.tags
