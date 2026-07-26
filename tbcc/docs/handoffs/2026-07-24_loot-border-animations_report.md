# Claude Code — Loot Border Animations Phases 2–3 — Reverse Report

**Branch:** `fix/loot-border-reveal`
**ACK:** Decision A (HOLD) confirmed — no island/docker work performed. Flag `TBCC_LOOT_BORDER_REVEAL=1` untouched on island.
**Scope observed:** border code + import script + tests + this report only. Did not touch unrelated dirty-tree files (Buffer/Kit/growth/etc. modifications from other lanes were left alone and not committed).

---

## Phase 2 — Import single clips

### Source
`C:\Users\ianmp\Downloads\tbcc\AOF NETWORK\AOF RESOURCES (ZIPS)\AOF LOGOS\_transparent border_gemini\OPEN & STASIS ANIMATIONS\BORDER OPEN ANIMATIONS`
Found on first check — all 14 operator-confirmed source files present, no fallback search needed.

### Run
```
py -3.13 scripts/import_loot_border_animations.py
```
`Done imported=14` (exit 0). All 14 source clips encoded to 512×512 h264 MP4s (preserve-names mode), landing alongside the 3 pre-existing legacy `border-00x` files → **17 total** in `borders/open/`.

### Gap found and fixed
Doctrine (`phase2-plus` doc) calls out `Unix_Commands_on_Windows_Explained.mp4` as denylisted, but the import script doesn't filter at import time (by design — it imports everything in the source dir) and the **pick-time** denylist default in `loot_border_reveal.py` was `"border-001,border-002,border-003"` — it did not contain a token matching `unix_commands`. That stray screen-recording clip would have been eligible for `pick_border_clip()` selection.

Fix: added `unix_commands` to the default `TBCC_LOOT_BORDER_DENY` token list in `_border_deny_tokens()` (`backend/app/services/loot_border_reveal.py`). Added a regression test (`test_pick_border_clip_denies_unix_commands_stray`) mirroring the existing `border-001` denial test.

### Verification
- File count: 17 total in `borders/open/` (13 usable after denylist: 14 imported − 1 `Unix_Commands` − 3 legacy `border-00x`... note the 3 legacy files were already present pre-import, not part of the 14).
- Sizes: 48 KB – 795 KB per clip (small because `--trim` was not passed, i.e. full clip length at 512px/CRF23 — well under the "~2-3 MB pre-trim" estimate, which referred to *source* file size, not encoded output).
- Import script exit 0.

---

## Phase 3 — Rotation + local spike

### Rotation check
```
TBCC_LOOT_BORDER_ALLOW_UNPROFILED=1 pick_border_clip() over 50 draws (seed=42)
```
13 unique clips selected out of 17 on disk — confirms denylist correctly excludes `border-001`, `border-002`, `border-003`, and (post-fix) `Unix_Commands_on_Windows_Explained`.

### Pytest trio
```
cd backend
py -3.13 -m pytest tests/test_loot_border_reveal.py tests/test_loot_stamp_layout.py tests/test_loot_card_fallback.py -q
```
**10 passed**, 2 unrelated deprecation warnings (`datetime.utcnow()` in `test_loot_card_fallback.py` / `subscription_access.py` — pre-existing, not touched).

Also spot-checked `tests/test_loot_border_plates.py` (same feature family, not in the required trio) — **3 passed**.

### Missing `BorderRevealProfile` variants
Per doctrine, this is expected/OK: only `brushed_metal_stasis_sparkle` has a profile (covers the `brushed_metal_stasis_sparkle_open` and `PROJECT_AOF_LOOT_GOD_-_single` clips via `profile_for_border`). The other 11 imported clips (ccx, dxvdx, Metal_border_chr(c)ome_fills, the various `PROJECT_AOF_LOOT_GOD` numbered variants) have no dedicated profile and fall back to the shared plate geometry via `TBCC_LOOT_BORDER_ALLOW_UNPROFILED=1` (default-on in `_border_clip_allowed`). No action taken — matches doctrine.

### Local spike
```
TBCC_LOOT_BORDER_REVEAL=1 py -3.13 scripts/spike_border_reveal.py --tier 7
```
```
clips=17
clip=PROJECT_AOF_LOOT_GOD_—_animat (4).mp4
OK reveal-border.mp4 (255 KB) border clip=PROJECT_AOF_LOOT_GOD_—_animat (4).mp4 play=10.0s
```
Output: `backend/reveal-border.mp4` — tier 7 assets were present locally, so no fallback still was needed. Verified with `ffprobe`: h264, 512×512, 10.0s duration, 261303 bytes. Valid MP4. (Local scratch output, not committed.)

---

## Files changed / committed this phase

All of these were **untracked or modified-but-uncommitted** on disk from the prior lane (Cursor's single-clip refactor, per the takeover doc) — none were previously committed. This phase snapshots them as one coherent, working commit (verified green via the pytest trio + spike, which import the full chain: `loot_border_reveal` → `loot_border_profiles` → `loot_tier_card_assets.compose_reveal_border_layers`):

- `backend/app/services/loot_border_reveal.py` (new) — single-clip `pick_border_clip()` model; this phase added `unix_commands` to default denylist tokens (1-line fix), rest already matched doctrine.
- `backend/app/services/loot_border_profiles.py` (new) — per-border-animation plate geometry profiles.
- `backend/app/services/loot_border_plates.py` (new) — plate/window detection from reference frames.
- `backend/app/services/loot_tier_card_assets.py` (modified, +461/-59) — border-aware compose path (`compose_reveal_border_layers`, badge plate stacking, etc.).
- `backend/scripts/import_loot_border_animations.py` (new) — Phase 2 import script (used above).
- `backend/scripts/spike_border_reveal.py` (new) — Phase 3 local spike script (used above).
- `backend/tests/test_loot_border_reveal.py` (new) — added `test_pick_border_clip_denies_unix_commands_stray` to the existing suite.
- `backend/tests/test_loot_stamp_layout.py`, `backend/tests/test_loot_card_fallback.py` (new).
- `backend/app/data/loot_tier_cards/borders/open/*.mp4` — 13 newly imported usable clips + 3 pre-existing legacy denylisted clips (`border-001/002/003`). **`Unix_Commands_on_Windows_Explained.mp4` was left out of the commit** — it's junk (a screen-recording tutorial, not border art) that happened to sit in the source folder; the denylist token stays in code as defense-in-depth for anyone who re-runs the import locally, but there's no reason to ship the file itself.

Not committed this phase (separate concern, not required by DoD): `test_loot_border_plates.py` — spot-checked (3 passed) but out of the required trio, left for whichever lane owns it.

## Guardrails observed

- Did **not** touch island / SSH / `docker cp` / `deploy-island-live.ps1` / image rebuild.
- Did **not** apply the deprecated pair-model hot-patch.
- Did **not** touch Buffer/Kit/growth-flywheel or other unrelated dirty-tree files (left as pre-existing uncommitted changes from other lanes).
- Did **not** commit `infra/.env.revenue-island` or any secrets.
- Committed selectively: border service code + import/spike scripts + tests + imported clips + this report.

## STOP

Phases 2–3 complete. Awaiting Cursor/operator ACK before any Phase 4 (island deploy) work.
