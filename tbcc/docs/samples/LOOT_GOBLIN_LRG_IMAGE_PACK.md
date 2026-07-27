# Loot Goblin — LRG image + copy pack

Reference art: `loot_goblin_lrg_reference_grid.png` (2×2 neon-noir grid).  
Apply **image overlay** in Gemini; pair with **Telegram caption** below. No Linkvertise on goblin claim paths.

---

## Image overlay (for Gemini — bake into art)

Use a **top band** (~18% height) with high contrast. Suggested type:

| Field | Text | Notes |
|-------|------|--------|
| **Header title** | `LOOT GOBLIN` | All caps, bold condensed sans or faux-Genesis chrome |
| **Tagline** | `BLINK · TAP · DM` | Under title, letter-spaced |
| **Embedded description** | `Stolen signal on now-playing. ~45s to claim. First 5 taps → free pull in @aof_lootgod_bot.` | 2 lines max; bottom-left or top band under tagline |
| **Micro legal** | `18+ · NO FORWARDS` | Small, bottom-right (optional) |

**Placement notes for Gemini**
- Keep face + boombox readable; text lives in **letterbox bars** (top black bar + thin bottom bar), not over the mask eyes.
- Palette: hot magenta / toxic green / chrome silver on near-black.
- Do **not** bake Telegram buttons, `@handles`, or QR codes — CTA stays in caption.

### Overlay variant B (shorter, busier art)

- Title: `👺 LOOT GOBLIN`
- Tagline: `HE HEARD THE SONG. HE STOLE THE DROP.`
- Description: `Random AOF lane · 45 second window · cap 5`

### Overlay variant C (LGG cross-sell)

- Title: `LOOT GOBLIN × LOOT GOD`
- Tagline: `CATCH THE BLINK — ROLL THE TABLE`
- Description: `Goblin = free DM taste. Full tiers on the bot after.`

---

## Telegram caption (LRG commons / bulletin — paste with image)

```html
👺 <b>LOOT GOBLIN</b> — <i>blink · tap · DM</i>
━━━━━━━━━━━━━━━━━━

While the network is <b>listening</b>, a goblin can <b>blink</b> into a random AOF lane — boombox on his back, stolen signal in the air. He does <b>not</b> dump loot in chat. He leaves a button.

<b>How to catch him</b>
1. Watch for <b>👺 Loot goblin!</b> (often on a <b>now playing</b> scrobble).
2. Tap <b>Claim loot</b> within ~<b>45 seconds</b>.
3. First <b>5</b> unique tappers get a <b>complimentary pull</b> in DM.
4. Opens <b>@aof_lootgod_bot</b> — same family as a free pull (tier-capped teaser).

<b>Loot God Game</b> — tier card → spoiler album in DM. Five free rolls ever; then keys / Stars on the bot.

👉 <a href="https://telegram.me/aof_lootgod_bot?start=loot_free">Free taste — @aof_lootgod_bot</a>

<i>No Linkvertise on goblin drops. Claim links stay clearnet. Don’t forward goblin loot.</i>
```

---

## Sega Genesis–inspired cover prompts (clean art — no baked UI text)

Style lock for all: **1991 Japanese box art energy** — bold ink outlines, limited 32-color palette, ordered dithering, CRT scanline hint optional, **cartridge-box vertical 3:4**, dramatic perspective, readable silhouette at thumbnail.  
**Negative:** photoreal, 3D render, readable English paragraphs, Telegram UI, watermarks, copyrighted mascots.

### 1 — `LOOT GOBLIN: LASER VAULT` (tunnel chase)

```
Sega Genesis box art, 1991 Japanese game cover illustration. Short muscular green goblin in red oni demon mask,
iron chain harness, wooden treasure chest on back with chrome boombox (magenta speaker cones). Sprinting left through
a white-and-red laser security tunnel, motion streaks, purple loot cards fanning behind. Palette: black, crimson,
neon magenta, toxic green. Bold black outlines, ordered dither shading. Empty title space top third. No text, no logos.
```

### 2 — `LOOT GOBLIN: PORTAL ALLEY` (fiery escape)

```
Genesis 16-bit box art. Goblin thief with red hannya mask and boombox-backpack bursting out of a blazing orange-white
portal in a rain-slick cyber alley. Giant spectral mask looms inside the portal. Floating purple trading cards with
lock icons. Dark brick, red neon kanji-like glyphs (abstract, not readable). High contrast, poster composition, no text.
```

### 3 — `LOOT GOBLIN: NEON DOWNPOUR` (puddle splash)

```
1990s Sega cartridge cover painting. Low-angle action: goblin runner splashing through alley puddle, rain lashes,
boombox vibrating, chest bouncing. Red neon signs on wet walls, purple loot cards orbiting. Green skin, black tactical
pants, chain straps. Limited palette dither, dramatic rim light. Title-safe empty band at top. No letters, no UI.
```

### 4 — `LOOT GOBLIN: CARD TRAIL` (rear chase / highway)

```
Genesis box art rear-chase scene. Goblin fleeing down dark alley on glowing red light trail; loot cards laid on ground
like stepping stones (lock and lightning icons abstract). Boombox on chest, demon mask glancing back. Speed lines,
magenta fog, black void depth. 16-bit color banding aesthetic. Composition for vertical box. No text baked in.
```

### 5 — `LOOT GOBLIN: BOSS RUSH` (bonus — arena face-off)

```
Sega Genesis inspired boss-key art. Goblin perched on speaker stack, mask glowing, cards orbiting like satellites.
Silhouetted crowd of channel-door arches (empty rounded rectangles) in arena background. Lightning from boombox.
Poster dynamism, thick outlines, hot pink vs deep violet. Empty header for later LOOT GOBLIN logotype. No text.
```

### 6 — `LOOT GOBLIN: MEGA DRIVE` (bonus — title screen fantasy)

```
Fake Mega Drive title screen illustration (no actual SEGA trademark). Moonlit city skyline, goblin mid-leap between
rooftops, boombox trail of magenta sound waves. Card suit motifs abstract. Starfield, scanline overlay subtle.
Composition centered for 4:3 TV frame. Leave center lower third empty for future HTML caption. No readable words.
```

---

## Pin checklist (Loot Room commons)

1. Composite final art (Gemini overlay above).
2. Post **photo + caption** to Loot Room commons / bulletins topic.
3. **Pin** the post (bot needs pin rights in Loot Room).
4. Optional: update scheduler row `AOF LOOT ROOM — Goblin + LGG explainer (pinned)` with `attachment_urls_json` / media import for re-pin on deploy.

Island-only recommended for live pin (see `docs/REVENUE_ISLAND.md`).
