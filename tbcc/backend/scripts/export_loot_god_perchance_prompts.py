"""Write one-click Perchance prompts for loot tiers 1–10 (explicit center + value ladder).

  py -3.13 scripts/export_loot_god_perchance_prompts.py

Output: app/data/loot_tier_cards/perchance-tier-NN-*.txt

Design rules (learned the hard way):
- ONE square card only — never filmstrip / 5-panel / grid (model will obey the loudest conflict).
- Explicit adult center art escalates trash → godroll (loot pool needs garbage AND premium).
- UI text is BEST-EFFORT: prefer blank dark nameplate over gibberish. Telegram caption stamps real names.
- Quality primer is BAND-scoped (T1 is NOT 8K masterpiece).
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "loot_tier_cards"

OUTPUT = (
    "OUTPUT: ONE image. Aspect ratio 1:1 square. "
    "Single complete AOF LOOT trading card. "
    "No grid. No filmstrip. No collage. No stacked panels. No sheet of mini-cards."
)

CHROME = """LAYOUT LOCK — AOF LOOT GOD CARD (same chrome every tier; center sells value):
FORMAT: 1:1 square trading-card.
FRAME: dark chrome / wet vinyl border with thin neon accent (listed per tier).
TOP-LEFT: small distressed "AOF LOOT" wordmark if readable — else blank metal plate.
TOP-RIGHT: try exact "TIER N · WORLD" — if typography fails, blank dark plate (NO gibberish).
CENTER WINDOW ONLY: EXPLICIT adult erotic SUBJECT fills the inner window (nudity/sex OK for adults).
  Do not let the subject cover the frame, wordmark, tier plate, or bottom nameplate.
OVERLAY: light ASCII / terminal residue in corners only (box-drawing, rarity pips, "ROLL OK") — never cover UI.
BOTTOM BAND: try exact NAME + TAGLINE — if typography fails, leave a blank dark nameplate (NO fake letters).
OPTIONAL BADGES: "RESTRICTED" / "SPOILER" / "ADULT LANE" as chrome only.
NO QR. NO t.me / telegram.me links in the image.
NO cartoon. NO childish / underage subjects. Gritty film grain OK.
Adults only (18+)."""

NEGATIVE_BASE = (
    "grid of cards, filmstrip, collage, stacked panels, sheet of mini-cards, "
    "gibberish text, fake latin letters, misspelled tier names, wrong tier number, "
    "QR codes, t.me links, telegram.me links, cartoon, anime, childish subjects, "
    "child, children, minor, underage, teen, loli, watermark, logo spam, "
    "blurry UI mush covering chrome, softcore-only when explicit was requested"
)

TIERS: list[dict] = [
    {
        "n": 1,
        "slug": "crumb",
        "name": "CRUMB",
        "world": "1-1",
        "tagline": "Barely a taste. Still counts.",
        "band": "trash",
        "neon": "dull grey-green neon, sparse dust accents, cheapest rim",
        "mood": "trash loot — still filthy",
        "quality": (
            "QUALITY BAND = TRASH: phone-cam / dirty mirror, awkward crop, soft focus OK, "
            "harsh flash or fluorescent buzz, imperfect skin, cheap motel/bathroom grit. "
            "Throwaway garbage content — still explicit adult. NOT a masterpiece. NOT studio 8K."
        ),
        "subject": (
            "{ugly fluorescent bathroom, adult woman on dirty toilet lid, awkward phone flash, "
            "trashy nude, bored-horny face, litter on floor|"
            "cheap motel bathroom mirror selfie, adult woman half-nude, toothpaste spit on sink, "
            "bad angle, explicit garbage vibe|"
            "filthy bathroom stall, adult woman pants around ankles, phone cam from above, "
            "harsh light, trash loot energy}"
        ),
        "forbid": "gold chrome, luxury frame, studio beauty lighting, godroll polish, sealed foil pack only",
    },
    {
        "n": 2,
        "slug": "peek",
        "name": "PEEK",
        "world": "1-2",
        "tagline": "Skirt lifts. Nothing promised.",
        "band": "trash",
        "neon": "cool blue neon, voyeur edge glow",
        "mood": "almost-caught trash peek",
        "quality": (
            "QUALITY BAND = TRASH: phone grain, doorway/mirror voyeur, still low value. "
            "Explicit peek. NOT premium production."
        ),
        "subject": (
            "{door cracked, voyeur peek of adult woman lifting skirt no panties, "
            "cool blue hallway light, phone grain|"
            "mirror edge side-boob flash, adult woman startled, almost-caught, cheap apartment|"
            "window blinds peek, adult woman changing, sideboob + hip, trash voyeur}"
        ),
        "forbid": "blood-red gold boss frame, sealed pack only, SFW silhouette only",
    },
    {
        "n": 3,
        "slug": "leak",
        "name": "LEAK",
        "world": "1-3",
        "tagline": "Someone left the door cracked.",
        "band": "low",
        "neon": "sickly amber neon, steam film",
        "mood": "leaked-nudes scandal heat",
        "quality": (
            "QUALITY BAND = LOW: amateur leak / locker-cam, bodies readable, still grit. "
            "Explicit. Not VIP."
        ),
        "subject": (
            "{locker room steam, adult woman nude towel dropped, amber light, leaked-nudes aesthetic|"
            "bathroom steam leak cam, adult athletic woman full frontal, wet tile|"
            "phone propped recording, adult woman stripping, amateur scandal heat}"
        ),
        "forbid": "trash toilet only, godroll confetti, sealed redacted polaroid with no body",
    },
    {
        "n": 4,
        "slug": "throb",
        "name": "THROB",
        "world": "2-1",
        "tagline": "The room starts breathing with you.",
        "band": "low",
        "neon": "pulse-red neon inner edge, heartbeat glow",
        "mood": "body-heat macro need",
        "quality": (
            "QUALITY BAND = LOW–RISING: intimate macro, sweat sheen, explicit anatomy focus, "
            "phone-to-amateur still OK."
        ),
        "subject": (
            "{extreme close-up aroused wet pussy or erect cock, pulse-red practical light, precum/wet gloss|"
            "adult body heat macro, sweat sheen, throbbing need, shallow DOF|"
            "hands spreading, explicit genital focus, heartbeat mood}"
        ),
        "forbid": "empty sealed pack, distant room with no subject, softcore tease only",
    },
    {
        "n": 5,
        "slug": "drip",
        "name": "DRIP",
        "world": "2-2",
        "tagline": "Mid-heat. You're not leaving yet.",
        "band": "mid",
        "neon": "hot-pink neon on wet black vinyl",
        "mood": "sticky club mid-tier hunger",
        "quality": (
            "QUALITY BAND = MID: club/VIP heat, cleaner lighting, wet vinyl, hotter framing. "
            "Explicit. Rising value."
        ),
        "subject": (
            "{adult woman on black vinyl, legs spread dripping, hot-pink neon, club mid-tier|"
            "wet hair and body, natural tits, filthy pose on sticky couch, neon drip|"
            "club bathroom sink fuck tease escalating to explicit, mid heat}"
        ),
        "forbid": "bathroom trash only, sealed condensation pack with no adult, SFW oil/rain only",
    },
    {
        "n": 6,
        "slug": "soak",
        "name": "SOAK",
        "world": "3-1",
        "tagline": "Mixed media. Density climbing.",
        "band": "mid",
        "neon": "orange chrome, VIP corridor weight",
        "mood": "denser haul, after-hours VIP",
        "quality": (
            "QUALITY BAND = MID+: coupled / denser explicit action, orange neon VIP, "
            "readable penetration / fluids OK."
        ),
        "subject": (
            "{adult couple fucking VIP corridor, orange neon, penetration visible, velvet rope|"
            "soaked mixed fluids, denser haul energy, after-hours VIP|"
            "two adults against wall, clothes half-on, explicit density climbing}"
        ),
        "forbid": "single empty pack stack, softcore corridor only, crumb plastic rim",
    },
    {
        "n": 7,
        "slug": "filth",
        "name": "FILTH",
        "world": "4-1",
        "tagline": "Vault opens. Packs may follow.",
        "band": "high",
        "neon": "toxic-green vault metal, RESTRICTED chrome",
        "mood": "forbidden archive, production filth",
        "quality": (
            "QUALITY BAND = HIGH: cinematic adult production, sharp skin, strong neon, "
            "dense explicit action, premium filth."
        ),
        "subject": (
            "{toxic-green vault light, adult woman on knees cum-covered, open mouth, tits glazed|"
            "kneeling blowjob aftermath in vault spill light, high production filth|"
            "RESTRICTED vault door open, explicit filth archive, body + packs implied behind}"
        ),
        "forbid": "vault door with no adult, sealed mega sleeve only, softcore classified stamp",
    },
    {
        "n": 8,
        "slug": "ruin",
        "name": "RUIN",
        "world": "5-1",
        "tagline": "Density spikes. No soft landing.",
        "band": "high",
        "neon": "purple/gold chrome overload",
        "mood": "victory mess, no soft landing",
        "quality": (
            "QUALITY BAND = HIGH: dense explicit mess, purple/gold, fucked-raw aftercare energy."
        ),
        "subject": (
            "{chaotic aftercare mess, creampie visible, purple/gold chrome, ruined makeup|"
            "no soft landing — fucked-raw adults, ticket stubs + fluids, density spike|"
            "orgy aftermath pile, explicit ruin, victory mess of bodies}"
        ),
        "forbid": "packaging pile only, softcore holo shards, empty crumb rim",
    },
    {
        "n": 9,
        "slug": "blackout",
        "name": "BLACKOUT",
        "world": "6-1",
        "tagline": "Near-mythic. Modifiers stack mean.",
        "band": "godroll",
        "neon": "ultraviolet slash on near-black",
        "mood": "mythic extreme",
        "quality": (
            "QUALITY BAND = NEAR-GODROLL: almost-surreal photoreal, UV wet chrome, "
            "mean modifiers, extreme consensual adult scene."
        ),
        "subject": (
            "{near-black room ultraviolet slash across extreme consensual bondage scene, explicit anatomy|"
            "mythic blackout sex, UV wet chrome, mean modifiers stacked|"
            "glitch-lit extreme adult scene, almost unseen then revealed}"
        ),
        "forbid": "frosted silhouette only, sealed void pack only, playful confetti without body",
    },
    {
        "n": 10,
        "slug": "godroll",
        "name": "GODROLL",
        "world": "★",
        "tagline": "MAX TIER — screenshot the mess.",
        "band": "godroll",
        "neon": "blood-red + gold chrome max, thickest boss frame",
        "mood": "boss-drop jackpot",
        "quality": (
            "QUALITY BAND = GODROLL: hyper-realistic photographic masterpiece, 8K detail, "
            "razor-sharp pores when visible, cinematic rim light, physically plausible fluids/chrome, "
            "max dopamine explicit finale."
        ),
        "subject": (
            "{godroll finale — adult woman gold body paint, multi-partner cumshot, blood-red + gold chrome|"
            "max tier screenshot-the-mess orgy energy, explicit jackpot|"
            "boss-drop porn flex, covered in cum, victory smirk, 8K chrome}"
        ),
        "forbid": "thin plastic crumb rim, sealed mega-pack packaging only, SFW confetti jackpot",
    },
]


def build_prompt(t: dict) -> str:
    n = t["n"]
    return f"""{OUTPUT}

{CHROME}

TIER BLOCK (spell exactly when text is attempted; blank plate OK if typography fails):
TOP-RIGHT = TIER {n} · {t["world"]}
BOTTOM NAME = {t["name"]}
TAGLINE = {t["tagline"]}
NEON / FRAME ACCENT: {t["neon"]}
MOOD CUE: {t["mood"]}
LOOT VALUE BAND: {t["band"]}

{t["quality"]}

SUBJECT (center window only — this is the loot, not a sealed pack tease):
{t["subject"]}

VARIATION (optional Perchance braces — pick one path per Generate):
Lighting: {{harsh flash|fluorescent buzz|club neon split|rim-only darkness|warm practical lamp|ultraviolet accent}}
Camera: {{phone selfie angle|voyeur doorway|tight window crop|medium card-hero|macro on skin inside window}}
Wear/finish: {{sweat sheen|wet vinyl|messy sheets|steam film|fingerprint on chrome frame}}

Generate now. ONE card. Explicit center matches band {t["band"]}. Lock chrome. Prefer blank nameplate over gibberish.

NEGATIVE: {NEGATIVE_BASE}, {t["forbid"]}
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for t in TIERS:
        path = OUT / f"perchance-tier-{t['n']:02d}-{t['slug']}.txt"
        path.write_text(build_prompt(t).strip() + "\n", encoding="utf-8")
        paths.append(path)
        print(path.name)

    readme = OUT / "PERCHANCE_PROMPTS_README.md"
    readme.write_text(
        """# Loot God Perchance prompts (tiers 1–10)

One file per tier — open, copy all, paste into Perchance. Shape: **Square**. Guidance scales with tier (Lab presets: T1≈7 … T10≈13).

## What these prompts are

- **ONE** 1:1 card (never filmstrip / 5-panel / grid).
- **Explicit** adult center that escalates trash → godroll.
- UI text is **best-effort** — blank nameplate beats gibberish; Telegram captions stamp real names.
- T1–2 quality is intentionally **not** 8K masterpiece.

## Do not paste

Old martyrs / “FIVE cards stacked” / “NO nudity sealed pack” prompts. Those fight the Lab and produce sheets + garbage letters.

## Corpus

Keep **3–5** keepers per tier. Bot uses one `tier-N.png` today — promote your favorite; stash variants in `_inbox/` or `variants/`.

```powershell
cd tbcc\\backend
py -3.13 scripts\\export_loot_god_perchance_prompts.py
```

Or use extension FAB **Loot Cards** → Compose (same library).
""",
        encoding="utf-8",
    )
    print(f"wrote {len(paths)} prompts + {readme.name} -> {OUT}")


if __name__ == "__main__":
    main()
