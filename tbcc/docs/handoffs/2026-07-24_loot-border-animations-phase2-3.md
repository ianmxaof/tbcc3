# Claude Code Handoff — Loot Border Animations Phases 2–3

**Date:** 2026-07-24  
**Branch:** `fix/loot-border-reveal`  
**Repo:** `C:\Powercore-repo-main\telegram_bot2\tbcc`  
**Operator decision:** **A — HOLD** (no interim pair-model hot-patch; island deploy at Phase 4)  
**Prior report:** `docs/handoffs/2026-07-24_loot-border-reveal_report.md` (Phase 1 ops DONE)  
**Reverse report required:** `docs/handoffs/2026-07-24_loot-border-animations_report.md` after each phase

## Operator-confirmed source (2026-07-24)

**14 MP4s verified** at:

`C:\Users\ianmp\Downloads\tbcc\AOF NETWORK\AOF RESOURCES (ZIPS)\AOF LOGOS\_transparent border_gemini\OPEN & STASIS ANIMATIONS\BORDER OPEN ANIMATIONS`

Import script `DEFAULT_SRC` already matches — no `--src` override needed.

| File | ~MB |
|------|-----|
| brushed_metal_stasis_sparkle_open.mp4 | 2.47 |
| PROJECT_AOF_LOOT_GOD_-_single.mp4 + animat variants (1)–(4) | 2.2–2.5 each |
| Metal_border_chrome_fills_.mp4, Metal_border_chrccome_fills_.mp4 | 2.3–2.4 |
| ccx.mp4, dxvdx.mp4 | 2.5 |
| PROJECT_AOF_L4OOT_GOD / LO4OT_GOD typo variants | 2.3–2.4 |
| Unix_Commands_on_Windows_Explained.mp4 | 2.45 — **denylist** |

---

```
# TBCC Loot Border Animations — Phases 2–3 (Lane C)

## Operator ACK

Decision **A — HOLD** confirmed. Do **not** hot-patch island with deprecated pair-model (`docker cp` backend-src). Flag `TBCC_LOOT_BORDER_REVEAL=1` stays ON on island; borders go live at **Phase 4** after single-clip code + assets are final.

## Goal (definition of done)

Phases 2–3 complete when:

1. All single-clip border MP4s are imported to `backend/app/data/loot_tier_cards/borders/open/` (14 source files per phase2-plus doc, minus denylisted strays).
2. `pick_border_clip()` rotates imported clips locally; denylist excludes `border-001`, `border-002`, `border-003`, `Unix_Commands`.
3. Tests pass:
   ```
   cd backend
   py -3.13 -m pytest tests/test_loot_border_reveal.py tests/test_loot_stamp_layout.py tests/test_loot_card_fallback.py -q
   ```
4. One local spike produces a valid MP4:
   ```
   cd backend
   py -3.13 scripts/spike_border_reveal.py --tier 7
   ```
   (Use any small center still if tier assets missing; document path used.)
5. Reverse report written; **STOP** — do not run Phase 4 (island deploy).

## Scope

### In scope
- `backend/scripts/import_loot_border_animations.py` — run/fix if source path wrong
- `backend/app/data/loot_tier_cards/borders/open/*.mp4` — imported assets (git may track or gitignore large binaries per repo convention; document choice in report)
- `backend/app/services/loot_border_reveal.py` — single-clip `pick_border_clip()` (431 lines in working copy; do not revert to pair-only)
- `backend/app/services/loot_border_profiles.py`, `loot_border_plates.py`
- `backend/app/services/loot_tier_card_assets.py` — border-aware compose path
- `backend/tests/test_loot_border_reveal.py`, `test_loot_stamp_layout.py`, `test_loot_card_fallback.py`
- `docs/handoffs/2026-07-24_loot-border-animations-phase2-plus.md` — doctrine reference

### Out of scope (STOP if tempted)
- Island SSH / `docker cp` / `deploy-island-live.ps1` / image rebuild (**Phase 4**)
- Interim pair-model hot-patch (decision A)
- Buffer, Kit, growth flywheel, unrelated TBCC changes
- Committing `infra/.env.revenue-island` or secrets

## Constraints & gotchas

1. **Source clips path** (operator-confirmed, 14 MP4s present):
   `C:\Users\ianmp\Downloads\tbcc\AOF NETWORK\AOF RESOURCES (ZIPS)\AOF LOGOS\_transparent border_gemini\OPEN & STASIS ANIMATIONS\BORDER OPEN ANIMATIONS`
   `import_loot_border_animations.py` DEFAULT_SRC matches — run without `--src`. Denylist `Unix_Commands` via env per doctrine.

2. **Stasis deprecated.** Single clip per border. `pick_border_pair()` is compat-only (returns same clip twice). No `borders/stasis/` folder.

3. **Island state (do not touch):** `TBCC_LOOT_BORDER_REVEAL=1` live; no `loot_border_reveal` module in image (static path still — expected until Phase 4).

4. **Multi-agent:** Cursor may have uncommitted border `*.py` edits. Read current files from disk; do not overwrite working single-clip refactor with island's 403-line pair-only copy.

5. **ffmpeg** required for import + spike. Verify `ffmpeg -version` before encode.

6. **Guardrails:** No `deploy-island-live.ps1` (OOM). Selective commits only — border code + import script + tests + report; not whole dirty tree.

## Verification (run and paste summaries in report)

```powershell
cd C:\Powercore-repo-main\telegram_bot2\tbcc\backend

# Phase 2
py -3.13 scripts/import_loot_border_animations.py
# optional: py -3.13 scripts/import_loot_border_animations.py --trim 7.6 --size 512
Get-ChildItem app\data\loot_tier_cards\borders\open\*.mp4 | Measure-Object

# Phase 3
py -3.13 -m pytest tests/test_loot_border_reveal.py tests/test_loot_stamp_layout.py tests/test_loot_card_fallback.py -q
py -3.13 scripts/spike_border_reveal.py --tier 7
```

## Working agreement

- Branch: `fix/loot-border-reveal`
- Commit after each phase with focused message (border import / tests only)
- Push: **no** unless operator asks
- After **each** phase: write `docs/handoffs/2026-07-24_loot-border-animations_report.md` using reverse-report structure, then **STOP for Cursor ACK**
- Run `/usage` in Claude Code before starting; halt if weekly cap nearly exhausted

## Phases

### Phase 2 — Import single clips
- Locate source folder; run `import_loot_border_animations.py`
- Confirm ≥10 MP4s in `borders/open/` (expect ~14 minus denials)
- Verify file sizes sane (~2–3 MB each pre-trim)
- Verification: file count + import script exit 0
- Write report section **Phase 2**; STOP

### Phase 3 — Rotation + local spike
- Confirm `pick_border_clip()` returns non-None with `TBCC_LOOT_BORDER_ALLOW_UNPROFILED=1`
- Confirm denylist blocks legacy `border-001` etc.
- Run full pytest trio + `spike_border_reveal.py`
- Note any missing `BorderRevealProfile` for variants (OK to use `BRUSHED_METAL_STASIS_SPARKLE` shared plate per doctrine)
- Verification: pytest green + spike output path
- Write report section **Phase 3**; STOP

### Phase 4 (NOT NOW — Cursor will hand off after ACK)
- Bake or volume-mount `borders/open/` + border Python modules to island
- `docker cp` assets or image rebuild (operator chooses; avoid OOM rebuild path)
- Island spike + one real `/roll` smoke
```

---

## Lane note

- **Phases 2–3:** Lane C (mechanical import + test grind)
- **Phase 4 deploy strategy:** Lane B judgment (bake vs volume-mount vs targeted `docker cp` with persistence) → then Lane C or Cursor ops

## Quota reminder

Run `/usage` in Claude Code before pasting. Cursor cannot read your Anthropic quota window.
