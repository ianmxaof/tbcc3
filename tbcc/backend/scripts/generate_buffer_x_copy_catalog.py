#!/usr/bin/env python3
"""
Generate docs/samples/buffer_x_copy/*.json + backend/app/data/buffer_x_copy/*.json
(both — the latter is the runtime-loaded copy per seed_social_copy_templates.py's
DEFAULT_DIR; the former is the historical fallback) — ~100 templates per category.

Phase 3 (2026-08-13) expanded HOOKS from 20 to 90 and rewrote _build() to round-robin
across hooks instead of a random shuffle-and-dedup pick. With only 20 hooks, a 100-body
category averaged ~5 repeats of every opening line (same "first sentence" over and over —
the "many share same short stems" symptom). Round-robin over 90 hooks means the first 90
of the 100 bodies each open with a DISTINCT hook, guaranteed by construction rather than
left to chance — see tests/test_buffer_x_copy_diversity.py, which loads the committed
JSON output of this script and asserts the diversity claim directly.
"""

from __future__ import annotations

import json
import random
import re
from itertools import product, zip_longest
from pathlib import Path

TBCC_ROOT = Path(__file__).resolve().parents[2]  # backend/scripts -> backend -> tbcc
OUT = TBCC_ROOT / "docs" / "samples" / "buffer_x_copy"
RUNTIME_OUT = TBCC_ROOT / "backend" / "app" / "data" / "buffer_x_copy"

HOOKS = [
    # --- original 20 (unchanged) ---
    "you weren't invited.",
    "main hub just moved.",
    "casuals bounce.",
    "the maze has teeth.",
    "scarcity isn't cruelty.",
    "another relay fired.",
    "psy-slop hour:",
    "built TBCC so the firehose doesn't rot.",
    "public face. private hub.",
    "the pipeline doesn't apologize.",
    "filtration is a feature.",
    "you clicked anyway. good.",
    "tourists leave at the gate.",
    "the seduction is friction.",
    "no filler. no apology.",
    "edge lane energy.",
    "the table owns you eventually.",
    "curiosity tax: paid in attention.",
    "the hub stays intentional.",
    "another drop cleared the queue.",
    # --- Phase 3 expansion (2026-08-13) — 70 new stems, same gold delivery/pipeline/
    # curated-dump/no-apology voice as the Telegram lane + PACKS hooks, translated to
    # plain-text Buffer X style (lowercase, short, no emoji/HTML) ---
    "new delivery just cleared customs.",
    "planet express doesn't do delays.",
    "no apology tour. just the folder.",
    "the conveyor doesn't stop for you.",
    "another parcel skipped the queue.",
    "curated, not scraped blind.",
    "someone actually checked this batch.",
    "porn first. paragraphs never.",
    "zero fluff. just the link.",
    "no soft launch. it just landed.",
    "hosts die. this one didn't.",
    "the internet forgot this one.",
    "deleted elsewhere. still here.",
    "the gate keeps tourists out.",
    "rotation moves fast today.",
    "not everyone gets this drop.",
    "this post won't own the feed forever.",
    "curated at scale, not random.",
    "hand-selected, daily rotation.",
    "imagine having this local.",
    "one tap from the whole stack.",
    "skip the sketchy mirrors.",
    "your drive, your rules.",
    "cheaper than wasting your night.",
    "less than another empty scroll.",
    "the network keeps growing.",
    "pipeline's hot this week.",
    "early stack energy right now.",
    "access before the public push.",
    "the ones here now will understand later.",
    "one lane, full stack in the footer.",
    "more than another chat.",
    "not on the list. showed up anyway.",
    "no corporate bird speak here.",
    "self-aware filth, no pr department.",
    "the receipt is the link below.",
    "every parcel gets logged first.",
    "someone signed off on this batch.",
    "tagged and shipped, not dumped.",
    "this one's heavy. not a teaser.",
    "bigger than the usual rotation.",
    "the gate's quick if you trust it.",
    "one gate, one folder, repeat.",
    "the key's right there. turn it.",
    "no maze, no tricks, one door.",
    "you already know why you're here.",
    "not for everyone reading this.",
    "some lanes stay surface level.",
    "timestamp this one. it's fresh.",
    "every day a new batch clears.",
    "this delivery is today's, not yesterday's.",
    "rotation, not repeat, every time.",
    "the relay fired again just now.",
    "storage to pool to your feed.",
    "signal relayed, blink and you missed it.",
    "the belt keeps moving regardless.",
    "no ceremony, just the drop.",
    "straight to the point, no preamble.",
    "raw drop, no intro necessary.",
    "the folder is the whole pitch.",
    "built, not borrowed, not stolen.",
    "months in the pipeline, one drop.",
    "hand-picked before it hit the feed.",
    "the labor so you don't scroll garbage.",
    "created, not copied, ever.",
    "the receipt below is the proof.",
    "mega batch, not a snack drop.",
    "sized for serious unlocks only.",
    "a mountain, not a molehill.",
    "know the route, you've done this.",
]

CLOSERS_LOOT = [
    "{lootgod} · hub {hub}",
    "{lootgod_free} · map {allmylinks}",
    "DM pull {lootgod} · keys @aofsubscriptions_bot",
    "card reveal → album in DM · {lootgod}",
    "five free rolls then the table · {lootgod_free}",
    "goblin grants blink into lanes · {lootgod}",
    "loot keys live on {hub} · rolls {lootgod}",
]

CLOSERS_SPICY = [
    "{spicy} · hub {hub}",
    "trial photo + chat · {spicy}",
    "upload → chat → unlock · {spicy}",
    "owned bot first · {spicy} · map {allmylinks}",
    "DM {spicy} · revshare optional {affiliate}",
    "free trial in DM · {spicy} · stack {allmylinks}",
]

CLOSERS_PAIRED = [
    "{lootgod} + {spicy} · hub {hub}",
    "rolls {lootgod_free} · trial {spicy} · map {allmylinks}",
    "loot table {lootgod} · spicy DM {spicy}",
    "two bots one maze · {lootgod} · {spicy}",
    "keys on loot · chat on spicy · {hub}",
]

CLOSERS_NETWORK = [
    "full map {allmylinks} · hub {hub}",
    "every lane one addlist · {hub} · {allmylinks}",
    "LOOT · AI · TABOO · VOYEUR — {hub}",
    "one network arrogant pipeline · {allmylinks}",
    "finish on Telegram · {hub} · {allmylinks}",
]

CLOSERS_AFFILIATE = [
    "revshare lane · {affiliate} · hub {hub}",
    "coins before cash · {affiliate} · map {allmylinks}",
    "affiliate tools on X · {affiliate} · AOF {hub}",
    "try {affiliate} · stack {allmylinks}",
    "free credits · {affiliate} · hub {hub}",
]

MID = [
    "you won't.",
    "act accordingly.",
    "zero tourist energy.",
    "that's the point.",
    "you're still here.",
    "good.",
    "no explanation needed.",
    "the clock is real.",
    "impatient people fund the network.",
    "another step slightly harder.",
]


def _unique(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _build(category: str, closers: list[str], extra_body: str = "") -> list[dict]:
    """
    Round-robin across HOOKS (not a random shuffle-and-dedup pick) so first-sentence
    diversity is guaranteed by construction: with len(HOOKS)=90 and a 100-body cap, the
    first 90 bodies each open with a distinct hook before any hook repeats. The old
    approach (shuffle the full hook x mid x closer product, dedup on the full body) could
    land 100 bodies drawn from as few as 20 hooks with heavy repeats — exactly the "many
    share same short stems" symptom this rewrite fixes.
    """
    mid_closer_combos = list(product(MID, closers))
    per_hook_bodies: list[list[str]] = []
    for hook in HOOKS:
        local = list(mid_closer_combos)
        random.shuffle(local)
        bodies_for_hook = []
        for mid, closer in local:
            body = f"{hook} {extra_body} {mid} {closer}" if extra_body else f"{hook} {mid} {closer}"
            bodies_for_hook.append(body)
        per_hook_bodies.append(bodies_for_hook)
    random.shuffle(per_hook_bodies)  # randomize which hook's group leads each round

    raw: list[str] = []
    for round_items in zip_longest(*per_hook_bodies, fillvalue=None):
        for item in round_items:
            if item is not None:
                raw.append(item)

    bodies = _unique(raw, 100)
    return [
        {
            "category": category,
            "surface": "x_buffer",
            "body": b,
            "image_hint": "promo_pool" if i % 7 == 0 else "none",
            "max_uses_before_demote": 2,
        }
        for i, b in enumerate(bodies)
    ]


def first_sentence(body: str) -> str:
    """Everything up to and including the first '.' or ':' followed by a space — matches
    how HOOKS entries are written (each ends in '.' or ':'). Used only to verify/report
    diversity; not used by _build() itself."""
    m = re.match(r"^(.*?[.:])\s", body)
    return m.group(1) if m else body.split(" ", 1)[0]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    RUNTIME_OUT.mkdir(parents=True, exist_ok=True)
    catalogs = {
        "lootgod.json": _build("lootgod", CLOSERS_LOOT, "Loot God: card reveal → album."),
        "spicy.json": _build("spicy", CLOSERS_SPICY, "Spicy companion: trial photo + chat."),
        "paired_dual_cta.json": _build("paired", CLOSERS_PAIRED),
        "network.json": _build("network", CLOSERS_NETWORK),
        "affiliate.json": _build("affiliate", CLOSERS_AFFILIATE),
    }
    for name, items in catalogs.items():
        payload = json.dumps({"category": items[0]["category"], "templates": items}, indent=2)
        diversity = len({first_sentence(it["body"]) for it in items})
        for out_dir in (OUT, RUNTIME_OUT):
            (out_dir / name).write_text(payload, encoding="utf-8")
        print(f"wrote {name}: {len(items)} templates, {diversity} unique first-sentence hooks -> {OUT} + {RUNTIME_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
