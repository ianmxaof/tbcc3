#!/usr/bin/env python3
"""Generate docs/samples/buffer_x_copy/*.json — ~100 templates per category."""

from __future__ import annotations

import json
import random
import sys
from itertools import product
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "docs" / "samples" / "buffer_x_copy"

HOOKS = [
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
    raw: list[str] = []
    combos = list(product(HOOKS, MID, closers))
    random.shuffle(combos)
    for hook, mid, closer in combos:
        body = f"{hook} {mid} {closer}"
        if extra_body:
            body = f"{hook} {extra_body} {mid} {closer}"
        raw.append(body)
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


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    catalogs = {
        "lootgod.json": _build("lootgod", CLOSERS_LOOT, "Loot God: card reveal → album."),
        "spicy.json": _build("spicy", CLOSERS_SPICY, "Spicy companion: trial photo + chat."),
        "paired_dual_cta.json": _build("paired", CLOSERS_PAIRED),
        "network.json": _build("network", CLOSERS_NETWORK),
        "affiliate.json": _build("affiliate", CLOSERS_AFFILIATE),
    }
    for name, items in catalogs.items():
        path = OUT / name
        path.write_text(json.dumps({"category": items[0]["category"], "templates": items}, indent=2), encoding="utf-8")
        print(f"wrote {path.name}: {len(items)} templates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
