"""Tests for Erome private-staging governance queue."""

from __future__ import annotations

import json

from app.services import erome_upload_governance as gov
from app.services.erome_upload_analytics import EromeUploadParams, merge_sidecar_params, record_erome_upload
from app.services.erome_upload_policy import append_ledger_row


def _patch_ledger(monkeypatch, tmp_path):
    ledger = tmp_path / "upload_ledger.jsonl"
    monkeypatch.setattr("app.services.erome_upload_policy.ledger_path", lambda: ledger)
    monkeypatch.setattr(gov, "ledger_path", lambda: ledger)
    return ledger


def test_default_visibility_private(monkeypatch):
    monkeypatch.delenv("TBCC_EROME_DEFAULT_VISIBILITY", raising=False)
    assert gov.default_upload_visibility() == "private"
    monkeypatch.setenv("TBCC_EROME_DEFAULT_VISIBILITY", "public")
    assert gov.default_upload_visibility() == "public"


def test_list_pending_and_mark_approved(monkeypatch, tmp_path):
    ledger = _patch_ledger(monkeypatch, tmp_path)
    append_ledger_row(
        {
            "ok": True,
            "album_url": "https://www.erome.com/a/priv1",
            "title": "Draft A",
            "visibility": "private",
            "governance_status": "needs_review",
            "tags": ["milf"],
        }
    )
    append_ledger_row(
        {
            "ok": True,
            "album_url": "https://www.erome.com/a/pub1",
            "title": "Live",
            "visibility": "public",
            "governance_status": "approved_public",
        }
    )
    pending = gov.list_pending_review()
    assert len(pending) == 1
    assert pending[0]["album_url"].endswith("/a/priv1")

    out = gov.mark_governance(
        album_url="https://www.erome.com/a/priv1",
        status="approved_public",
        title="Final Title",
        tags=["milf", "webcam"],
    )
    assert out["ok"] is True
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    priv = next(r for r in rows if str(r.get("album_url", "")).endswith("/a/priv1"))
    assert priv["governance_status"] == "approved_public"
    assert priv["visibility"] == "public"
    assert priv["title"] == "Final Title"
    assert gov.list_pending_review() == []


def test_sidecar_visibility_merge(tmp_path):
    side = {
        "visibility": "private",
        "tags": ["milf", "amateur"],
        "source": "intel_week",
    }
    (tmp_path / "erome.params.json").write_text(json.dumps(side), encoding="utf-8")
    params = merge_sidecar_params(
        tmp_path,
        EromeUploadParams(title="Folder Title", visibility=None, source="cli"),
    )
    assert params.visibility == "private"
    assert "milf" in params.tags
    assert params.source in ("cli", "intel_week")


def test_record_erome_upload_private_skips_published_at(monkeypatch, tmp_path):
    ledger = tmp_path / "upload_ledger.jsonl"
    analytics = tmp_path / "analytics"
    analytics.mkdir()
    monkeypatch.setattr("app.services.erome_upload_policy.ledger_path", lambda: ledger)
    monkeypatch.setattr("app.services.erome_upload_analytics.analytics_dir", lambda: analytics)
    path = record_erome_upload(
        EromeUploadParams(title="Priv", tags=["x"], visibility="private", source="test"),
        {
            "ok": True,
            "album_url": "https://www.erome.com/a/zz",
            "visibility": "private",
            "governance_status": "needs_review",
            "file_count": 1,
        },
    )
    assert path.is_file()
    row = json.loads(ledger.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["visibility"] == "private"
    assert row["governance_status"] == "needs_review"
    assert row["published_at"] is None


def test_seed_intel_week_sidecar(monkeypatch, tmp_path):
    monkeypatch.setattr(gov, "erome_staging_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "app.services.erome_upload_policy.intel_upload_hints",
        lambda top_n=8: {
            "ok": True,
            "top_tags": [{"tag": "milf", "score": 10}, {"tag": "webcam", "score": 8}],
            "top_quartile_tags": ["milf"],
            "preferred_format_bucket": "single_video",
            "saturated_tags": [],
            "row_count": 40,
        },
    )
    folder = gov.intel_week_staging_dir(week="2026-W28")
    out = gov.seed_intel_week_sidecar(folder, title="Week pack")
    assert out["ok"] is True
    side = json.loads((folder / "erome.params.json").read_text(encoding="utf-8"))
    assert side["visibility"] == "private"
    assert "milf" in side["tags"]
