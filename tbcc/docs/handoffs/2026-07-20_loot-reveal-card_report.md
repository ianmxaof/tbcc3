# Loot Reveal Card — Phase 1 / 1b report (asset audit + clean/ pool)

Date: 2026-07-20
Branch: `feat/supervisor-panel-foundation` (committed, NOT pushed)
Scope: **Phase 1 + 1b + 2 + 3** + **rembg swap**. Phase 4 (island deploy) **not**
started — that's the operator step and the only thing between here and the live fix.

---

## REMBG SWAP (replaced remove.bg; investigated pool growth)

**What changed**
- Deleted `scripts/removebg_import_loot_frames.py`; added
  `scripts/rembg_import_loot_frames.py` with **two backends** (you chose Both):
  - `local` (default) — `rembg` library, offline/free/unlimited. Installed
    `rembg[cpu]` 2.0.77 + onnxruntime 1.27.0 under **Python 3.13** (no 3.14 wheels), so
    run the script with `py -3.13`. Verified: bg removal ~1.7s/sheet after a one-time
    176 MB u2net model download (md5-checked to `~/.u2net/u2net.onnx`).
  - `replicate` — `cjwbw/rembg` hosted fallback. Token from env `REPLICATE_API_TOKEN`
    or gitignored `backend/.replicate.key`. Coded, **not yet tested live** (you have a
    token — drop it in that file to use it).
- Pipeline: bg-remove → `split_cards` → `normalize_frame` (runs `punch_window` for the
  interior hole) → **staging** dir `frames/_rembg/` (gitignored; live selector ignores
  `_*`). **Never auto-writes clean/** — the structural audit is blind to baked TIER text,
  so a "TIER 5 / DRIP" card would pass the gate and re-introduce the wrong-tier bug.
  Human eyeball + hand-copy only.

**Key finding — the swap works but current source art can't grow the badge-free pool**
- Triaged all 9 new Gemini sheets. They are **either full 1–10 tier decks with baked
  tier labels** (`35rrlv`, `6ol2c8`, `qnv4qq`, `wy8vwf`) **or carry other baked text**
  (`yfb5x4` bakes "TIER 2 • 1-2" / "LOOT" / flavor). **None are truly blank-plate.** The
  094–101 batch (from the original `removebg_blank_plates` sheet) remains the only
  badge-free set. So local rembg removes backgrounds fine, but **feeding the random
  badge-free pool needs blank-plate art we don't currently have.**
- Also observed: `split_cards` mis-segments these tight grids (made 5 strips from a 2×4);
  a **fixed uniform-grid crop** (rows×cols known) splits cleanly. And `punch_window`
  leaves residual window checker on ~half the cards. Both are fixable but out of scope
  until the architecture below is chosen.

**Recommended next architecture (task's stretch goal) — decision for you**
- These tier decks aren't junk: each card is labeled with *its own* tier
  (NEWBIE=1 … DRIP=5 … GODROLL=10) and the baked names match the catalog. **Map each
  card → its labeled tier** and the baked "TIER 5 / DRIP" becomes *correct on tier 5*,
  reinforcing the roll instead of contradicting it. That turns the whole tier-deck supply
  into one coherent frame per tier — and is the path that actually uses the art you have.
  This is a genuinely different design from the shipped random-badge-free-pool selector,
  so it's your call. **Not started.**

---

## PHASE 3 (frame selection → clean pool) — this is the actual bug fix

- **Root cause of "Tier 5 showed TIER 3":** `pick_frame_path` chose from all 101 raw
  frames, ~90 of which bake a wrong tier/world label into the art. Fixed by **only
  selecting from the curated `clean/` pool.**
- New selectors in `loot_tier_card_assets.py`:
  - `list_clean_frame_paths()` → `frames/clean/` (the 12 vetted, badge-free frames)
  - `list_reveal_frame_paths()` → clean pool when present, else raw top-level
    (back-compat / fresh checkout with no clean/)
  - `compose_reveal_card`, `pick_frame_path`, `build_reveal_card_png` all now draw from
    `list_reveal_frame_paths()`. `build_reveal_card_png` note reports `pool=clean|raw`.
- **Baked-badge rejection = curation, not a runtime detector.** The task allowed either
  "reject frames with a baked badge OR only use clean/." I chose clean/-only: the 12
  frames were hand-vetted badge-free, so a fragile runtime badge-detector (which could
  wrongly reject the empty top-right plates) is unnecessary and riskier. If you want
  defense-in-depth detection too, that's a follow-up.
- **Verified:** `list_reveal_frame_paths()` returns 12 (was 101); a live
  `build_reveal_card_png(5)` reports `pool=clean frames=12` and produces a 210 KB JPEG.
  Two new selector tests (prefers clean / falls back to raw) + full loot suite **74
  passed, 0 failed**.
- **The 12 `clean/` PNGs are now committed** (≈360 KB) as the durable source of truth —
  unlike the raw 101 + 60 MB `_source` (untracked, rsync-deployed), the curated pool
  encodes a human keep-list that a fresh clone can't regenerate (its script inputs are
  untracked).
- **Still not live.** This is a committed code+asset change; it reaches users only when
  **Phase 4 deploys to the island**. Until deploy, production still rolls all 101 and the
  wrong-tier bug is 100% present.

### What each clean frame looks like (dynamic stamp still wins)
`test_tier_label_is_dynamic` proves the stamp varies by tier — but on a *blank* synthetic
frame. It does **not** yet prove the stamp beats a baked "TIER 3"; that scenario is now
avoided by curation rather than tested. Worth a real baked-frame test if we ever relax
the clean-only rule.

---

## PHASE 2 (compositor hardening + deterministic tests)

- **Layer order confirmed already correct:** center pasted first, `alpha_composite(frame)`
  second, `_window_bbox` flood-fills the exterior so only the interior hole gets the
  still. No rectangular window wipe. No change needed.
- **Opaque-output invariant enforced:** `compose_reveal_card` now converts to RGB before
  JPEG save unconditionally — send_photo can never receive an alpha channel.
- **Stamp bug fixed (name/tagline overlap):** the bottom name + flavor are now stacked
  and bottom-anchored using measured text heights; the tagline no longer renders on the
  name's descenders. Verified on real frames (003, 097).
- **Deterministic tests added** — `tests/test_loot_reveal_card_compose.py` (5 tests, all
  green; existing `test_loot_reveal_composite.py` 11/11 still green):
  - output is opaque JPEG, `mode == RGB`, no alpha
  - center region carries the vivid photo (paste actually happened), not the backdrop
  - no classic mid-grey checker pixel in any corner
  - **tier label is dynamic** — same frame at tier 2 vs 8 yields different top-right
    badge pixels (proves the label comes from the roll, not baked frame art)
  - name+tagline compose without error / stay opaque
- **NOT changed (design decision left to you):** the clean frames bake "AOF LOOT"
  top-left and the stamp also draws it → a faint doubled brand. Options: drop the stamp's
  brand+hub line (frames already carry branding) or require text-free frames. Left as-is
  (stamp = source of truth) since future frames may lack baked branding.
- **NOT done (deferred to Phase 3 by design):** folding the de-checker into
  `sanitize_frame_alpha` (blast radius across all 101 frames).

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
