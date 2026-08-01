"""Map Telegram SCRP folders / inbound channels → AOF content pools."""

from __future__ import annotations

import re

# First population batch (user priority lanes).
FIRST_BATCH_POOL_KEYS: tuple[str, ...] = ("bop", "goon", "abg", "voyeur", "ai")

# Second batch (milf / big tits folders).
SECOND_BATCH_POOL_KEYS: tuple[str, ...] = ("milf", "big_tits")

# Third batch — lanes not covered in first two batches.
THIRD_BATCH_POOL_KEYS: tuple[str, ...] = ("blowjob", "ass", "taboo", "packs")

# All inbound folder-mapped pool keys (excludes AOF main hub).
ALL_FOLDER_POOL_KEYS: tuple[str, ...] = (
    "bop",
    "goon",
    "abg",
    "voyeur",
    "ai",
    "milf",
    "big_tits",
    "blowjob",
    "ass",
    "taboo",
    "full_length",
    "packs",
    "inbox",
)

BATCH_PRESETS: dict[str, tuple[str, ...]] = {
    "first": FIRST_BATCH_POOL_KEYS,
    "second": SECOND_BATCH_POOL_KEYS,
    "third": THIRD_BATCH_POOL_KEYS,
}


def pool_keys_for_batch(batch: str | None) -> list[str]:
    """Resolve --batch preset or return remainder (unbatched lanes)."""
    key = (batch or "").strip().lower()
    if key in BATCH_PRESETS:
        return list(BATCH_PRESETS[key])
    if key == "remainder":
        done = set(FIRST_BATCH_POOL_KEYS) | set(SECOND_BATCH_POOL_KEYS) | set(THIRD_BATCH_POOL_KEYS)
        return [k for k in ALL_FOLDER_POOL_KEYS if k not in done]
    if key == "next":
        return list(next_unscraped_batch_pool_keys())
    return list(FIRST_BATCH_POOL_KEYS)


def next_unscraped_batch_pool_keys(*, size: int = 5) -> tuple[str, ...]:
    """Next N pool lanes not yet assigned to a named batch preset."""
    done = set()
    for keys in BATCH_PRESETS.values():
        done.update(keys)
    remaining = [k for k in ALL_FOLDER_POOL_KEYS if k not in done]
    return tuple(remaining[: max(1, int(size))])

# Folder title patterns (your "BIG TITS SCRP", "MILF SCRP", … labels) → AOF network pool key.
FOLDER_TITLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"scrp\s*bulk|\bscrp\s*bulk\b", re.I), "inbox"),
    (re.compile(r"scrp\s*tits|\btits\b|big\s*tits", re.I), "big_tits"),
    (re.compile(r"scrp\s*milf|\bmilf|gilf", re.I), "milf"),
    (re.compile(r"scrp\s*bop|\bbop\b", re.I), "bop"),
    (re.compile(r"scrp\s*goon|\bgoon\b|spun", re.I), "goon"),
    (re.compile(r"scrp\s*azn|\bazn\b|asian|abg|lbfm", re.I), "abg"),
    (re.compile(r"scrp\s*voy|voypub|voyeur|public", re.I), "voyeur"),
    (re.compile(r"scrp\s*ai|\bai\b|deepfake|waifu", re.I), "ai"),
    (re.compile(r"scrp\s*bj|\bbj\b|blowjob", re.I), "blowjob"),
    (re.compile(r"scrp\s*ass|\bass\b|big\s*ass", re.I), "ass"),
    (re.compile(r"scrp\s*tab|\btaboo\b|\btab\b", re.I), "taboo"),
    (re.compile(r"scrp\s*full|\bfull\s*length|\bfullength", re.I), "full_length"),
    (re.compile(r"mega|lv|link", re.I), "packs"),
)

# Never scrape these inbound ids (your own AOF infra / hubs).
SKIP_INBOUND_CHAT_IDS: frozenset[int] = frozenset(
    {
        -1003812457581,  # Storage & Bot Hangar
        -1004247083739,  # AOF PACKS
        -1003970144685,  # AOF LINK HUB
        -1003206350461,  # AOF main group
    }
)

# Seed inbound channels when a folder is empty or Telethon cannot read folders yet.
# Edit freely — or rely on your Telegram folder contents (preferred).
DEFAULT_INBOUND_SOURCES: dict[str, list[dict]] = {
    "bop": [
        {"chat_id": -1002603132268, "label": "Horny Central"},
        {"chat_id": -1002037585790, "label": "GoldenFans18+"},
    ],
    "goon": [
        {"chat_id": -1002603132268, "label": "Horny Central"},
        {"chat_id": -1001819558862, "label": "PNP GC"},
    ],
    "abg": [
        {"chat_id": -1003220778547, "label": "Hagarth's Asian's"},
    ],
    "voyeur": [
        {"chat_id": -1003145164056, "label": "Hagarth's Public"},
    ],
    "ai": [],
    "big_tits": [
        {"chat_id": -1003258433993, "label": "Hagarth's big tits"},
        {"chat_id": -1001565052409, "label": "Big Tits Milfs"},
    ],
    "milf": [
        {"chat_id": -1002337833082, "label": "Hagarth's Milf/Gilf"},
        {"chat_id": -1001565052409, "label": "Big Tits Milfs"},
    ],
    "blowjob": [
        {"chat_id": -1001730869690, "label": "Only Blowjob"},
    ],
    "ass": [
        {"chat_id": -1002779215335, "label": "Big A$$ mega after lv"},
        {"chat_id": -1003271959583, "label": "Hagarth's Big ass"},
    ],
    "taboo": [],
    "full_length": [],
    "packs": [],
    "inbox": [],
}


def match_folder_title_to_pool_key(folder_title: str) -> str | None:
    t = (folder_title or "").strip()
    if not t:
        return None
    best: tuple[int, str] | None = None
    for pat, key in FOLDER_TITLE_PATTERNS:
        if pat.search(t):
            score = len(pat.pattern)
            if best is None or score > best[0]:
                best = (score, key)
    return best[1] if best else None
