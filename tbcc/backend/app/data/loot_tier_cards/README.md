# AOF Loot tier cards — reveal art

Each key-roll reveal card is **composited at roll time** into one **opaque JPEG** (no alpha — Telegram Desktop checkerboards RGBA PNGs):

1. Opaque dark square canvas
2. Band NSFW **center**, cover-cropped into the frame’s **inner** window only
3. Layout-biased punched **frame** alpha-composited on top (prefers plates for text)
4. Stamp **AOF LOOT** + `TIER N` + world + name + flavor (reference LOOT ROOM CARDS layout)
5. Scrub residual checker pixels → black, **crop tight to the chrome** (no exterior void)
6. JPEG → `send_photo` + effect cascade (Premium → free 🎉 → bare)

**Animated reveal (optional):** when `TBCC_LOOT_REVEAL_VIDEO=1`, the composited JPEG is muxed over a looping MP4 background and sent via `send_animation` (JPEG fallback if ffmpeg/loops missing).

`migrated-*` sealed seed PNGs are skipped when real stills exist in the band folder.

## Center bands (start here)

| Band | Tiers | Folder | ContentPool (dashboard) |
|------|-------|--------|-------------------------|
| low | 1–5 | `centers/low/` | `LOOT CARD — LOW` |
| high | 6–9 | `centers/high/` | `LOOT CARD — HIGH` |
| godroll | 10 | `centers/godroll/` | `LOOT CARD — GODROLL` |

Fallback order: band folder → legacy `centers/t{N}/` → `centers/_any/` → static `tier-N.png`.

## Bootstrap from AOF AI POOL

```bash
cd tbcc/backend
py -3 scripts/export_ai_pool_to_loot_centers.py              # dry-run
py -3 scripts/export_ai_pool_to_loot_centers.py --execute    # download stills
py -3 scripts/export_ai_pool_to_loot_centers.py --execute --per-band 40
```

Snapshots approved **photos** from `AOF AI POOL` onto disk (and clones rows into the three LOOT CARD pools). This is a **snapshot**, not a live link to the channel library.

## Import borders

```bash
py -3 scripts/import_loot_card_frames.py
```

## Confetti / celebration effect

Reveal `send_photo` uses Bot API `message_effect_id` (private chats only).

- Default: **random** from a curated Premium pool (🩷 😲 ❄ 🌹 🍿 💊 🎉 🍑 ✨ 👾), with ✨ as the named primary.
- Force one id: `TBCC_LOOT_ROLL_EFFECT_ID=5089460564141278042`
- Disable: `TBCC_LOOT_ROLL_EFFECT_ID=off`

If Telegram rejects an effect id (bots often get `Premium_account_required`), delivery cascades: curated id → free 🎉 → bare photo. The card always sends when bytes exist.

## Layout

```
loot_tier_cards/
  frames/frame-*.png
  backgrounds/loop-*.mp4   # animated reveal loops (see generate script)
  centers/low|high|godroll/
  centers/_any/
  tier-1.png … tier-10.png   # legacy static fallback
```

## Animated reveal video

```bash
cd tbcc/backend
py -3.13 scripts/generate_loot_card_background_loops.py   # 5 procedural loops
```

Enable on island/worker:

- `TBCC_LOOT_REVEAL_VIDEO=1` — mux card over loop → `send_animation`
- `TBCC_LOOT_REVEAL_VIDEO_CELERY=1` — encode on Celery worker (CPU isolation)
- `TBCC_LOOT_REVEAL_VIDEO_SECONDS=4` — clip length (2–8)
- `TBCC_LOOT_REVEAL_VIDEO_SIZE=512` — square output px
- `TBCC_LOOT_CARD_BACKGROUNDS_DIR` — override loop folder

Requires **ffmpeg** in the API/worker image (`backend/Dockerfile`).

## Env

- `TBCC_LOOT_TIER_CARD_DIR`
- `TBCC_LOOT_CARD_FRAMES_DIR`
- `TBCC_LOOT_CARD_CENTERS_DIR`
- `TBCC_LOOT_ROLL_EFFECT_ID`

## Loot reveal animated cards (ffmpeg)

```env
# TBCC_LOOT_REVEAL_VIDEO=0
# TBCC_LOOT_REVEAL_VIDEO_CELERY=0
# TBCC_LOOT_REVEAL_VIDEO_SECONDS=4
# TBCC_LOOT_REVEAL_VIDEO_SIZE=512
# TBCC_LOOT_REVEAL_VIDEO_TIMEOUT_S=12
# TBCC_LOOT_CARD_BACKGROUNDS_DIR=
```

Generate placeholder loops: `cd tbcc/backend && py -3 scripts/generate_loot_card_background_loops.py`

## Island deploy

```bash
docker cp app/data/loot_tier_cards/. infra-api-1:/app/app/data/loot_tier_cards/
```
