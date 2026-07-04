"""Tests for companion image compression."""

from __future__ import annotations

import os

from app.services.companion_image_utils import compress_image_for_api_upload


def test_compress_large_payload_shrinks():
    path = os.path.join(os.path.dirname(__file__), "..", "erome_test_staging", "test_1.png")
    if not os.path.isfile(path):
        return
    raw = open(path, "rb").read()
    big = raw + b"\x00" * 3_500_000
    out, name = compress_image_for_api_upload(big, max_bytes=1_400_000)
    assert name == "result.jpg"
    assert len(out) <= 1_400_000
    assert out[:2] == b"\xff\xd8"
