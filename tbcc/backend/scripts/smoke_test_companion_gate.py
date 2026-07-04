#!/usr/bin/env python3
"""Dry-run companion gate config + optional Bot API membership probe."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.companion_access import (
    affiliate_undress_url,
    can_spend_operator_api,
    free_trial_photos,
    gate_enabled,
    gate_lv_url,
    get_access,
    network_channel_idents,
)
from app.services.companion_referral import referral_bonus_photos, referrals_enabled
from app.services.companion_stars import stars_enabled, stars_per_photo

import httpx


async def _probe_bot_api(channel_ident: str, admin_uid: int | None) -> dict:
    token = (os.getenv("TBCC_COMPANION_BOT_TOKEN") or "").strip()
    if not token:
        return {"error": "TBCC_COMPANION_BOT_TOKEN unset"}
    base = f"https://api.telegram.org/bot{token}"
    out: dict = {"channel": channel_ident}
    async with httpx.AsyncClient(timeout=30.0) as client:
        me = (await client.get(f"{base}/getMe")).json()
        if not me.get("ok"):
            out["bot"] = {"error": me}
            return out
        bot_id = me["result"]["id"]
        out["bot"] = {"id": bot_id, "username": me["result"].get("username")}
        chat_id = int(channel_ident) if channel_ident.lstrip("-").isdigit() else channel_ident
        adm = await client.get(
            f"{base}/getChatMember",
            params={"chat_id": chat_id, "user_id": bot_id},
        )
        out["bot_membership"] = adm.json()
        if admin_uid:
            user_chk = await client.get(
                f"{base}/getChatMember",
                params={"chat_id": chat_id, "user_id": admin_uid},
            )
            out["admin_probe"] = user_chk.json()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test companion gate configuration")
    parser.add_argument("--probe-channels", action="store_true", help="Bot API probe all AOF channels")
    parser.add_argument("--user-id", type=int, help="User id to simulate access state")
    args = parser.parse_args()

    report: dict = {
        "gate_enabled": gate_enabled(),
        "gate_lv_url": gate_lv_url() or "(missing)",
        "free_trial_photos": free_trial_photos(),
        "stars_enabled": stars_enabled(),
        "stars_per_photo": stars_per_photo(),
        "referrals_enabled": referrals_enabled(),
        "referral_bonus_photos": referral_bonus_photos(),
        "affiliate_url": affiliate_undress_url() or "(unset)",
        "channel_count": len(network_channel_idents()),
        "channels": [{"key": k, "ident": i, "name": n} for k, i, n in network_channel_idents()],
    }

    if args.user_id:
        uid = int(args.user_id)
        acc = get_access(uid)
        ok, reason = can_spend_operator_api(uid)
        report["user"] = {
            "user_id": uid,
            "access": acc.to_dict(),
            "can_spend": ok,
            "reason": reason,
        }

    if args.probe_channels:
        probes = []
        for _k, ident, name in network_channel_idents():
            row = asyncio.run(_probe_bot_api(ident, args.user_id))
            row["display_name"] = name
            probes.append(row)
        report["channel_probes"] = probes
        bot_ok = all(
            p.get("bot_membership", {}).get("ok")
            and p["bot_membership"]["result"]["status"] in ("administrator", "creator")
            for p in probes
            if "bot_membership" in p
        )
        report["bot_admin_all_channels"] = bot_ok

    print(json.dumps(report, indent=2, ensure_ascii=False))
    missing_lv = not report["gate_lv_url"] or report["gate_lv_url"] == "(missing)"
    if missing_lv and gate_enabled():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
