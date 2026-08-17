# Reverse handoff — gatekeeper-lane-split-train

- Branch: `lane-c/gatekeeper-lane-split`
- Head commit(s) this phase (hash + subject): `3f81412` feat(gatekeeper): online prototype bank + CLIP embeddings (Phase 3)
- Status: Phase 3 complete

## Done

- **Migration `114_gatekeeper_lane_labels`** (`down_revision = 113_secretary_draft_candidates`) creates `gatekeeper_lane_labels` exactly to spec: `id`, `media_id` (nullable), `file_unique_id` (indexed), `lanes_json`, `source`, `embedding_json` (nullable), `dim`, `created_at` (indexed). No unique on `media_id`. **Verified directly** (no test in the suite runs Alembic): stamped a throwaway SQLite DB at `113`, ran `alembic upgrade head`, inspected the resulting `CREATE TABLE`/indexes, then ran `alembic downgrade 113` and confirmed the table drops cleanly. The full migration chain from zero doesn't run on SQLite (an earlier, unrelated migration uses Postgres-only `ALTER COLUMN ... DROP NOT NULL`) — not a regression, this repo's migrations have only ever targeted Postgres; isolating from `113` sidesteps that pre-existing incompatibility.
- **`app/services/gatekeeper_prototypes.py`** (new) — pure-Python (no numpy; confirmed it's present only transitively, not in `requirements.txt`, so centroid math is plain lists/floats to stay portable to a lean island deploy):
  - `record_label(db, *, media_id, file_unique_id, lanes, source, embedding=None, hard_block=False)` — skips entirely (no row at all) when `hard_block=True`; dedupes on `(file_unique_id, source, embedding-presence)` so the two-pass ingest hook doesn't write a duplicate caption-only row on every re-verdict, while still allowing a caption-only row to be followed by a distinct embedding-bearing upgrade row.
  - `load_centroids(db)` / `score_embedding(db, vec)` — centroid = running sum / count, filtered to lanes with `count >= TBCC_GATEKEEPER_PROTOTYPE_MIN` (default 8).
  - `maybe_recalc(db)` — cache hit returns cached sums untouched; cache miss does exactly ONE full table scan then caches. No periodic rebuild.
  - Redis key `tbcc:gk:centroids` (24h TTL as a safety net) is deleted inside `record_label` on every embedding-bearing write — see deviation note below on the "as soon as that lane's count ≥ PROTOTYPE_MIN" wording.
  - `media_is_hard_blocked(media)` — shared by all three record-label call sites; reads `classification_json.gatekeeper` for `verdict == "reject"` or any `hard_block:*` flag.
- **CLIP sidecar** (`services/clip_categorize_app.py`): `POST /embed` and `POST /embed-path` return `{"ok", "dim", "embedding"}` — a raw L2-normalized image embedding via the same `encode_image` path as `/classify`, no catalog required. Calls `_ensure_model()` directly rather than going through `reload_catalog()`, since `reload_catalog()` returns early (never loading the model) when `TBCC_CLIP_CATEGORIES_FILE` is unset — exactly the config where `/embed` (no catalog needed) is most useful.
- **`app/services/clip_classifier.py`**: `embed_image_bytes()` client function, mirrors `classify_image_bytes()`.
- **Three `record_label` hook sites**, all wrapped in try/except so a labeling failure never breaks the caller's primary action:
  1. `media_gatekeeper.apply_gatekeeper_after_ingest` — for named-topic deposits (`expected_lane` is a genuine split lane, not inbox/packs), records `source="hub_topic"`. Embedding comes from `enrich.get("clip_embedding")` when present (the auto_tag_enrich pass), `None` otherwise (ingest-time pass) — same row, upgraded on the second call via the dedupe logic above.
  2. `auto_tag_enrich.py` — alongside the existing CLIP-niche-classify block, adds `out["clip_labels"]` (already Phase 2) and now `out["clip_embedding"]` via a second sidecar call (`embed_image_bytes`).
  3. `gatekeeper_review.py` — `operator_approve_media` records `source="operator_approve"` with the operator's selected lanes (`embedding=None` — see deviation note); `operator_reject_media` records `source="operator_reject"` with `lanes=[]` and no embedding, so a reject can never move a centroid.
- **`gatekeeper_inbox_split.py` blending**: `resolve_proposed_lanes` gained a keyword-only `prototype_scores` param (stays a pure function — no DB access). `maybe_auto_split_inbox` computes `prototype_scores` via `gatekeeper_prototypes.score_embedding` **only when `enrich["clip_embedding"]` is present** — never on the caption-only ingest pass, so a bulk dump doesn't force a centroid load (potential full table scan) per item. When CLIP's top lane and the prototype bank's top lane agree, the blended score for that lane is boosted ×1.15 (cap 1.0). When they disagree, `maybe_auto_split_inbox` forces the non-auto-route path — this is implemented as an explicit `disagree` flag ANDed into the confidence check, not merely "skip the boost," since skipping only the boost would still let the higher of the two raw scores clear the auto-route threshold on its own.

### Self-caught regressions (advisor review, before this landed on Cursor's desk)

1. **Disagreement was a missing boost, not an override, in the first draft.** Caught before commit: if CLIP says lane A at 0.6 and the prototype bank says lane B at 0.55, simply not applying the ×1.15 boost still lets 0.6 clear `AUTO_SPLIT_MIN`/margin and auto-route on lane A — exactly the silent-misroute shape this whole design exists to prevent. Fixed by making disagreement force `quarantine_preselect` with both lanes explicitly included (`sorted({clip_top, proto_top})`), regardless of the arithmetic. Covered by `test_clip_and_prototype_disagree_no_auto_route`.
2. **`record_label` could poison the caller's DB session on any failure.** Both the dedupe query and the final `db.add()`/`db.commit()` only logged and continued on exception — on Postgres, a failed statement (e.g. `gatekeeper_lane_labels` not yet migrated on an island that hasn't deployed this phase) leaves the transaction aborted; every subsequent statement on that same session fails until a rollback. Since `record_label` runs inside `apply_gatekeeper_after_ingest` and `operator_approve_media`, sharing `db` with code that keeps using it afterward (`_post_media_ingest`'s `db.refresh(record)`, the rest of the approve flow), an unmigrated table could have silently broken ingest/approve entirely rather than just skipping the label. Fixed with explicit `db.rollback()` in both failure paths; added `test_record_label_rolls_back_session_when_dedupe_query_fails` and `test_record_label_rolls_back_session_when_commit_fails` to lock it in.

## Files touched

- `tbcc/backend/alembic/versions/114_gatekeeper_lane_labels.py` (new)
- `tbcc/backend/app/models/gatekeeper_lane_label.py` (new)
- `tbcc/backend/app/services/gatekeeper_prototypes.py` (new)
- `tbcc/backend/tests/test_gatekeeper_prototypes.py` (new, 18 tests)
- `tbcc/services/clip_categorize_app.py` (edit — `/embed`, `/embed-path`, `embed_pil`)
- `tbcc/backend/app/services/clip_classifier.py` (edit — `embed_image_bytes`)
- `tbcc/backend/app/services/media_gatekeeper.py` (edit — `hub_topic` label hook)
- `tbcc/backend/app/services/auto_tag_enrich.py` (edit — `out["clip_embedding"]`)
- `tbcc/backend/app/services/gatekeeper_review.py` (edit — `operator_approve`/`operator_reject` label hooks)
- `tbcc/backend/app/services/gatekeeper_inbox_split.py` (edit — prototype blending, agreement boost, disagreement override)
- `tbcc/backend/tests/test_gatekeeper_inbox_split.py` (edit — 1 new test for the disagreement guard, 17 tests total)

## Verification run

Locked Phase 3 command:

```
cd tbcc/backend
py -3.13 -m pytest tests/test_gatekeeper_prototypes.py tests/test_gatekeeper_review.py -x -q --tb=short
# 27 passed in 350.85s
```

This command does not include `tests/test_gatekeeper_inbox_split.py` — the prototype-disagreement test (`test_clip_and_prototype_disagree_no_auto_route`) lives there, so the 27-pass number above does not exercise rule E's disagreement guard. Ran separately:

```
py -3.13 -m pytest tests/test_gatekeeper_inbox_split.py -q --tb=short
# 17 passed
```

Combined regression across everything touched this phase:

```
py -3.13 -m pytest tests/test_gatekeeper_prototypes.py tests/test_gatekeeper_inbox_split.py tests/test_media_gatekeeper_service.py tests/test_storage_deposit_auto_approve.py -q --tb=short
# 49 passed
```

Migration verified directly against a throwaway SQLite DB (stamp-from-113, upgrade, inspect, downgrade) — see "Done" above.

## Risks / open questions

- **Deviation, needs explicit ACK — always-invalidate on every embedded write.** Locked design B says delete the centroid cache "as soon as that lane's count ≥ PROTOTYPE_MIN — do not wait for a 24h TTL." Implemented as: always invalidate on every embedding-bearing `record_label` write, regardless of the lane's current count. This is a strict superset of the literal instruction (harmless — a cache serving stale-but-valid sums below `PROTOTYPE_MIN` doesn't matter since `load_centroids` filters by that threshold anyway) and avoids an off-by-one risk in a conditional invalidate. Flagging since it's still a reading of a "MUST," not a literal implementation.
- **Deviation, needs explicit ACK — no synchronous CLIP embed on either operator hook.** `operator_approve_media` and `operator_reject_media` both call `record_label` with `embedding=None`. The locked design says "Record embedding when sidecar up," but embedding a fresh image synchronously inside an operator's Telegram tap would add sidecar-HTTP latency to an interactive action. The embedding still arrives for approved items via the `hub_topic` hook once/if `auto_tag_enrich` runs on that same item. Same reasoning as the Phase 2 report's identical deviation on the split path.
- **Sidecar load doubles per enriched item.** `auto_tag_enrich.py` now makes two CLIP sidecar HTTP calls per item when CLIP is enabled (`/classify` for niche labels, `/embed` for the prototype embedding) instead of one. Only matters when the operator has the sidecar on; stating it since it's a real doubling of that call volume, not a rounding error.
- **`gatekeeper_lane_labels` rows from the embedding-less `hub_topic` hook are currently write-only.** Nothing reads a caption-only (no-embedding) row — `load_centroids`/`_scan_running_sums` only sum rows that have an `embedding_json`. This matches the locked design ("labels without embedding still count as caption-side truth but do not move centroids") but there is no caption-side consumer built yet; the rows exist for future use, not Phase 3's own logic.
- Migration ordering risk on deploy: if `TBCC_MEDIA_GATEKEEPER_ENABLED=1` and inbox/hub-topic traffic flows before migration 114 has been applied on a given environment, `record_label` will hit the missing-table failure path on every call — harmless now (rolls back, skips, logs at debug level) but worth deploying the migration first in the normal case.

## Operator smoke (Tray only)

Not applicable — no bot Start, no live Telegram or CLIP sidecar calls exercised. All 49 tests use mocked DB sessions, mocked/fake Redis, and monkeypatched sidecar functions. The migration was verified against a throwaway local SQLite file only (not the real Postgres island DB) — do not run `alembic upgrade head` against `api.powercore.app` from this session.

## Do not

- push / start bots / touch `.env` / Phase 4 until Cursor ACK
