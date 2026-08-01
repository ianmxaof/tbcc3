#!/usr/bin/env python3
"""Smoke companion + LLM config before/after island deploy. Run from tbcc/backend."""

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


async def _main(verify_llm: bool) -> int:
    from app.services.companion_generation import check_public_webhook_reachable
    from app.services.companion_ops import companion_ops_status
    from app.services.llm_chat import complete_llm_chat, provider_configured

    ops = await companion_ops_status()
    webhook_ok, webhook_detail = await check_public_webhook_reachable()
    out: dict = {
        "companion_ops": ops,
        "webhook_ok": webhook_ok,
        "webhook_detail": webhook_detail,
        "llm_configured": provider_configured(),
    }

    if verify_llm and provider_configured():
        try:
            reply = await complete_llm_chat(
                [
                    {"role": "system", "content": "Reply with exactly: spicy-smoke-ok"},
                    {"role": "user", "content": "ping"},
                ]
            )
            out["llm_smoke_reply"] = (reply or "")[:200]
            out["llm_smoke_ok"] = "spicy-smoke-ok" in (reply or "").lower()
        except Exception as e:
            out["llm_smoke_ok"] = False
            out["llm_smoke_error"] = str(e)[:300]

    print(json.dumps(out, indent=2, default=str))

    ok = bool(ops.get("token_configured")) and webhook_ok and provider_configured()
    if verify_llm:
        ok = ok and bool(out.get("llm_smoke_ok"))
    return 0 if ok else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Companion island smoke")
    p.add_argument("--verify-llm", action="store_true", help="Send one chat completion ping")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_main(args.verify_llm)))


if __name__ == "__main__":
    main()
