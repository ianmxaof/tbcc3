#!/usr/bin/env python3
"""Probe manual vs dynamic Linkvertise URLs (takedown vs live gate page)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.services.link_gate_provider import wrap_linkvertise_url

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def probe(name: str, url: str) -> None:
    try:
        r = httpx.get(url, follow_redirects=True, timeout=25, headers=UA)
        body = (r.text or "")[:4000].lower()
        flags: list[str] = []
        if "no longer available" in body or "removed by the creator" in body:
            flags.append("TAKEDOWN")
        if "please enable" in body and "javascript" in body:
            flags.append("JS_GATE")
        if any(x in body for x in ("linkvertise", "link-target", "link-center", "link-to.net")):
            flags.append("LV_SHELL")
        print(f"{name}")
        print(f"  url:   {url[:100]}")
        print(f"  http:  {r.status_code}")
        print(f"  final: {str(r.url)[:100]}")
        print(f"  flags: {flags or ['UNKNOWN']}")
        print()
    except Exception as e:
        print(f"{name}: ERROR {e}\n")


def main() -> None:
    pub = 1367336
    targets = [
        ("manual_pixeldrain_paste", "https://link-target.net/1367336/MJtA5BGXQPeG"),
        ("dynamic_milf_invite", wrap_linkvertise_url(pub, "https://t.me/+AY0zGwyeAy9jNDIx")),
        ("dynamic_taboo_invite", wrap_linkvertise_url(pub, "https://t.me/+w46b7uJK5eo0MDcx")),
        ("dynamic_addlist", wrap_linkvertise_url(pub, "https://t.me/addlist/r-7_7CGIkExhMDcx")),
        ("dynamic_main_hub", wrap_linkvertise_url(pub, "https://t.me/+hMQzGsBFjF02MDkx")),
        (
            "dynamic_link_target_domain",
            wrap_linkvertise_url(
                pub,
                "https://t.me/+AY0zGwyeAy9jNDIx",
                base_url="https://link-target.net",
            ),
        ),
    ]
    for name, url in targets:
        probe(name, url)


if __name__ == "__main__":
    main()
