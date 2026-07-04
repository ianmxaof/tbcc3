"""Telegram channel sources for mega / file-host link scraping (user-curated)."""

from __future__ import annotations

# AOF PACKS — distribution target for resolved + LV-wrapped mega drops (relay posts).
AOF_PACKS_CHANNEL_ID = -1004247083739
AOF_PACKS_INVITE_URL = "https://t.me/+xCtxqzQEuoRmZGZh"

# kind hints:
#   lv_gated      — mostly Linkvertise / AdMaven; content every few ad posts
#   direct_host   — Sophon, terabox, bunkr, etc. without LV on every drop
#   mixed         — LV + mega + invites + site links

MEGA_SCRAPE_CHANNEL_SOURCES: list[dict] = [
    {"chat_id": -1003368758012, "label": "Leaks", "kind": "mixed"},
    {"chat_id": -1002779215335, "label": "Big A$$ mega after lv", "kind": "lv_gated"},
    {"chat_id": -1001565052409, "label": "Big Tits Milfs", "kind": "direct_host", "notes": "link.newsophon.com"},
    {"chat_id": -1001730869690, "label": "Only Blowjob", "kind": "direct_host", "notes": "link.newsophon.com"},
    {"chat_id": -1002567670679, "label": "Free Pack Channel", "kind": "lv_gated"},
    {"chat_id": -1002603132268, "label": "Horny Central", "kind": "mixed"},
    {"chat_id": -1002337833082, "label": "Hagarth's Milf/Gilf", "kind": "lv_gated"},
    {"chat_id": -1002037585790, "label": "GoldenFans18+", "kind": "direct_host", "notes": "terabox single videos"},
    {"chat_id": -1002325514677, "label": "Bunkr albums", "kind": "direct_host", "notes": "t.me/bunkrleaks"},
    {"chat_id": -1003258433993, "label": "Hagarth's big tits", "kind": "lv_gated"},
    {"chat_id": -1003220778547, "label": "Hagarth's Asian's", "kind": "lv_gated"},
    {"chat_id": -1001685767713, "label": "The Outlander", "kind": "mixed", "notes": "LV, mega, siterips"},
    {"chat_id": -1001819558862, "label": "PNP GC", "kind": "lv_gated"},
    {"chat_id": -1003145164056, "label": "Hagarth's Public", "kind": "lv_gated"},
    {"chat_id": -1003271959583, "label": "Hagarth's Big ass", "kind": "lv_gated"},
    {"chat_id": -1002785485759, "label": "FamousLeaks Only", "kind": "lv_gated", "notes": "duplicate LV posts"},
    {"chat_id": -1002043056722, "label": "Dorcel", "kind": "direct_host", "notes": "sophon links"},
    {"chat_id": -1002326423864, "label": "Hagarth's Bimbos", "kind": "mixed", "notes": "LV, admaven, invites"},
    {"chat_id": -1001478363127, "label": "RawDrop Network", "kind": "lv_gated", "notes": "onlyfans free"},
    {"chat_id": -1002733242718, "label": "LV mega scrape", "kind": "mixed"},
    {"chat_id": -1003600056723, "label": "Thot P0st", "kind": "lv_gated"},
    {"chat_id": -1001594921207, "label": "FREE ONLY PACKS", "kind": "direct_host", "notes": "sophon direct links"},
    {"chat_id": -1001761260369, "label": "Mega scrape extra", "kind": "mixed"},
]

# Sample paste / mirror URLs for pipeline testing (post-LV destinations).
MEGA_SCRAPE_PASTE_FIXTURES: list[dict] = [
    {"url": "https://pixeldrain.com/l/XpMdBYoo", "hint_gb": 63, "label": "Chloe surreal"},
    {"url": "https://pastelink.net/8x76kg6y", "label": "pastelink"},
    {"url": "https://justpaste.it/HQOFss", "label": "HQOFs"},
    {"url": "https://rentry.co/3y5yyxzo", "label": "rentry mega"},
    {"url": "https://pastetoday.com/dyfydwd7xb", "label": "pastetoday"},
    {"url": "https://epicload.com/files/gKRzBJj9", "hint_gb": 8.67, "label": "evamarieee zip"},
    {"url": "https://epicload.com/files/DJpOL6VZ", "hint_gb": 12.2, "label": "KARDELEX zip"},
    {"url": "https://rentry.co/2b6ffxg4", "label": "rentry mega"},
    {"url": "https://rentry.co/ikqsc8iw", "label": "rentry mega"},
    {"url": "https://rentry.co/ogxaz8ce", "label": "rentetoday chain"},
]
