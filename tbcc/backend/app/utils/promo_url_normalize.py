"""Normalize promo_image_url when users paste ImgBB BBCode or multiple URLs."""

from __future__ import annotations

import re


def normalize_promo_image_url(raw: str | None) -> str:
    """
    Users sometimes paste forum/ImgBB embeds, e.g.:
    https://ibb.co/xxx][img]https://i.ibb.co/yyy/file.jpg[/img]

    Telegram and our fetchers need a single direct image URL.
    """
    s = (raw or "").strip()
    if not s:
        return ""

    # ImgBB / BBCode: take the URL after ][img]
    if "][img]" in s.lower():
        s = s.split("][img]", 1)[-1]
        for sep in ("[/img]", "[", "\n", " "):
            if sep in s:
                s = s.split(sep, 1)[0]
                break
        s = s.strip()

    # First http(s) URL in the string
    m = re.search(r"https?://[^\s\[\]<>\"']+", s)
    if m:
        return m.group(0).rstrip(".,;)'\"")
    return s.strip()
