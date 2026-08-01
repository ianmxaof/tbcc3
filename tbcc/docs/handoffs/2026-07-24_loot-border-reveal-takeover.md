# Claude Code Handoff — Loot Border Reveal (AOF LOOT GOD)

**Date:** 2026-07-24  
**Repo:** `C:\Powercore-repo-main\telegram_bot2\tbcc`  
**Island:** `root@5.161.53.91` (Docker: `infra-api-1`, `infra-worker-1`, `infra-loot_bot-1`)  
**Reverse report required:** `tbcc/docs/handoffs/2026-07-24_loot-border-reveal_report.md` after each phase

---

## Paste this block into Claude Code

```
# TBCC Loot Border Reveal — Lane C Takeover

## Goal (definition of done)

A `/roll` or paid key roll in @aof_lootgod_bot delivers an animated tier card that:
1. Uses the **brushed_metal_stasis_sparkle** border pair (open once → stasis loop) — NOT legacy static `mag-*.png` frames or background-loop fallback
2. Shows the **rolled NSFW center still** filling the border window (with slight bleed under chrome)
3. Has **no chroma artifacts**: no magenta/pink matte, no green/red bars, no pixelized black holes in border metal
4. Has **stamps aligned** to border plates: brand (top-left), badge stack (top-right), name on nameplate, tagline in footer strip below nameplate
5. Key rolls that fail card delivery **compensate** (+24h loot key) and do not leave user with zero loot when media is recoverable

Verify on island after deploy with a real `/roll` and inspect delivery notes in API logs.

## Scope

### In scope
- `backend/app/services/loot_border_reveal.py` — chroma mux, pair picking, denylist
- `backend/app/services/loot_tier_card_assets.py` — `compose_reveal_border_layers`, stamps, `build_reveal_card_mp4`
- `backend/app/services/loot_border_profiles.py` — plate geometry for brushed_metal
- `backend/app/services/loot_border_plates.py` — auto-detect plates from stasis ref frame
- `backend/app/services/loot_preview_delivery.py` — delivery path, inline encode, fallbacks
- `backend/app/services/loot_reveal_video.py` — legacy loop path (only when border reveal OFF)
- `backend/app/services/subscription_access.py` — `compensate_loot_key_card_failure`
- `backend/app/api/loot.py`, `backend/bots/loot_bot.py` — key roll failure messaging
- `backend/tests/test_loot_border_reveal.py`, `test_loot_stamp_layout.py`, `test_loot_card_fallback.py`
- `infra/env.revenue-island.example` — ensure border env vars documented
- Island deploy: env vars, asset persistence, `docker cp` or image rebuild
- Media load reliability for center still (`_load_media_bytes` in loot_preview_delivery)

### Out of scope
- New border art generation / Gemini imports (unless needed to replace bad clips)
- Buffer cross-post, Kit email, growth flywheel
- Full loot pool re-import (unless blocking center image — then minimal repair only)
- GHCR image rebuild (nice-to-have; hot-patch acceptable if documented)

## Critical gotcha discovered 2026-07-24

**`TBCC_LOOT_BORDER_REVEAL` is NOT set in the live `infra-api-1` container.**

Verified on island:
```
docker exec infra-api-1 python -c "from app.services.loot_border_reveal import loot_border_reveal_enabled; print(loot_border_reveal_enabled())"
# → False
```

Env has `TBCC_LOOT_REVEAL_VIDEO=1` and `TBCC_LOOT_REVEAL_VIDEO_CELERY=1` but **missing** `TBCC_LOOT_BORDER_REVEAL=1`.

Result: production rolls use the **old static frame compositor** (`compose_reveal_card` + `mag-*.png` frames) or **celery background-loop video** — NOT the animated border clips. This explains user report: "no resemblance to any of the borders."

**Fix first:** set `TBCC_LOOT_BORDER_REVEAL=1` in island compose/env and recreate api + loot_bot. Confirm `loot_border_reveal_enabled()` → True.

## Architecture (intended pipeline)

```
roll → loot_preview_delivery._send_loot_preview_to_chat_inner
  → _load_media_bytes(row) → center_jpeg
  → build_reveal_card_mp4 (INLINE on API when border mode — no Celery)
      → pick_border_pair() → brushed_metal only (legacy border-001/002/003 denied)
      → compose_reveal_border_layers(size=512) → center JPEG + stamp PNG
      → mux_border_reveal_mp4 (ffmpeg):
           [0] center still (looped)
           [1] open clip (chromakey magenta, enable 0..open_dur)
           [2] stasis clip (chromakey, looped, enable >= open_dur)
           [3] stamp overlay
  → send_video (non-looping) with tier opening HTML + effects
```

Chroma: `0xFF00FF`, similarity **0.22**, blend **0.03** (0.38 eats grey metal → black holes).

Border assets on island:
```
/app/app/data/loot_tier_cards/borders/open/
/app/app/data/loot_tier_cards/borders/stasis/
```
Only **brushed_metal_stasis_sparkle_{open,stasis}.mp4** should be in rotation. Legacy `border-00*.mp4` must stay disabled (code denylist exists; also move to `borders/disabled/`).

## Problems we're solving (user-visible)

| Symptom | Likely cause |
|--------|----------------|
| Card looks like random static frame (teal/brown), not metal border animation | `TBCC_LOOT_BORDER_REVEAL` off → static `mag-*.png` path |
| Magenta/pink center, black pixel holes in chrome | Chroma too aggressive OR wrong border clip without profile |
| Green/red vertical bars beside card | Failed chroma / wrong encode path / entity too large partial send |
| Center image missing (black/magenta void) | `_load_media_bytes` failed — stale saved message IDs |
| Stamps off-center, tagline on nameplate | Stamp geometry; footer_plate split added in local code |
| Open animation repeats (ping-pong) | Must use timeline overlay + `send_video` not looping `send_animation` |
| Key roll: "no loot delivered" | All preview media skipped; see logs below |
| Bot stuck "packing your pull" | API wedged, Celery timeout, Telethon sqlite lock |

## Error log history (island, recent)

```
loot reveal video celery failed: The operation timed out.
loot preview skip media id=7187: 
loot preview skip media id=7160: Saved message 18408 not found or has no media
loot preview skip media id=4488: media id=4488 has no local file and no saved message id
loot preview delivery telegram error chat=7787282561: Request Entity Too Large
```

Earlier session (pre-fix):
```
loot border reveal celery failed: 'app.workers.loot_reveal_video_worker.build_reveal_card_mp4_task'
reveal center from roll media skipped media_id=... Saved message not found
```

**Media IDs to investigate:** 7187, 7160 (saved msg 18408), 4488

**Scripts that may help:**
- `backend/scripts/spike_saved_message_probe.py`
- `backend/scripts/spike_loot_pool_health.py`
- `backend/scripts/repair_loot_pool_channels.py`
- `backend/scripts/quarantine_stale_loot_saved_sql.py`

## Local code state (Cursor session — may not all be on island)

Recent fixes in repo (verify deployed):
- `loot_border_reveal.py`: chroma 0.22/0.03, denylist `border-001,002,003`, profile-only rotation, open/stasis timeline mux
- `loot_preview_delivery.py`: skip Celery for border mode, inline `build_reveal_card_mp4`, still JPEG fallback
- `loot_tier_card_assets.py`: window paste with 2.5% bleed, stamps at `reveal_video_size()`, `footer_plate` for tagline below nameplate
- `loot_border_profiles.py`: `BRUSHED_METAL_STASIS_SPARKLE` plate rects + `footer_plate`

Tests (run locally):
```
cd tbcc/backend
py -3 -m pytest tests/test_loot_border_reveal.py tests/test_loot_stamp_layout.py tests/test_loot_card_fallback.py -q
```

Spike (local, needs border assets + ffmpeg):
```
cd tbcc/backend
set TBCC_LOOT_BORDER_REVEAL=1
py -3 scripts/spike_border_reveal.py --tier 7 --out reveal-border.mp4
```

## Island deploy notes (fragile)

- Hot-patch: `scp` to `/opt/tbcc/backend-src/app/services/` then `docker cp` into `infra-api-1` and `infra-loot_bot-1`
- `docker compose recreate` **wipes** hot patches and may reset border asset dirs
- `ffmpeg` must exist in api container: `docker exec infra-api-1 which ffmpeg`
- Worker may lack border modules if image stale — border encode should run on **API** only
- Set env in compose `.env` or stack file, not only `docker cp`

**Deploy checklist:**
1. `TBCC_LOOT_BORDER_REVEAL=1`
2. `TBCC_LOOT_REVEAL_VIDEO=1`
3. Optional: `TBCC_LOOT_BORDER_PAIR=brushed_metal_stasis_sparkle` (force pair)
4. Consider `TBCC_LOOT_REVEAL_VIDEO_CELERY=0` for border path (API inline is canonical)
5. Restart `infra-api-1`, `infra-loot_bot-1`
6. Confirm: `pick_border_pair()` returns only brushed_metal pair
7. Real roll + check logs for `tier card video:border open=...`

## Phases

### Phase 1 — Unblock production path (env + verify border mode ON)
- Add `TBCC_LOOT_BORDER_REVEAL=1` to island env/compose
- Deploy latest `loot_border_reveal.py`, `loot_preview_delivery.py`, `loot_tier_card_assets.py`, `loot_border_profiles.py`
- Archive legacy `border-00*.mp4` to `borders/disabled/`
- Verify `loot_border_reveal_enabled()` True, one test encode on island
- **Verify:** spike or manual python compose on island; log shows border note not static/celery loop
- **Report:** `docs/handoffs/2026-07-24_loot-border-reveal_report.md` phase 1 — STOP for ACK

### Phase 2 — Visual parity with static cards
- Confirm chroma 0.22, center fills window, stamps on plates, footer below nameplate
- Fix any remaining stamp geometry from stasis ref frame
- Ensure MP4 size under Telegram limit (512, crf 23; watch "Request Entity Too Large")
- **Verify:** pytest + visual still from `mux_border_reveal_still_jpeg`
- **Report:** phase 2 section — STOP for ACK

### Phase 3 — Media load reliability (center image + key rolls)
- Triage media 7187, 7160, 4488 — saved message vs local file
- Ensure roll doesn't fail entirely when one media row bad; card still sends with pool fallback center if roll media missing
- Key compensation when `tier_card_delivered` false
- **Verify:** pool health script; test roll with known-good media id
- **Report:** phase 3 section — STOP for ACK

### Phase 4 — Persistence (optional but recommended)
- Volume-mount `loot_tier_cards/borders` in compose so recreates don't lose assets
- Bake border reveal modules + ffmpeg into GHCR image
- Document in `infra/env.revenue-island.example`
- **Report:** final summary + operator runbook

## Working agreement

- Branch: create `fix/loot-border-reveal` from current main/feat branch
- Commit per phase with clear messages; do not push unless user asks
- After each phase: write reverse report, stop, wait for Cursor ACK
- Do not commit secrets (.env tokens visible in container env — do not copy to repo)

## Reference files

- Prior loot card work: `docs/handoffs/2026-07-20_loot-reveal-card_report.md`
- Border import: `backend/scripts/import_loot_border_animations.py`
- Env example: `infra/env.revenue-island.example` (lines 42–48)
- Bot: `@aof_lootgod_bot` / TBCC_LOOT_BOT_TOKEN in island env

## Success screenshot target

Animated card should match local spike quality:
- Brushed dark metal frame, cyan side accents, shield badge plate
- Center: rolled photo filling window
- Stamps: AOF LOOT + @aof_lootgod_bot centered on brand plate; TIER N / World / X-Y on badge; NAME on nameplate; tagline in black footer strip
- Open animation plays once (~1.6s), then stasis sparkles loop (~6s), video does not loop on Telegram
```

---

## Quota reminder

Run `/usage` in Claude Code before starting — check weekly cap and 5-hour window. Pull visual judgment / stamp layout tuning back to Cursor (Lane B) if Sonnet struggles with plate geometry.

## Lane note

Phases 1–3 are Lane C grind (env, deploy, media triage, tests). Phase 2 stamp alignment may need Lane B eyeball against static `compose_reveal_card` reference.

## Reverse report

Claude Code must write `tbcc/docs/handoffs/2026-07-24_loot-border-reveal_report.md` after each phase, then stop. User returns to Cursor with `/cc-report` or "read the CC report."
