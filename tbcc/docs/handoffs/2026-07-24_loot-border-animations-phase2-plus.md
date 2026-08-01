# Claude Code — Loot Border Animations (single-clip model)

**Updated:** 2026-07-24 — **stasis pairs deprecated**. One MP4 per border covers open + sustain.

## Doctrine change (operator confirmed)

- **Do NOT** use `BORDER STASIS ANIMATIONS/` or `{stem}_stasis.mp4` pairs.
- **Do** use single clips from:
  `C:\Users\ianmp\Downloads\tbcc\AOF NETWORK\AOF RESOURCES (ZIPS)\AOF LOGOS\_transparent border_gemini\OPEN & STASIS ANIMATIONS\BORDER OPEN ANIMATIONS`
- Runtime picks from `borders/open/` only via `pick_border_clip()`.
- Mux: center still + one chroma-keyed border clip + stamps (`mux_border_reveal_mp4`).

## Available source clips (14 files, ~2.3–2.7 MB each)

| File | Notes |
|------|--------|
| `brushed_metal_stasis_sparkle_open.mp4` | Production reference (rename optional) |
| `PROJECT_AOF_LOOT_GOD_-_single.mp4` | Canonical single-clip naming |
| `PROJECT_AOF_LOOT_GOD_-_animat.mp4` | Variants (1)–(4) |
| `PROJECT_AOF_LO4OT_GOD_-_animat (1).mp4` | Typo variants — import as-is |
| `Metal_border_chrome_fills_.mp4` | |
| `Metal_border_chrccome_fills_.mp4` | |
| `ccx.mp4`, `dxvdx.mp4` | |
| `Unix_Commands_on_Windows_Explained.mp4` | Likely stray — consider denylist |

## Phase 1 (ops — unchanged)

Append `TBCC_LOOT_BORDER_REVEAL=1` on island → recreate `api` + `loot_bot` (no rebuild).

## Phase 2 — Import all single clips

```powershell
cd tbcc/backend
py -3 scripts/import_loot_border_animations.py
# Optional cap: py -3 scripts/import_loot_border_animations.py --trim 7.6 --size 512
```

Dest: `app/data/loot_tier_cards/borders/open/*.mp4`

## Phase 3 — Rotation + profiles

- `TBCC_LOOT_BORDER_ALLOW_UNPROFILED=1` (default) — all imported clips rotate until per-stem profiles exist.
- `loot_god` / `project_aof` / `brushed_metal` stems → `BRUSHED_METAL_STASIS_SPARKLE` plate geometry (shared for now).
- Add per-variant `BorderRevealProfile` only when stamp plates diverge (measure stasis frame @ 512px).
- Denylist stray: `TBCC_LOOT_BORDER_DENY=border-001,border-002,border-003,Unix_Commands`

## Phase 4 — Island assets

- `docker cp` or volume-mount `borders/open/` → island
- `TBCC_LOOT_CARD_BORDERS_DIR` if not baked in image
- Spike on island: `TBCC_LOOT_BORDER_REVEAL=1 python scripts/spike_border_reveal.py --tier 7`

## Env

| Var | Default | Meaning |
|-----|---------|---------|
| `TBCC_LOOT_BORDER_REVEAL` | off | Master switch |
| `TBCC_LOOT_BORDER_PLAY_SECONDS` | clip length | Max play duration |
| `TBCC_LOOT_BORDER_ALLOW_UNPROFILED` | `1` | Rotate clips without custom profile |
| `TBCC_LOOT_BORDER_DENY` | border-001,002,003 | Legacy denylist |
| `TBCC_LOOT_BORDER_CLIP` | — | Force one stem substring |

## Tests

```
py -3 -m pytest tests/test_loot_border_reveal.py tests/test_loot_stamp_layout.py tests/test_loot_card_fallback.py -q
```

## Deprecated (do not implement)

- `pick_border_pair()` open+stasis mux (wrapper returns same clip twice for compat only)
- `borders/stasis/` folder
- `import_loot_border_animations.py --stasis-src`

Report: `docs/handoffs/2026-07-24_loot-border-animations_report.md` per phase.
