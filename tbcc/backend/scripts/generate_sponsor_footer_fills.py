#!/usr/bin/env python3
"""
Fill SPONSOR_URL / SPONSOR URL / [SPONSOR_URL] placeholders using URLs from promo_bulk_import_adultforce.json.

Run from repo (any cwd):
  python tbcc/backend/scripts/generate_sponsor_footer_fills.py

Writes: tbcc/backend/scripts/sponsor_footers_filled.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
JSON_PATH = SCRIPT_DIR / "promo_bulk_import_adultforce.json"
OUT_PATH = SCRIPT_DIR / "sponsor_footers_filled.md"

# --- Variation set: 25 single-line promos (numbered list from chat; typo SPONSOR URL normalized by filler).
SET_25_LINES: list[str] = [
    'They whispered about the <a href="SPONSOR_URL">rituals</a> performed in Room 207. Now they don\'t whisper anymore.',
    'Your reflection isn\'t smiling. It\'s <a href="SPONSOR_URL">pleading</a>. Help it escape.',
    'The dollhouse came with a hidden compartment. Inside was a note: "Meet me on <a href="SPONSOR_URL">cam</a>. Don\'t be late."',
    'The static on Channel 666...it\'s forming words. It wants you to visit <a href="SPONSOR_URL">her</a>.',
    'Found footage recovered from a missing hiker\'s camera. Last frame: a distorted face saying, "Join the <a href="SPONSOR_URL">circle</a>."',
    'They say laughter is the best medicine. But the sounds coming from <a href="SPONSOR_URL">there</a>...that\'s pure agony.',
    'The basement stairs creak. Not from age, but from anticipation. They\'re waiting for you on <a href="SPONSOR_URL">stage</a>.',
    'Don\'t trust the mirror. It shows what you crave, not what you are. See the truth on <a href="SPONSOR_URL">display</a>.',
    'The abandoned asylum whispers your name. It knows your darkest desires. Fulfill them on <a href="SPONSOR_URL">demand</a>.',
    'Scratching at your window isn\'t the neighbor\'s cat. It\'s the echo of what awaits on <a href="SPONSOR_URL">access</a>.',
    'Sleep paralysis? Nah, it\'s just her <a href="SPONSOR_URL">touch</a>, reaching through the veil.',
    'The Ouija board spelled out one word: "<a href="SPONSOR_URL">Subscribe</a>". Now it won\'t stop moving.',
    'They say eyes are the windows to the soul. But hers...they lead directly to <a href="SPONSOR_URL">forbidden</a> realms.',
    'Your therapist warned you about intrusive thoughts. This isn\'t a thought, it\'s a <a href="SPONSOR_URL">live feed</a>.',
    'Urban legend or reality? Find out on <a href="SPONSOR_URL">site</a>. Viewer discretion advised.',
    'The internet remembers. And what it remembers most about you is your <a href="SPONSOR_URL">fantasy</a>.',
    'They call it a glitch in the matrix. I call it an invitation to <a href="SPONSOR_URL">escape</a>.',
    'Lost connection? No, it\'s a <a href="SPONSOR_URL">signal</a>. A signal from the other side.',
    'Your search history knows too much. It led you here. To <a href="SPONSOR_URL">confession</a>.',
    'The algorithm predicted this. You\'d click. You\'d <a href="SPONSOR_URL">indulge</a>.',
    'Don\'t blame the AI. Blame your <a href="SPONSOR_URL">curiosity</a>. It brought you here.',
    'They said curiosity killed the cat. But satisfaction brought you to <a href="SPONSOR_URL">paradise</a>.',
    'The dark web isn\'t a myth. It\'s a doorway. Step through on <a href="SPONSOR_URL">entry</a>.',
    'Delete your history? Too late. It\'s already playing on <a href="SPONSOR_URL">loop</a>.',
    'Free will is an illusion. You were always meant to find <a href="SPONSOR_URL">release</a>.',
]

# --- Long “grainy security footage” block (cleaned: no markdown **, fixed stray “2 0.”).
SET_LONG_PARAGRAPH = (
    'The grainy security footage shows nothing but a blank room...except for your '
    '<a href="SPONSOR_URL">reflection</a>, changing positions. They say sleep is for the weak. '
    'But the nightmares...they originate from <a href="SPONSOR_URL">reality</a>. '
    'Check [SPONSOR_URL] to wake up. Found a child\'s drawing in the attic. It depicts YOU, '
    'bound and gagged, captioned "<a href="SPONSOR_URL">coming soon</a>". That scratching noise? '
    "It's not rodents. It's fingers clawing to escape the "
    '<a href="SPONSOR_URL">content</a>. Break free with us. Your deepest fears manifested as a website. '
    'Don\'t look away. Face them on <a href="SPONSOR_URL">view</a>. The antique music box plays a lullaby...'
    'but the melody twists, morphing into a <a href="SPONSOR_URL">scream</a>. Hear the full symphony. '
    'They warned you about urban legends. This one\'s real. And it demands '
    '<a href="SPONSOR_URL">payment</a>. In flesh and fantasy. The dollhouse furniture is rearranging itself. '
    'It knows your <a href="SPONSOR_URL">desires</a>. Let\'s play. Your phone vibrates...not a message, '
    'but a pulse. A heartbeat from <a href="SPONSOR_URL">inside</a>. Answer the call. '
    'The flickering streetlight reveals a figure...and then it vanishes. But the '
    '<a href="SPONSOR_URL">invitation</a> remains. The voice in your head isn\'t yours. It belongs to '
    '<a href="SPONSOR_URL">them</a>. Join the chorus. They say mirrors reflect your soul. '
    'Mine shows a glimpse of <a href="SPONSOR_URL">what lurks</a> beyond. The blood moon rises...'
    'and so does <a href="SPONSOR_URL">desire</a>. Unleash it. Responsibly. Your browser history '
    'self-deletes...except for one entry: <a href="SPONSOR_URL">never forget</a>. '
    'The last thing she saw before the blackout was YOUR <a href="SPONSOR_URL">username</a>. '
    'Now it\'s your turn. They say laughter is the best medicine...until the '
    '<a href="SPONSOR_URL">laughter turns</a> to screams. The void calls. It promises '
    '<a href="SPONSOR_URL">completion</a>. Enter if you dare. The abandoned asylum isn\'t silent. '
    'It whispers your <a href="SPONSOR_URL">name</a>, beckoning you closer. The filter distorts reality...'
    'but the truth behind it is far <a href="SPONSOR_URL">more unsettling</a>. Discover it. '
    'They told you not to touch the Ouija board. Too late. It\'s <a href="SPONSOR_URL">typing</a> back. '
    'The news report cuts out mid-sentence, replaced by a single image: '
    '<a href="SPONSOR_URL">your face</a>, contorted in ecstasy. Your dreams bleed into reality. '
    'And the only escape is through <a href="SPONSOR_URL">this portal</a>. '
    'The countdown timer started when you clicked this link. Time is running out on '
    '<a href="SPONSOR_URL">innocence</a>. They say curiosity killed the cat. But satisfaction...'
    'satisfaction is <a href="SPONSOR_URL">served here</a>. The internet remembers everything. '
    'And it wants you to <a href="SPONSOR_URL">remember too</a>.'
)


def load_urls() -> list[str]:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    urls = [str(it["url"]).strip() for it in data.get("items", []) if str(it.get("url") or "").strip()]
    if len(urls) < 25:
        raise SystemExit(f"Expected many URLs in {JSON_PATH}, got {len(urls)}")
    return urls


def fill_placeholders(text: str, urls: list[str], cursor: list[int]) -> str:
    """Replace placeholders one-by-one; cursor[0] walks through urls modulo len."""
    out = text
    placeholders = ("SPONSOR_URL", "SPONSOR URL", "[SPONSOR_URL]")
    while True:
        found_at: tuple[int, str] | None = None
        for ph in placeholders:
            pos = out.find(ph)
            if pos >= 0 and (found_at is None or pos < found_at[0]):
                found_at = (pos, ph)
        if found_at is None:
            break
        _, ph = found_at
        url = urls[cursor[0] % len(urls)]
        cursor[0] += 1
        out = out.replace(ph, url, 1)
    return out


def md_escape_fence_body(s: str) -> str:
    """Avoid breaking markdown fences if body contained ```."""
    return s.replace("```", "``\\`")


def main() -> None:
    urls = load_urls()
    cursor = [0]
    lines_out: list[str] = [
        "# Sponsor relay footers (filled hrefs)",
        "",
        f"Source URLs: `{JSON_PATH.name}` (**{len(urls)}** rows). Placeholders filled in JSON array order, ",
        "repeating from the start when a template needs more links than one rotation.",
        "",
        "---",
        "",
    ]

    n_batches = max(6, (len(urls) + 24) // 25)
    for batch_idx in range(n_batches):
        lines_out.append(f"## Batch {batch_idx + 1}/{n_batches} — 25 single-line footers")
        lines_out.append("")
        for i, tpl in enumerate(SET_25_LINES, start=1):
            filled = fill_placeholders(tpl, urls, cursor)
            global_idx = batch_idx * len(SET_25_LINES) + i
            lines_out.append(f"### Footer #{global_idx}")
            lines_out.append("")
            lines_out.append("```")
            lines_out.append(md_escape_fence_body(filled))
            lines_out.append("```")
            lines_out.append("")
        lines_out.extend(["---", ""])

    lines_out.extend(
        [
            "## Long paragraph footer (single paste)",
            "",
            "```",
        ]
    )
    long_filled = fill_placeholders(SET_LONG_PARAGRAPH, urls, cursor)
    lines_out.append(md_escape_fence_body(long_filled))
    lines_out.extend(["```", ""])

    lines_out.extend(
        [
            "---",
            "",
            "## Stats",
            "",
            f"- Source URLs: **{len(urls)}**",
            f"- Total substitutions (filled placeholders): **{cursor[0]}**",
            "",
        ]
    )

    OUT_PATH.write_text("\n".join(lines_out), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(urls)} source URLs, {cursor[0]} substitutions, {n_batches} batches)")


if __name__ == "__main__":
    main()
