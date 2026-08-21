# Report: TBCC taboo tag corpus (Entropy Scan pick, devops lens)

**Against:** locked plan pasted in-thread ("Claude Code — TBCC taboo tag corpus (Entropy Scan pick)")
**Date:** 2026-08-21

## Summary

Built a first-party, versioned, structured tag corpus (parent/child + aliases + lane binding) to replace the one-time-pasted, unversioned 1,704-tag snapshot as the source of vision-LLM cue vocabulary — specifically to close the `taboo` lane gap that never improved under any prompt or model change earlier tonight. All five done-conditions from the plan are met; all four specified test files pass together, plus a broader 59-test regression sweep across the wider gatekeeper/CLIP-lane surface with no failures.

## What shipped

**New files:**
- `tbcc/backend/app/data/tag_corpus.json` — versioned (`schema_version: "1.0.0"`) corpus data file. 18 nodes: one thin stub per canonical lane (14), plus a real `taboo` subtree with 4 child categories (stepfamily roleplay, age-gap, authority-figure roleplay, infidelity roleplay) carrying 33 total aliases — all standard adult-industry roleplay/fauxcest vocabulary, no underage or real-incest framing per the plan's explicit constraint.
- `tbcc/backend/app/services/tag_corpus.py` — loader/validator module. Parses + validates the JSON (rejects lane_keys outside `CANONICAL_LANE_KEYS`, duplicate slugs, unknown `parent_slug` refs), builds an alias→slug index with a first-registered-wins dedup rule, and exposes `resolve_lane_keys_for_alias()` (walks the parent chain), `aliases_for_lane()`, `cue_bullet_for_lane()` (comma-joined prompt text), and two reshaping helpers (`clip_slug_aliases_for_lane()`, `lane_tag_map_aliases_for_lane()`) for the merge points below.
- `tbcc/backend/app/services/media_lane_vision_classify.py`, `tbcc/backend/tests/test_media_lane_vision_classify.py` — these existed as uncommitted work from earlier tonight (multi-label vision classification, shipped in-session before this slice); listed here since this slice modified both further.

**Modified:**
- `app/services/aof_lane_tag_map.py` — `LANE_TAG_MAP` now gets an additive merge of corpus-derived aliases at import time (`_merge_corpus_lane_tag_aliases()`, called once after `CANONICAL_LANE_KEYS` is defined). Never overwrites an existing hand-curated entry — `setdefault` only.
- `app/data/clip_slug_lane_map.py` — same pattern for `CLIP_SLUG_TO_LANE` (`_merge_corpus_clip_slug_aliases()`), scoped to `SPLIT_LANE_KEYS` (the 11 visually-classifiable feed lanes this map already targets). Multi-word aliases get hyphenated to match this map's existing key style (`"step mom"` → `"step-mom"`).
- `app/services/vision_llm.py` — added an optional `prompt_override` param to `analyze_image_bytes()` so the AOF-specific multi-label prompt doesn't touch the shared `_niche_prompt()` path used by `media_niche_classify.py` (local-disk sorting) and `watch_folder_nsfw.py`, both of which still depend on the old bare `primary_slug` shape.
- `media_lane_vision_classify.py` — the taboo cue line in the vision prompt is now generated from `tag_corpus.cue_bullet_for_lane("taboo")` at call time (`_build_lane_vision_prompt()`), not hand-pasted. Falls back to a short static line if the corpus fails to load, so classification never hard-fails on it.
- `tests/test_aof_lane_tag_map.py`, `tests/test_gatekeeper_clip_lane_map.py` — added end-to-end checks that a corpus-only alias (`stepmom` / `step-mom`) resolves to `taboo` through each map, and that pre-existing hand-curated entries (`taboo`, `stepsis`) are untouched.

## Done-conditions — verified against the plan's own list

1. ✅ Versioned, structured corpus on disk with parent/child + aliases + lane binding — `tag_corpus.json`, `schema_version: "1.0.0"`.
2. ✅ Real taboo subtree, not a single token — 33 aliases across 4 child categories (stepsis/stepmom/stepdad/stepbro/stepson/stepdaughter/fauxcest/family-roleplay, age-gap/old-young, babysitter/authority-figure, cheating/affair).
3. ✅ Vision lane classification consumes the corpus for taboo cues, not the one-time pasted blob — confirmed the built prompt actually contains `stepsis`, `stepmom`, `fauxcest`, `cheating`, `babysitter`, `age gap` at runtime, not just in the corpus file.
4. ✅ Unit tests prove (a) alias→taboo resolution and (b) non-zero taboo hits replaying a fixture set through the real cue/vocab wiring (mocked LLM, but the prompt-build → call → parse → persist path executes for real on every fixture item — verified the captured prompt argument, not just the mock's echo).
5. ✅ This report. No deploy performed — nothing pushed to the island, no `git commit` (kept as uncommitted working-tree changes per your "no deploy unless operator asks").

## Verification run

```
py -3.13 -m pytest tests/test_tag_corpus.py tests/test_media_lane_vision_classify.py tests/test_aof_lane_tag_map.py tests/test_gatekeeper_clip_lane_map.py -x -q --tb=short
48 passed, 9 warnings (pre-existing SQLAlchemy utcnow() deprecation, unrelated)
```

Broader regression sweep (gatekeeper/CLIP-lane surface, to check the two shared files I modified didn't break anything downstream):
```
py -3.13 -m pytest tests/test_gatekeeper_inbox_split.py tests/test_media_gatekeeper_service.py tests/test_gatekeeper_lane_picker.py tests/test_gatekeeper_prototypes.py tests/test_gatekeeper_review.py -q --tb=short
59 passed in 374.82s
```

One note: `tests/test_tag_corpus.py` was edited externally partway through this slice (a simpler 11-test version replaced my original ~15-test draft). Ran it as-is against the implementation — all 11 pass cleanly, no conflict with what shipped, so left it as the current state rather than reverting.

## Refresh process (operator adds aliases by hand later)

1. Open `tbcc/backend/app/data/tag_corpus.json`.
2. To extend an existing category: add a term to that node's `aliases` array (lowercase, natural spacing — the loader normalizes and reshapes for each consumer).
3. To add a new subcategory: add a node with a unique `slug`, `parent_slug` pointing at the parent category, and `lane_keys` restricted to `CANONICAL_LANE_KEYS` (the loader raises on anything else — a typo'd lane key fails fast at load time, not silently).
4. Bump `schema_version` on structural changes (new top-level categories, renamed slugs) — not required for a pure alias addition.
5. Restart the process (or call `tag_corpus.load_tag_corpus.cache_clear()` in a live process) — the loader caches per-process via `lru_cache`.
6. No code changes needed for a pure vocabulary addition — the taboo prompt line, `LANE_TAG_MAP`, and `CLIP_SLUG_TO_LANE` all pull from the same file automatically on next load.

## Explicitly not touched (per plan's out-of-scope list)

Q&A batch-review mis-tagging bug, container-patch-without-restart guardrails, Telethon session contention enforcement, `enqueue_lane_route_for_media`'s silent `logger.debug` swallow, any third-party scraping (StashDB/coomer/etc.), fine-tune dashboard, operator-correction loop, sidecar `.tbcc-meta.json` removal, making vision primary for live routing, local tray/bots/Postgres/Celery, `.env` edits, remote pushes, island deploy. `tbcc_tags` DB schema also untouched — went with the versioned data-file SSOT per the plan's explicit preference, no alembic migration needed for this slice.
