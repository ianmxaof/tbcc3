"""Smoke: creator promo normalize + island API queue (no Telegram UI)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

load_dotenv(_backend.parent / ".env", override=True)

from app.services.loot_creator_platforms import normalize_creator_url

API = (
    os.getenv("TBCC_ISLAND_API_URL")
    or "https://api.powercore.app"
).rstrip("/")
KEY = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
SMOKE_UID = 7787282561  # operator sandbox


def main() -> int:
    samples = [
        "https://onlyfans.com/smoke_test_handle",
        "https://sextingfinder.com/profile/smokeuser",
        "https://t.me/smoke_channel",
        "https://link-hub.net/1367336/dead",
    ]
    print("=== normalize_creator_url ===")
    for s in samples:
        out = normalize_creator_url(s)
        print(f"  {'OK' if out else 'REJECT':6} {s}")

    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{API}/health")
        print(f"\n=== health {r.status_code} ===")

        handle = f"tbcc_smoke_{int(time.time())}"
        body = {
            "url": f"https://fansly.com/{handle}",
            "telegram_user_id": SMOKE_UID,
            "display_name": "Smoke Test",
        }
        r = client.post(f"{API}/loot/creator-submit", json=body)
        print(f"=== creator-submit {r.status_code} ===")
        print(r.text[:1200])

        if not KEY:
            print("\nSKIP queue: TBCC_INTERNAL_API_KEY not set")
            return 0

        headers = {"X-TBCC-Internal-Key": KEY, "Content-Type": "application/json"}
        r = client.get(f"{API}/loot/creator-submissions?status=pending&limit=5", headers=headers)
        print(f"\n=== pending queue {r.status_code} ===")
        if r.status_code == 200:
            items = r.json().get("items") or []
            print(f"  pending count (page): {len(items)}")
            for row in items[:3]:
                print(f"  #{row.get('submission_id')} {row.get('label')} {row.get('normalized_url')}")
        else:
            print(r.text[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
