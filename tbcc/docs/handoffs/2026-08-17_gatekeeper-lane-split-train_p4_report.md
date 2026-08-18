# Reverse handoff — gatekeeper-lane-split-train

- Branch: `lane-c/gatekeeper-lane-split`
- Head commit(s) this phase:
  - `acb78a6` — feat(gatekeeper): P4 CLIP catalog export helper + review-card proposed lanes
  - `aaf101b` — docs(gatekeeper): P5 section + TEST_MAP row for inbox mixed split
- Status: Phase 4 complete

## Done

- `docs/MEDIA_GATEKEEPER.md`: added a `P5` row to the status table and a `### P5 — Inbox mixed split + prototype bank` section (signal sources, auto-route decision, gold labels, known limitation, deviations summary) plus an `### Env (inbox split + prototype bank)` table (`TBCC_GATEKEEPER_INBOX_SPLIT`, `TBCC_GATEKEEPER_AUTO_SPLIT_MIN`, `TBCC_GATEKEEPER_AUTO_SPLIT_MARGIN`, `TBCC_GATEKEEPER_PROTOTYPE_MIN`, `TBCC_CLIP_CATEGORIZE_URL`). Red lines (no vision-LLM judge, no GPU fine-tune) restated, not touched.
- `docs/TEST_MAP.md`: added the **Gatekeeper lane split** row pointing at all six spec/service/mapper/inbox-split/prototype/tag-map test files.
- `backend/scripts/export_aof_lane_clip_catalog.py` (new, optional per spec): `build_aof_lane_catalog(*, max_slugs_per_lane=3)` builds a small catalog from `CLIP_SLUG_TO_LANE` / `SPLIT_LANE_KEYS`, one entry per lane→slug in the same shape the production catalog uses (`slug`, `name`, `prompts`, `group`). `main()` refuses to write to a path literally named `clip-categories.json` and prints to stdout when no `--out` is given. Default run produces 32 categories across all 11 lanes.
- `backend/app/services/gatekeeper_review.py`: `format_quarantine_review_html` now appends an `<i>Proposed: 🍑 ass, 🍒 big_tits</i>`-style line when `lane_fit.proposed_lanes` is present and non-empty.

## Files touched

- `tbcc/docs/MEDIA_GATEKEEPER.md`
- `tbcc/docs/TEST_MAP.md`
- `tbcc/backend/scripts/export_aof_lane_clip_catalog.py` (new)
- `tbcc/backend/tests/test_export_aof_lane_clip_catalog.py` (new, 6 tests)
- `tbcc/backend/app/services/gatekeeper_review.py`
- `tbcc/backend/tests/test_gatekeeper_review.py` (+2 tests)

## Verification run

Locked Phase 4 command plus the new catalog-script tests, from `tbcc/backend`:

```
py -3.13 -m pytest tests/test_media_gatekeeper_spec.py tests/test_media_gatekeeper_service.py tests/test_gatekeeper_clip_lane_map.py tests/test_gatekeeper_inbox_split.py tests/test_gatekeeper_prototypes.py tests/test_aof_lane_tag_map.py tests/test_export_aof_lane_clip_catalog.py -x -q --tb=short
```
→ **94 passed**.

Full regression on the file touched by the review-card change (not part of the locked Phase 4 command, run for safety since Phase 3's `test_gatekeeper_prototypes.py` overlaps the same review path):

```
py -3.13 -m pytest tests/test_gatekeeper_review.py -x -q --tb=short
```
→ **9 passed** (includes the two new tests: `test_format_quarantine_shows_proposed_lanes_when_present`, `test_format_quarantine_omits_proposed_line_when_empty`). This file is historically slow (~5-6 min, unrelated to this change — retry/timeout behavior against unreachable endpoints in other tests in the same file).

## Risks / open questions

- **Deviation — review-card line is unscored, not the literal spec text.** Spec text was `proposed: 🍑 ass 0.41 / 🍒 big_tits 0.22` (with numbers). Shipped: `Proposed: 🍑 ass, 🍒 big_tits` (lane keys only, ranked, no scores). Reason: per-lane scores from `resolve_proposed_lanes` (Phase 2, `gatekeeper_inbox_split.py`) are computed on the auto-route/quarantine decision path (`maybe_auto_split_inbox`) and are not persisted to `classification_json` on the preselect/quarantine branch — only the already-persisted (Phase 1) unscored `lane_fit.proposed_lanes` ranked-key list is available to the review-card formatter. Adding score persistence would mean writing a new sibling key from inside `maybe_auto_split_inbox`'s quarantine branch, which Hermes's Phase 3 ACK just signed off on as-is — out of scope for a "cheap one-line" ask. Flagging here per the spec's own "if cheaply" gate, so Cursor/Hermes can decide whether scored persistence is worth a follow-up.
- **`export_aof_lane_clip_catalog.py` writes `"group": "<lane>"` per entry**; the production `clip-categories.json` catalog uses `"group": null`. Harmless — `load_categories_from_path` reads `group` through unchanged either way — but worth knowing if an operator points `TBCC_CLIP_CATEGORIES_FILE` at the generated file: entries will carry a `group` value the production catalog doesn't use.
- No push, no bot Start, no `.env` touched, no island deploy this phase.
- Migration 114 (`gatekeeper_lane_labels`) is still verified against throwaway SQLite only, per the Phase 3 ACK's "confirm, not blocker" note — still not run against the real Postgres island DB. Unchanged from Phase 3; restating since this is the last phase in the locked plan before any deploy decision.

## Operator smoke (Tray only)

Not run this phase — Phase 4 is docs/script/review-card only, no runtime behavior change to the split/route/auto-approve decision path itself. No Tray smoke needed beyond what Phases 1-3 already covered.

## Do not

- push
- start bots
- touch `.env`
- deploy to island
- start Phase 5 — none exists in the locked plan; Hermes's Phase 3 ACK constraint #9 requires a fresh ACK before any further work on this line
