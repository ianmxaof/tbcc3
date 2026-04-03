"""Detect actual media kind from file magic bytes (overrides wrong Content-Type / URL)."""

from __future__ import annotations


def sniff_media_kind(data: bytes) -> tuple[str, str]:
    """
    Returns (kind, ext) where kind is one of: photo, video, gif, document.
    ext is a sensible filename extension for Telethon upload.
    """
    if not data or len(data) < 12:
        return "document", "bin"

    if data[:3] == b"\xff\xd8\xff":
        return "photo", "jpg"

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "photo", "png"

    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return "photo", "webp"

    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "gif"

    # MP4 / ISO BMFF
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video", "mp4"

    # WebM / Matroska EBML
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "video", "webm"

    # AVI
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"AVI ":
        return "video", "avi"

    return "document", "bin"


def telegram_media_type_from_sniff(kind: str) -> str:
    """Map sniff kind to Media.media_type / send_file branch."""
    if kind == "video":
        return "video"
    if kind == "gif":
        return "photo"
    if kind == "photo":
        return "photo"
    return "document"
