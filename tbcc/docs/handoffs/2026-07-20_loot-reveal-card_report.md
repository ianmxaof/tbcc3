# Loot Reveal Card — Phase 1 / 1b report (asset audit + clean/ pool)

Date: 2026-07-20
Branch: `feat/supervisor-panel-foundation` (committed, NOT pushed)
Scope: **Phase 1 + 1b** — asset audit + `frames/clean/` pool + audit/de-checker tools.
Phases 2 (compositor), 3 (pick_frame_path tier-band + baked-badge reject), 4 (island
deploy) not yet started.

---

## PHASE 1b UPDATE (no-API pool expansion) — clean pool 8 → 12

- **remove.bg is a dead end for now:** key file is present but empty / 0 credits on the
  account. The client (`scripts/removebg_import_loot_frames.py`) is committed and
  dry-run verified, but its **live API path is untested** (no credits). It reads the key
  from env `REMOVEBG_API_KEY` or gitignored `backend/.removebg.key`; never printed/committed.
- **No-API de-checker added** (`declutter_exterior` in `audit_loot_card_frames.py`):
  floods the baked grey checkerboard inward from the frame edges to real alpha=0,
  stopping at dark/neon borders. This rescues frames that have a clean center hole but a
  baked *opaque* checker margin (the import punch misses those — large checker cells only
  show the brightness step at cell edges).
- **Rescued 4 frames** into `clean/` via a **curated, eyeballed** keep-list
  (`--declutter-rescue 001,003,005,007,010`): **001, 003, 005, 007** promoted;
  **010 auto-rejected** by the audit gate (raw decheckered file still 2.8% checkerish —
  its cyan double-border trips the detector; composed clean by eye but excluded
  conservatively rather than relax the gate).
- **Every rescued frame was eyeballed** (compose over a bright placeholder center), not
  just gate-passed — because the gate confirms *checker gone* but cannot confirm *border
  survived* the flood. Dropped on inspection: 002 (ragged glitch), 004 (neon fragments +
  residue), 006 (silver border survived but outer checker residue), 008 (speckle), 009
  (heavy magenta speckle).
- **clean/ is no longer pure-copy:** 094–101 are copied as-is; 001/003/005/007 are
  **script-regenerated** (decheckered). All 12 have corner+center alpha 0, so the
  compositor's `sanitize_frame_alpha` hits its `already_clean` fast-path and ships them
  byte-identical to what was eyeballed. Rebuild any time:
  `py -3 scripts/audit_loot_card_frames.py --write --declutter-rescue 001,003,005,007,010`
- **Still no live-behavior change.** `list_frame_paths()` = 101; live rolls still serve
  all 101 (incl. checkered 001–010 and baked-tier 050/070). The user-visible wrong-tier
  bug persists until **Phase 3** flips the selector to `clean/`. Phase 1b grew an inert
  pool only.
- **Deferred to Phase 2 (noted, not done):** folding the de-checker into
  `sanitize_frame_alpha` would fix all frames at delivery, but has blast radius across all
  101 frames (could eat light metal borders) — left as a Phase 2 decision.

---

## PHASE 1 (original)

---

## DONE

- Added `backend/scripts/audit_loot_card_frames.py` — programmatic, reusable auditor
  that classifies every `frames/frame-*.png` on **structural** cleanliness and
  (with `--write`) **COPIES** the clean ones into `frames/clean/`.
- Audited all **101** frames. Result: **8 clean, 93 rejected.**
  - Clean pool = `frame-094 … frame-101` (the remove.bg batch the task doc flagged
    as "best").
  - Copied to `app/data/loot_tier_cards/frames/clean/` (8 files). **Top-level frames
    left untouched** — `list_frame_paths()` still returns 101, so live rolls are
    byte-for-byte unchanged (clean/ is a subdir the current selector skips; Phase 3
    flips the selector).
- Full per-frame audit table saved to `docs/handoffs/2026-07-20_frame-audit.json`.

## VERIFIED

- **Live behavior unchanged:** `list_frame_paths()` → 101 paths, none from `clean/`.
  (The advisor's regression trap — moving instead of copying would have dropped the
  live pool to 0 and silently fallen back to static `tier-N.png`. We copied.)
- **Ground-truthed by eye, not just metrics.** Composited representative frames over
  solid magenta (holes show magenta, opaque checker/chrome shows real):
  - `frame-001..010`: clean center hole + clean neon-chrome border, BUT baked **opaque
    exterior checkerboard** outside the border (edge-checker 8–11%) → rejected.
  - `frame-050`, `frame-070`: **no window** — baked full-art / baked checker center,
    baked "TIER 6 • 3-1" / "TIER 3 • 1-3" text → these are the "wrong-tier label" bug
    source → rejected.
  - `frame-094..101`: transparent exterior, real center hole, distressed metal border,
    baked "AOF LOOT" branding + **empty** top-right plate (no baked tier number) →
    clean.
- **No wrong-tier baked text in the clean pool.** All 8 clean frames carry only "AOF
  LOOT" branding and an empty top-right plate where the dynamic stamp writes TIER N —
  nothing to contradict the roll. (Confirmed on 8-frame contact sheet.)
- **Composed a real card from the pool** (existing `compose_reveal_card`, no Phase-2
  changes) — `frame-094` + bright placeholder center, Tier 5 / World 2-2 / "drip":
  output is opaque RGB JPEG (970×1024, no alpha), real photo in the window, border
  wraps the edges, **TIER 5** green badge lands correctly in the top-right plate, no
  checkerboard. Render saved to scratchpad `frameaudit/compose_t5_frame094.jpg`.
  So the deliverable is "a pool that makes good cards," not just "8 frames that pass a
  metric." Two Phase-2 nits observed (deferred, not Phase 1):
    - The stamp's "AOF LOOT" line **overlaps** the frame's baked "AOF LOOT" (they are
      two offset copies, not reinforcement — corrected wording below). Baked copy is
      dark-on-dark so the white stamp covers it acceptably, but Phase 2 should either
      drop the stamp brand line or require text-free frames.
    - Bottom name ("DRIP") and tagline ("Mid-heat.") overlap vertically — stamp layout
      nit for Phase 2.

## DEFINITION USED (read this before ACK)

`clean/` = **STRUCTURAL** cleanliness only:
  - central window is a real alpha hole (`window_hole ≥ 0.55`)
  - baked-checker residue `< 1.5%` overall and `< 2%` on the edge ring
Baked *tier/world text* detection is **out of Phase 1** (it's Phase 3 frame-rejection +
Phase 2 stamp-wins-visually). We only *recorded* a top-right-opaque signal per frame;
it did not gate selection. The clean pool happens to also be text-safe (empty plates),
but that is a property of the 094–101 batch, not something Phase 1 enforced.

## BLOCKED / DECISIONS FOR CURSOR

1. **Pool size = 8.** Small but curated. Expanding it means re-processing dirtier
   frames (see NEXT), which is asset re-work — deferred out of Phase 1.
2. **remove.bg script NOT added.** The clean batch (094–101) already *is* remove.bg
   output, so the pipeline effectively already ran. Wiring
   `scripts/removebg_import_loot_frames.py` would (a) need the user's `REMOVEBG_API_KEY`
   and (b) upload frame art to an external paid service. **Decision needed:** do you
   want it wired now? If yes, supply the key out-of-band (do not commit it).
3. **Assets are untracked by design.** Nothing under `loot_tier_cards/` is in git; the
   island deploy `rsync`s the backend tree instead. So this commit is **code/text only**
   (audit script + JSON + this report). The 8 `clean/` PNGs live on disk and are
   reproducible any time via `py -3 scripts/audit_loot_card_frames.py --write`.
   FYI `frames/_source/` holds ~60 MB of raw Gemini sheets — untracked, but a future
   blanket `git add` would sweep them in; consider a `.gitignore` guard (not done here).

## NEXT (Phase 2+ — do NOT start without ACK)

- **Phase 1b (optional pool expansion):** `frame-001..010` have the nicest borders
  (cyan neon) and perfect holes; only their *exterior* is baked checker. A targeted
  exterior re-punch (reuse `import_loot_card_frames.punch_window` / `repunch_*`) could
  promote ~10 more frames into `clean/`. Cheap, high-value variety win.
- **Phase 2 (compositor):** verify layer order (center paste → alpha_composite frame),
  deterministic `compose_reveal_card(frame_path=, center_path=)` mode, assert JPEG/no-
  alpha output. Add `tests/test_loot_reveal_card_compose.py`.
- **Phase 3 (selection):** point `pick_frame_path` at `frames/clean/` only; reject any
  frame with a detectable baked tier badge. Dynamic stamp must win visually.
- **Phase 4:** island deploy + one live `/roll` smoke screenshot.

## Repro / verify commands

```
cd tbcc/backend
py -3 scripts/audit_loot_card_frames.py                 # print classification table
py -3 scripts/audit_loot_card_frames.py --write          # rebuild frames/clean/ (COPY)
py -3 -c "from app.services.loot_tier_card_assets import list_frame_paths; \
  print(len(list_frame_paths()))"                        # -> 101 (live pool unchanged)
```
