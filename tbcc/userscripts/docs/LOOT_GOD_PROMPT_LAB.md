# Loot God Card Lab (TBCC extension)

Compose AOF LOOT reveal cards on Perchance **without Tampermonkey**. The suite ships as
`extension/perchance-suite.bundle.js` (built from `packages/perchance-suite/`).

## What you type vs what is locked

| Layer | Editable? | Role |
|-------|-----------|------|
| Border / chrome | No | Single card-game frame + exact `TIER N · world` / NAME / tagline |
| Quality primer | No (per band) | **Trash → godroll** ladder — T1–2 are NOT 8K masterpieces |
| Generator dropdowns | Auto on Compose | Guidance / Extras / Pose escalate by tier |
| Subject | **Yes** | Your NSFW center art (Seed uses tier-specific trash→godroll seeds) |
| Δ 0–3 | Slider | Local rewrite of subject only (lighting → pose → wardrobe) |

Negative prompt bans wrong tier text, QR/t.me, cartoon, **minors** — not nudity.

### Loot-value ladder (why T1 looks like garbage)

| Tiers | Band | Guidance | Intent |
|-------|------|----------|--------|
| 1–2 | trash | 7–8 | Fill the trash pool — toilet/peek grit, phone-cam mess |
| 3–4 | low | 9–10 | Amateur leak / body heat — better than trash, not VIP |
| 5–6 | mid | 11 | Club / VIP sticky mid-tier |
| 7–8 | high | 12 | Cinematic filth production |
| 9–10 | godroll | 13 | Max dopamine finale |

Constant across tiers: Square, NSFW-Realistic, Age 32, Filthy/Horny defaults, chrome layout lock.
Tier-specific: quality primer band, subject seeds, Guidance, Extras (Toilet only on T1), compose note.

**Compose + Apply** also tries to set page dropdowns. Use **Apply page dropdowns** alone if you only want the selects. If Perchance labels differ, set Guidance/Extras manually from the Lab chip.

## Operator flow

1. From `tbcc/userscripts`: `npm run build` (emits `../extension/perchance-suite.bundle.js`).
2. Chrome → Extensions → **Reload TBCC Importer** (v1.40.9+).
3. Open your Perchance generator — lean mode (default ON) kills comments + public gallery and forces NSFW/uncensor. Own generation results stay.
4. FAB **Loot Cards** → pick tier → **Seed subject** (tier-aware) → Δ → **Compose + Apply** (prompt + dropdowns).
5. Generate 3–4 Δ variants; keep one. For T1 expect trashy bathroom garbage — that is correct for the pool.
6. Save as `tbcc/backend/app/data/loot_tier_cards/tier-N.png`.
7. Island: `docker cp tier-*.png infra-api-1:/app/app/data/loot_tier_cards/`

Checklist buttons (1–10) track local progress (`localStorage`). **Mark tier done** after a keeper.

## Clear + instant presets

| Control | What it does |
|---------|----------------|
| **Clear** | Every page `<select>` with a `Default` option → Default; soft-sets Pics/Shape/Guidance; blanks prompt + negative |
| **Instant preset** + **Apply preset** | One-shot: Clear / blank border / this-tier border / T1–T10 full compose |
| **Border blank** | Empty chrome frame (no tier stamp) + all character plugins → Default |
| **Border this tier** | Same + neon/nameplate cues for the selected tier → save `frame-T{n}.png` |
| **Border next →** | Advance tier, apply tier border (bulk loop) |

Offline prompt packs (same text the Lab applies):  
`backend/app/data/loot_tier_cards/border-prompts/` (`frame-T1.txt` … `frame-T10.txt`, `pack.json`).

Perchance `#data=uup1:….gz` share links are **not** importable into the Lab — that blob is Perchance UI state, not our preset schema. Source of truth for instant apply is `generatorPresets` in `loot-god-library.json`.

## Library source

- [`packages/perchance-suite/data/loot-god-library.json`](../packages/perchance-suite/data/loot-god-library.json)
- Loader: `loot-god-library.js` (bundled)

SFW/tease Gemini loot jobs were retired — jobs bar loot lane is now **explicit**.
Prefer **Loot Cards** FAB for God Lab compose. Use **Copy border-only** for a transparent
chrome frame to overlay in code.

## Tonight: get cards into loot rotation

1. Reload TBCC extension after `npm run build` in `tbcc/userscripts`.
2. Perchance → **Loot Cards** FAB → for each tier 1–10: Seed/Δ → Compose → Generate → save `tier-N.png`.
3. Optional: **Copy border-only** once → generate `frame.png` (alpha or #00FF00 center) for code overlay.
4. Copy keepers to `tbcc/backend/app/data/loot_tier_cards/`.
5. Island: `docker cp tier-*.png infra-api-1:/app/app/data/loot_tier_cards/`
6. Smoke a `/roll` on loot bot (tray/island) — do not start a second payment/loot process from agent.

## Module toggle

Pinned TBCC icon → Site tools → **Perchance suite (Loot God Card Lab)**.
