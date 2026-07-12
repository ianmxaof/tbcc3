"""Post & earn Linkvertise slugs — one dashboard post per AOF network destination."""

from __future__ import annotations

# Keys align with aof_network.BULLETIN_CHANNEL_INVITES + channel keys.
AOF_MANUAL_LV_GATES: dict[str, str] = {
    "main_group": "https://link-center.net/1367336/eURa9KVdlIR2",
    "main": "https://link-center.net/1367336/eURa9KVdlIR2",
    "mainhub": "https://link-center.net/1367336/DgIo85a7oux0",
    "ai": "https://direct-link.net/1367336/ZrNHOhHaxSYM",
    "ass": "https://link-hub.net/1367336/6PIRZVafUcTa",
    "blowjob": "https://link-target.net/1367336/QBzt1dFPTqai",
    "big_tits": "https://direct-link.net/1367336/j3kYBP7ehwvi",
    "taboo": "https://link-center.net/1367336/XNRjZbn41Sg8",
    "voyeur": "https://direct-link.net/1367336/N8IObaZoZEqE",
    "milf": "https://link-target.net/1367336/0zFTaQqUG3S3",
    "abg": "https://link-hub.net/1367336/cnly0eLYXB9P",
    "goon": "https://link-hub.net/1367336/HAOxJYVt7iD4",
    "bop": "https://link-center.net/1367336/vaTKeNRpy3tV",
    "packs": "https://direct-link.net/1367336/ARbG9LkABgVV",
    "loot": "https://direct-link.net/1367336/S4isAVBXklrz",
    # Post & earn addlist gate (t.me/addlist target).
    "addlist": "https://link-target.net/1367336/OXrWginA5Ztr",
}

# LootModifier.label (seed_aof_shop_and_loot) → gate key
LOOT_MODIFIER_LABEL_TO_GATE_KEY: dict[str, str] = {
    "AOF Main Hub": "main_group",
    "AOF AI": "ai",
    "AOF ASS": "ass",
    "AOF BIG TITS": "big_tits",
    "AOF BLOWJOB": "blowjob",
    "AOF MILF": "milf",
    "AOF TABOO": "taboo",
    "AOF PUBLIC VOYEUR": "voyeur",
    "AOF LOOT ROOM": "loot",
    "AOF Addlist": "addlist",
    "AOF GOON": "goon",
    "AOF BOP": "bop",
    "AOF PACKS": "packs",
    "ABG / LBFM": "abg",
}

# Anchor text (lowercase) → gate key for stale URL replacement in scheduled post HTML.
ANCHOR_TEXT_TO_GATE_KEY: tuple[tuple[str, str], ...] = (
    ("addlist all channels", "addlist"),
    ("all channels addlist", "addlist"),
    ("addlist", "addlist"),
    ("aofmainhub", "mainhub"),
    ("t.me/aofmainhub", "mainhub"),
    ("main group", "loot"),
    ("main hub", "loot"),
    ("aof blowjob", "blowjob"),
    ("blowjob", "blowjob"),
    ("aof big tits", "big_tits"),
    ("big tits", "big_tits"),
    ("aof public voyeur", "voyeur"),
    ("public voyeur", "voyeur"),
    ("voyeur", "voyeur"),
    ("aof abg", "abg"),
    ("abg / lbfm", "abg"),
    ("lbfm", "abg"),
    ("aof loot room", "loot"),
    ("loot room", "loot"),
    ("aof packs", "packs"),
    ("aof goon", "goon"),
    ("aof bop", "bop"),
    ("aof milf", "milf"),
    ("milf", "milf"),
    ("aof taboo", "taboo"),
    ("taboo", "taboo"),
    ("aof ass", "ass"),
    ("aof ai", "ai"),
    ("join", "loot"),
)


def manual_gate_url(key: str) -> str | None:
    k = (key or "").strip().lower()
    return AOF_MANUAL_LV_GATES.get(k)


def manual_gate_urls() -> dict[str, str]:
    """Full bulletin/footer map (keys used by growth hub)."""
    out = dict(AOF_MANUAL_LV_GATES)
    out.setdefault("main_group", out["main"])
    out.setdefault("addlist", out.get("addlist") or out["main_group"])
    return {k: v for k, v in out.items() if k != "main" and v}


def all_manual_gate_urls() -> frozenset[str]:
    return frozenset(u.strip().split()[0] for u in AOF_MANUAL_LV_GATES.values() if u)
