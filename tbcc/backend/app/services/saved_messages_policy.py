"""When TBCC should still touch Telegram Saved Messages (me) vs local disk only."""

from __future__ import annotations

import os


def loot_local_bytes_only() -> bool:
    """
    Loot rolls deliver from on-disk pool bytes only — no Saved Messages download.

    Default on: avoids admin_import.session lock storms and dead telegram_message_id refs.
    Set TBCC_LOOT_LOCAL_BYTES_ONLY=0 to allow legacy Saved Messages refs until migrated.
    """
    return (os.getenv("TBCC_LOOT_LOCAL_BYTES_ONLY") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def loot_allows_saved_message_delivery() -> bool:
    return not loot_local_bytes_only()
