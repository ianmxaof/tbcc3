"""Discover Buffer org + channel IDs from TBCC_BUFFER_API_KEY and write .env + Cursor MCP.

Run from tbcc/backend after pasting your new key into tbcc/.env:

  py -3.13 scripts/wire_buffer_credentials.py
  py -3.13 scripts/wire_buffer_credentials.py --sync-island   # also seed island .env

Only TBCC_BUFFER_API_KEY is required in .env — org and channel ids are auto-filled.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.buffer_graphql import (  # noqa: E402
    BufferRateLimitError,
    buffer_api_key,
    get_channels,
    get_organizations,
)

TBCC_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = TBCC_ROOT / ".env"
MCP_FILE = Path.home() / ".cursor" / "mcp.json"

_PREFERRED_X_HANDLES = ("wizardstick69", "powercoreai", "archiveoffilthx")


def _set_dotenv_key(lines: list[str], key: str, value: str) -> list[str]:
    pat = re.compile(rf"^{re.escape(key)}=")
    out: list[str] = []
    replaced = False
    for line in lines:
        if pat.match(line):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def _channel_label(ch: dict) -> str:
    return " ".join(
        str(ch.get(k) or "")
        for k in ("displayName", "name", "service")
    ).strip().lower()


def _pick_twitter_channels(chans: list[dict]) -> tuple[str | None, str | None]:
    twitter = [c for c in chans if str(c.get("service") or "").lower() == "twitter"]
    if not twitter:
        return None, None

    def score(ch: dict) -> int:
        label = _channel_label(ch)
        for i, hint in enumerate(_PREFERRED_X_HANDLES):
            if hint in label:
                return 100 - i
        return 0

    ranked = sorted(twitter, key=score, reverse=True)
    primary = str(ranked[0].get("id") or "").strip() or None
    secondary = None
    for ch in ranked[1:]:
        cid = str(ch.get("id") or "").strip()
        if cid and cid != primary:
            secondary = cid
            break
    return primary, secondary


def _pick_extra_channel_ids(chans: list[dict], *, skip: set[str]) -> str:
    extras: list[str] = []
    for service in ("instagram", "threads", "bluesky", "facebook", "linkedin"):
        for ch in chans:
            if str(ch.get("service") or "").lower() != service:
                continue
            cid = str(ch.get("id") or "").strip()
            if cid and cid not in skip and cid not in extras:
                extras.append(cid)
    return ",".join(extras)


def _write_env(updates: dict[str, str]) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    for key, value in updates.items():
        lines = _set_dotenv_key(lines, key, value)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_mcp_bearer(api_key: str) -> bool:
    if not MCP_FILE.is_file():
        print(f"skip MCP (missing {MCP_FILE})", file=sys.stderr)
        return False
    data = json.loads(MCP_FILE.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") or {}
    buf = servers.get("buffer")
    if not isinstance(buf, dict):
        print("skip MCP (no buffer server in mcp.json)", file=sys.stderr)
        return False
    headers = buf.setdefault("headers", {})
    headers["Authorization"] = f"Bearer {api_key}"
    MCP_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-wire Buffer org + channel IDs")
    parser.add_argument("--sync-island", action="store_true", help="Run seed-island-env-from-home.ps1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    key = (buffer_api_key() or "").strip()
    if not key:
        print("Set TBCC_BUFFER_API_KEY in tbcc/.env first.", file=sys.stderr)
        return 1

    try:
        orgs = get_organizations()
    except BufferRateLimitError as e:
        print(f"Buffer rate limited (retry_after={e.retry_after_s}s). Use a fresh API key.", file=sys.stderr)
        return 2

    if not orgs:
        print("No Buffer organizations for this API key.", file=sys.stderr)
        return 1

    oid = str(orgs[0].get("id") or "").strip()
    org_name = str(orgs[0].get("name") or "").strip()
    owner = str(orgs[0].get("ownerEmail") or "").strip()
    if len(orgs) > 1:
        print(f"Multiple orgs; using first: {org_name!r}", file=sys.stderr)

    try:
        chans = get_channels(organization_id=oid)
    except BufferRateLimitError as e:
        print(f"Buffer rate limited listing channels (retry_after={e.retry_after_s}s).", file=sys.stderr)
        return 2

    primary, secondary = _pick_twitter_channels(chans)
    skip = {x for x in (primary, secondary) if x}
    extras = _pick_extra_channel_ids(chans, skip=skip)

    updates = {
        "TBCC_BUFFER_API_KEY": key,
        "TBCC_BUFFER_ORGANIZATION_ID": oid,
    }
    if primary:
        updates["TBCC_BUFFER_CHANNEL_ID_PRIMARY"] = primary
    if secondary:
        updates["TBCC_BUFFER_CHANNEL_ID_X_SECONDARY"] = secondary
    else:
        updates["TBCC_BUFFER_CHANNEL_ID_X_SECONDARY"] = ""
    updates["TBCC_BUFFER_CHANNEL_IDS"] = extras

    print(json.dumps({"organization": org_name, "ownerEmail": owner, "channels": chans}, indent=2))

    summary = {
        "TBCC_BUFFER_ORGANIZATION_ID": oid,
        "TBCC_BUFFER_CHANNEL_ID_PRIMARY": primary,
        "TBCC_BUFFER_CHANNEL_ID_X_SECONDARY": secondary or "(cleared)",
        "TBCC_BUFFER_CHANNEL_IDS": extras or "(cleared)",
    }
    print("\nWill write:", json.dumps(summary, indent=2), file=sys.stderr)

    if args.dry_run:
        return 0

    _write_env(updates)
    mcp_ok = _write_mcp_bearer(key)
    print(f"Updated {ENV_FILE}", file=sys.stderr)
    if mcp_ok:
        print(f"Updated {MCP_FILE} (reload MCP in Cursor)", file=sys.stderr)

    if args.sync_island:
        ps1 = TBCC_ROOT / "scripts" / "revenue-island" / "seed-island-env-from-home.ps1"
        if ps1.is_file():
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                check=True,
                cwd=str(TBCC_ROOT),
            )
        else:
            print(f"skip island seed (missing {ps1})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
