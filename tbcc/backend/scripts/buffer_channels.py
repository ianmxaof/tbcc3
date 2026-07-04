"""List Buffer organizations and channels (for .env setup). Run from tbcc/backend."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.buffer_graphql import find_channel_id_by_service, get_channels, get_organizations, resolve_organization_id


def main() -> None:
    orgs = get_organizations()
    print("organizations:", json.dumps(orgs, indent=2))
    oid = resolve_organization_id()
    print("\nresolved organization_id:", oid, file=sys.stderr)
    chans = get_channels(organization_id=oid)
    print("\nchannels:", json.dumps(chans, indent=2))
    twitter = find_channel_id_by_service("twitter", organization_id=oid)
    instagram = find_channel_id_by_service("instagram", organization_id=oid)
    threads = find_channel_id_by_service("threads", organization_id=oid)
    if twitter:
        print(f"\nSuggested TBCC_BUFFER_CHANNEL_ID_PRIMARY (twitter): {twitter}", file=sys.stderr)
    if instagram and threads:
        print(
            f"Suggested TBCC_BUFFER_CHANNEL_IDS (instagram,threads): {instagram},{threads}",
            file=sys.stderr,
        )
    elif instagram:
        print(f"Suggested TBCC_BUFFER_CHANNEL_IDS (instagram only): {instagram}", file=sys.stderr)
    elif threads:
        print(f"Suggested TBCC_BUFFER_CHANNEL_IDS (threads only): {threads}", file=sys.stderr)
    print("\nMatch displayName/name to your target @handle before copying ids into .env.", file=sys.stderr)


if __name__ == "__main__":
    main()
