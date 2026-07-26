"""Extension Storage Hub topic list + send validation (no Telethon)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.extension_storage_hub import _short_topic_label, _topics_payload
from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
from app.main import app


def test_short_topic_label_strips_aof_storage():
    assert _short_topic_label("AOF MILF/GILF STORAGE") == "MILF/GILF"
    assert _short_topic_label("AOF ASS STORAGE") == "ASS"


def test_topics_payload_includes_milf_and_ass():
    topics = _topics_payload()
    assert topics
    keys = {t["network_key"] for t in topics}
    assert "milf" in keys
    assert "ass" in keys
    milf = next(t for t in topics if t["network_key"] == "milf")
    assert milf["message_thread_id"] == 5972
    assert "MILF" in milf["short_label"].upper() or "GILF" in milf["short_label"].upper()


def test_list_endpoint():
    client = TestClient(app)
    r = client.get("/extension/storage-hub")
    assert r.status_code == 200
    data = r.json()
    assert data["storage_hub_ident"] == STORAGE_HUB_IDENT
    assert isinstance(data["topics"], list)
    assert len(data["topics"]) >= 8


def test_send_rejects_unknown_topic():
    client = TestClient(app)
    r = client.post(
        "/extension/storage-hub/send",
        files={"file": ("x.jpg", b"\xff\xd8\xff", "image/jpeg")},
        data={"media_type": "photo", "message_thread_id": "999999"},
    )
    assert r.status_code == 400
    assert r.json().get("ok") is False


def test_send_rejects_empty():
    client = TestClient(app)
    r = client.post(
        "/extension/storage-hub/send",
        files={"file": ("x.jpg", b"", "image/jpeg")},
        data={"media_type": "photo", "message_thread_id": "5972"},
    )
    assert r.status_code == 400
