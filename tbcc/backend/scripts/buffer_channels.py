"""List Buffer organizations and channels (for .env setup). Run from tbcc/backend."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.buffer_graphql import find_channel_id_by_service, get_channels, get_organizations, resolve_organization_id


def main() -> None:
    orgs = get_organizations()
    print("organizations:", json.dumps(orgs, indent=2))
    oid = resolve_organization_id()
    print("\nresolved organization_id:", oid, file=sys.stderr)
    chans = get_channels(organization_id=oid)
    print("\nchannels:", json.dumps(chans, indent=2))
    twitter = find_channel_id_by_service("twitter", organization_id=oid)
    if twitter:
        print(f"\nSuggested TBCC_BUFFER_CHANNEL_ID_PRIMARY (twitter): {twitter}", file=sys.stderr)


if __name__ == "__main__":
    main()
