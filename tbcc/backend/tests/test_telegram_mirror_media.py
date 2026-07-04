"""Tests for storage-topic mirror media classification and upload prep."""

from types import SimpleNamespace

from telethon.tl.types import DocumentAttributeVideo, MessageMediaDocument

from app.services.telegram_storage import (
    TelegramStorage,
    _channel_message_media_kind,
    _document_video_attributes,
)


def _doc_message(*, mime: str = "video/mp4", attrs=None):
    document = SimpleNamespace(mime_type=mime, attributes=attrs or [])
    return SimpleNamespace(
        media=MessageMediaDocument(document=document),
    )


def test_document_video_attributes_from_attribute():
    doc = SimpleNamespace(
        mime_type="video/mp4",
        attributes=[DocumentAttributeVideo(duration=127, w=1280, h=720, supports_streaming=True)],
    )
    attrs = _document_video_attributes(doc)
    assert attrs is not None
    assert attrs[0].duration == 127
    assert attrs[0].w == 1280
    assert attrs[0].h == 720


def test_channel_message_media_kind_detects_video_without_mime():
    msg = _doc_message(
        mime="application/octet-stream",
        attrs=[DocumentAttributeVideo(duration=90, w=640, h=480, supports_streaming=False)],
    )
    assert _channel_message_media_kind(msg) == "video"


def test_prepare_file_for_send_attaches_video_attributes():
    msg = _doc_message(
        attrs=[DocumentAttributeVideo(duration=42, w=800, h=600, supports_streaming=True)],
    )
    storage = TelegramStorage(client=SimpleNamespace())  # type: ignore[arg-type]
    data = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32
    _f, kwargs, bucket = storage._prepare_file_for_send(
        data,
        "video",
        skip_watermark=True,
        source_message=msg,
    )
    assert bucket == "video"
    assert kwargs.get("force_document") is False
    assert kwargs.get("attributes")
    assert kwargs["attributes"][0].duration == 42
