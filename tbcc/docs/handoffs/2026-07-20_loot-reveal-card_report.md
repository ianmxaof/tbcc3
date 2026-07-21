# Loot Reveal Card — Phase 1 report (asset audit + clean/ pool)

Date: 2026-07-20
Branch: `feat/supervisor-panel-foundation` (committed, NOT pushed)
Scope: **Phase 1 only** — asset audit + `frames/clean/` pool + import/audit script.
Phases 2 (compositor), 3 (pick_frame_path tier-band + baked-badge reject), 4 (island
deploy) are **not** started — stopped here for Cursor ACK per working agreement.

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
