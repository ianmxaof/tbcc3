"""Tests for Telegram → Erome storage lane."""

from __future__ import annotations

import pytest

from app.services import erome_telegram_ingest as ingest


def test_erome_storage_topic_from_env(monkeypatch):
    monkeypatch.setenv("TBCC_EROME_STORAGE_TOPIC_ID", "99999")
    assert ingest.erome_storage_topic_id() == 99999
    assert ingest.is_erome_storage_topic(99999) is True
    assert ingest.is_erome_storage_topic(1) is False


def test_erome_auto_upload_default_off(monkeypatch):
    monkeypatch.delenv("TBCC_EROME_AUTO_UPLOAD", raising=False)
    assert ingest.erome_auto_upload_enabled() is False
    monkeypatch.setenv("TBCC_EROME_AUTO_UPLOAD", "1")
    assert ingest.erome_auto_upload_enabled() is True


def test_erome_max_files_default_50(monkeypatch):
    monkeypatch.delenv("TBCC_EROME_MAX_FILES_PER_ALBUM", raising=False)
    assert ingest.erome_max_files_per_album() == 50


def test_erome_upload_job_key_grouped():
    class _Msg:
        def __init__(self, mid, gid=None):
            self.id = mid
            self.grouped_id = gid

    assert ingest.erome_upload_job_key(_Msg(10)) == 10
    assert ingest.erome_upload_job_key(_Msg(10, gid=999)) == 999
    assert ingest.erome_upload_job_key(_Msg(11, gid=999)) == 999


def test_stage_processed_bytes_for_erome(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "erome_staging_dir", lambda: tmp_path)
    items = [(b"\xff\xd8\xff" + b"\x00" * 100, "photo")]
    folder, paths = ingest.stage_processed_bytes_for_erome(items, batch_key="t1")
    assert folder.is_dir()
    assert len(paths) == 1
    assert paths[0].read_bytes() == items[0][0]


class _Cfg:
    allowed_extensions = (".jpg",)
    album_title_default = "AOF Pack"


class _Verdict:
    allowed = True
    warnings: list = []

    def to_dict(self):
        return {"allowed": True}


def _stub_upload_pipeline(tmp_path, monkeypatch, *, upload_ok: bool):
    """Wire upload_staged_folder's dependencies to hermetic stubs; return touched list."""
    from app.services import erome_upload_analytics, erome_upload_policy, idle_service_governor

    f = tmp_path / "000.jpg"
    f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 500)

    monkeypatch.setattr(ingest, "selectors_ready", lambda cfg: True)
    monkeypatch.setattr(ingest, "load_flow_config", lambda: _Cfg())
    monkeypatch.setattr(
        ingest,
        "upload_local_folder",
        lambda folder, **kw: ingest.UploadResult(
            ok=upload_ok,
            album_url="https://www.erome.com/a/xyz" if upload_ok else None,
            title=kw.get("title"),
            file_count=1,
            staging_path=str(folder),
            error=None if upload_ok else "album_not_published",
        ),
    )
    monkeypatch.setattr(erome_upload_policy, "check_upload_policy", lambda **kw: _Verdict())
    monkeypatch.setattr(erome_upload_analytics, "record_erome_upload", lambda *a, **k: tmp_path)

    touched: list[str] = []
    monkeypatch.setattr(idle_service_governor, "touch_service_activity", touched.append)
    return touched


def test_upload_staged_folder_signals_governor_on_success(tmp_path, monkeypatch):
    touched = _stub_upload_pipeline(tmp_path, monkeypatch, upload_ok=True)
    result = ingest.upload_staged_folder(tmp_path, title="T", skip_watermark=True, source="test")
    assert result.ok is True
    assert touched == ["erome_view_sync"]


def test_upload_staged_folder_no_governor_signal_on_failure(tmp_path, monkeypatch):
    touched = _stub_upload_pipeline(tmp_path, monkeypatch, upload_ok=False)
    result = ingest.upload_staged_folder(tmp_path, title="T", skip_watermark=True, source="test")
    assert result.ok is False
    assert touched == []


def test_format_erome_upload_reply_ok():
    text = ingest.format_erome_upload_reply(
        {"ok": True, "album_url": "https://www.erome.com/a/abc", "title": "Teaser", "file_count": 3},
        html=False,
    )
    assert "erome.com/a/abc" in text
    assert "3" in text
