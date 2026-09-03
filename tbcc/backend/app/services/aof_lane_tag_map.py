"""
Low-CPU semantic tag → AOF network lane map (no CLIP / NSFW / LLM).

Canonical keys match ``aof_network`` (e.g. ``big_tits``). Folder labels use
Telegram storage emoji stamps + display names: ``🍒 AOF BIG TITS``.
"""

from __future__ import annotations

import re
from pathlib import Path

# tag fragment (lowercase, no #) → ordered AOF network keys
LANE_TAG_MAP: dict[str, tuple[str, ...]] = {
    # ABG / LBFM
    "malaysian": ("abg",),
    "malay": ("abg",),
    "indonesian": ("abg",),
    "indo": ("abg",),
    "thai": ("abg",),
    "vietnam": ("abg",),
    "vietnamese": ("abg",),
    "viet": ("abg",),
    "cambodian": ("abg",),
    "khmer": ("abg",),
    "filipina": ("abg",),
    "pinay": ("abg",),
    "asian": ("abg",),
    "abg": ("abg",),
    "lbfm": ("abg",),
    # Ass / curves
    "ass": ("ass",),
    "booty": ("ass",),
    "pawg": ("ass",),
    "curvy": ("ass", "big_tits"),
    "thick": ("ass", "big_tits"),
    # Big tits ecosystem (canonical big_tits — not legacy bigtits)
    "bbw": ("big_tits",),
    "bigtits": ("big_tits",),
    "big_tits": ("big_tits",),
    "bigboobs": ("big_tits",),
    "boobs": ("big_tits",),
    "tits": ("big_tits",),
    "bustyy": ("big_tits",),
    "busty": ("big_tits",),
    # Other lanes
    "milf": ("milf",),
    "gilf": ("milf",),
    "mature": ("milf",),
    "blowjob": ("blowjob",),
    "bj": ("blowjob",),
    "oral": ("blowjob",),
    "voyeur": ("voyeur",),
    "public": ("voyeur",),
    "taboo": ("taboo",),
    "goon": ("goon",),
    "bop": ("bop",),
    "ai": ("ai",),
    "deepfake": ("ai",),
    "packs": ("packs",),
    "pack": ("packs",),
    "cosplay": ("cosplay",),
    "cosplayer": ("cosplay",),
    "amateur": ("amateur",),
    "homemade": ("amateur",),
    "full_length": ("full_length",),
    "fulllength": ("full_length",),
    "feature": ("full_length",),
}

# Legacy scrape key → canonical aof_network key
_LEGACY_KEY_ALIASES: dict[str, str] = {
    "bigtits": "big_tits",
}

_TAG_RE = re.compile(r"#?([\w\u0080-\uFFFF]+)", re.UNICODE)
_AOF_BRAND_RE = re.compile(r"(?i)telegram\.me_aofmainhub|t\.me_aofmainhub")
_SAFE_NAME_RE = re.compile(r"[^\w.\-]+")


def normalize_tag_token(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s.startswith("#"):
        s = s[1:]
    return s


def normalize_lane_key(key: str | None) -> str | None:
    k = (key or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not k:
        return None
    k = _LEGACY_KEY_ALIASES.get(k, k)
    return k


def suggest_lane_keys_from_tags(tags: str | list[str] | None, *, limit: int = 6) -> list[str]:
    """Return ordered unique canonical AOF lane keys from tag sample."""
    tokens: list[str] = []
    if isinstance(tags, list):
        tokens = [normalize_tag_token(t) for t in tags]
    elif tags:
        for part in re.split(r"[,;\s]+", str(tags)):
            m = _TAG_RE.match(part.strip())
            if m:
                tokens.append(normalize_tag_token(m.group(1)))

    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        keys = LANE_TAG_MAP.get(tok)
        if not keys:
            for frag, mapped in LANE_TAG_MAP.items():
                if frag in tok or tok in frag:
                    keys = mapped
                    break
        if not keys:
            continue
        for k in keys:
            nk = normalize_lane_key(k)
            if not nk or nk in seen:
                continue
            seen.add(nk)
            out.append(nk)
            if len(out) >= limit:
                return out
    return out


def resolve_lane_key(tags: str | list[str] | None, *, preferred: str | None = None) -> str | None:
    """Primary lane for routing: preferred key if valid, else first tag suggestion."""
    pref = normalize_lane_key(preferred)
    if pref:
        return pref
    keys = suggest_lane_keys_from_tags(tags, limit=1)
    return keys[0] if keys else None


def lane_display_name(lane_key: str | None) -> str:
    from app.data.aof_network import network_channel_by_key

    key = normalize_lane_key(lane_key)
    if not key:
        return "Unsorted"
    ch = network_channel_by_key(key)
    if ch:
        return ch.display_name
    return key.replace("_", " ").upper()


# The real AOF network lanes — single source of truth for "what's a valid lane key."
CANONICAL_LANE_KEYS: tuple[str, ...] = (
    "abg",
    "ai",
    "ass",
    "big_tits",
    "blowjob",
    "bop",
    "goon",
    "inbox",
    "milf",
    "packs",
    "taboo",
    "voyeur",
    "full_length",
    "erome",
    "stim",
)

def _merge_corpus_lane_tag_aliases() -> None:
    """Layer first-party tag_corpus.json aliases onto LANE_TAG_MAP (additive — never
    overwrites an existing hand-curated entry). Single source of truth for cue
    vocabulary; see app/services/tag_corpus.py.
    """
    try:
        from app.services.tag_corpus import lane_tag_map_aliases_for_lane

        for lane in CANONICAL_LANE_KEYS:
            for alias, lanes in lane_tag_map_aliases_for_lane(lane).items():
                LANE_TAG_MAP.setdefault(alias, lanes)
    except Exception:
        # Corpus is optional sugar for LANE_TAG_MAP — never break tag resolution
        # if the data file is missing/malformed.
        pass


_merge_corpus_lane_tag_aliases()


# Disk folder names under Downloads/tbcc/AOF NETWORK (operator tree — no emoji).
LANE_DISK_FOLDERS: dict[str, str] = {
    "abg": "AOF ABGLBFM",
    "ai": "AOF AI",
    "ass": "AOF ASS",
    "big_tits": "AOF BIG TITS",
    "blowjob": "AOF BLOWJOB",
    "bop": "AOF BOP",
    "goon": "AOF GOON",
    "inbox": "AOF INBOX",
    "milf": "AOF MILFGILF",
    "packs": "AOF PACKS",
    "taboo": "AOF TABOO",
    "voyeur": "AOF VOYPUB",
    "full_length": "AOF FULL LENGTH",
    "erome": "AOF EROME UPLOAD",
    "stim": "AOF STIM",
}


def lane_disk_folder_name(lane_key: str | None) -> str:
    """Match operator AOF NETWORK subfolders (e.g. milf → AOF MILFGILF)."""
    key = normalize_lane_key(lane_key)
    if not key:
        return "Unsorted"
    return LANE_DISK_FOLDERS.get(key) or f"AOF {lane_display_name(key).replace(' / ', '').replace('/', '')}"


def lane_folder_name(lane_key: str | None, *, style: str | None = None) -> str:
    """
    Folder segment for watch library.

    style:
      - ``emoji`` (default): ``🍒 AOF BIG TITS`` via STORAGE_CATEGORY_EMOJI
      - ``disk``: operator AOF NETWORK folder names (``AOF MILFGILF``, …)
    """
    import os

    mode = (style or os.environ.get("TBCC_WATCH_AOF_FOLDER_STYLE") or "emoji").strip().lower()
    if mode in ("disk", "network", "operator"):
        return lane_disk_folder_name(lane_key)
    if mode not in ("emoji", "stamp", "telegram", ""):
        # Unknown → treat as emoji (plan default)
        pass
    from app.data.aof_storage_hub_map import category_emoji_for_network_key

    key = normalize_lane_key(lane_key)
    if not key:
        return "Unsorted"
    emoji = category_emoji_for_network_key(key)
    return f"{emoji} {lane_display_name(key)}"

def lane_emoji_stamp(lane_key: str | None) -> str:
    from app.data.aof_storage_hub_map import category_emoji_for_network_key

    return category_emoji_for_network_key(normalize_lane_key(lane_key))


def sanitize_aof_name_segment(raw: str) -> str:
    s = _SAFE_NAME_RE.sub("_", (raw or "").strip()).strip("_")
    return (s[:64] or "media")


def is_aof_branded_filename(name: str) -> bool:
    return bool(_AOF_BRAND_RE.search(name or ""))


def build_aof_filename(*, name: str = "media", index: int = 1, ext: str = "jpg") -> str:
    """Match extension TbccZipNaming default: AOF_{name}_{#####}_telegram.me_aofmainhub.{ext}"""
    seg = sanitize_aof_name_segment(name)
    idx = max(1, int(index))
    e = (ext or "jpg").lstrip(".").lower() or "jpg"
    return f"AOF_{seg}_{idx:05d}_telegram.me_aofmainhub.{e}"


def aof_filename_for_path(path: Path, *, name_hint: str | None = None, index: int = 1) -> str:
    stem_hint = name_hint or path.stem
    if is_aof_branded_filename(path.name):
        return path.name
    # Strip accidental AOF_ prefix for cleaner segment
    hint = stem_hint
    if hint.lower().startswith("aof_"):
        hint = hint[4:]
    return build_aof_filename(name=hint, index=index, ext=path.suffix.lstrip(".") or "jpg")
