# Reverse handoff — gatekeeper-lane-split-train

- Branch: `lane-c/gatekeeper-lane-split`
- Head commit(s) this phase (hash + subject): `3fd6f17` feat(gatekeeper): inbox mixed-split auto-route + preselect (Phase 2)
- Status: Phase 2 complete

## Done

- `app/services/gatekeeper_inbox_split.py` (new): implements locked rule E.
  - `resolve_proposed_lanes(media, enrich, caption)` — blends caption (via Phase 1's `caption_confidence`/`map_text_to_lanes`) with CLIP labels from `enrich["clip_labels"]` (`[{"slug": str, "score": float}, ...]` — **real per-slug scores only**; `map_clip_slugs_to_lanes` is never called with a bare slug list here). Same lane hit from both sources keeps the higher score and is tagged `source: "mixed"`.
  - `maybe_auto_split_inbox(db, media_id, *, caption="", enrich=None)` — the decision engine. Guards, in order: inbox-split enabled → media exists → `classification_json.gatekeeper.globs.lane_fit.expected == "inbox"` → origin is trusted Storage Hub (never scrape) → not hard-blocked (`verdict == "reject"` or any `hard_block:*` flag in blocks/warnings). Then: confident single lane (score ≥ `AUTO_SPLIT_MIN` and margin ≥ `AUTO_SPLIT_MARGIN`) → `_apply_auto_route`; two-or-more strong lanes or low confidence → `set_picked_lanes` with the top 1-2 lanes; no signal at all → no-op with `reason: "no_signal"`.
  - `_apply_auto_route` does **not** call `operator_approve_media` — see Risks below for why. It directly stamps `media.status = "approved"`, assigns `pool_id` via `pool_id_for_network_key`, writes a sibling `classification_json.gatekeeper_split` key (does not touch `gatekeeper.verdict` — see idempotency note), and calls `enqueue_lane_route_for_media` (the same Celery→Telethon forward path `operator_approve_media` itself uses — reuse point satisfied without duplicating Telethon).
  - Idempotency: a Redis marker (`tbcc:gk:inbox_split:{media_id}`, 30-day TTL) is set only on the auto-route action, since `apply_gatekeeper_after_ingest` runs this twice per inbox item (ingest-time caption-only, then again if/when `auto_tag_enrich`'s CLIP pass runs) — the second confident decision returns `already_routed` instead of forwarding again.
- `app/services/media_gatekeeper.py`: `apply_gatekeeper_after_ingest` now calls `maybe_auto_split_inbox` for every `expected_lane == "inbox"` item, **regardless of verdict** (Cursor ACK constraint #1 — untagged trusted inbox already reaches `approve` at quality ~75, the majority mixed-dump shape). The split call runs **before** the quarantine-review enqueue and suppresses it when the split action was `auto_route` or `already_routed` — see the ordering bug caught below.
- `app/services/auto_tag_enrich.py`: the existing CLIP-niche-classify block now also populates `out["clip_labels"]` (real per-slug scores from the sidecar) and `out["clip_slug"]` before calling `apply_gatekeeper_after_ingest(db, media_id, enrich=out)` — this is the "Celery task that classifies then maybe_auto_split_inbox" the locked design asked for; no new Celery task was needed since this existing enrich pass already re-invokes `apply_gatekeeper_after_ingest` with CLIP data in hand.
- Env vars: `TBCC_GATEKEEPER_INBOX_SPLIT` (default `1`), `TBCC_GATEKEEPER_AUTO_SPLIT_MIN` (default `0.28`), `TBCC_GATEKEEPER_AUTO_SPLIT_MARGIN` (default `0.04`).

### Self-caught regressions (advisor review, before this landed on Cursor's desk)

Two real bugs, both invisible to the first pass of tests:

1. **Ordering**: the quarantine-review enqueue originally ran before the split decision. A tagged inbox item that auto-routed would still get posted as a review card; tapping Approve on that card would call `operator_approve_media`, whose `prior not in ("quarantine", ...)` guard does **not** block (the gatekeeper verdict itself is untouched by the split — only a sibling `gatekeeper_split` key changes), causing a second `enqueue_lane_route_for_media` (duplicate forward) plus an unwanted `enqueue_micro_pull_for_lane` and `enqueue_vault_approved_media`. Fixed by reordering: split runs first, and its result suppresses the review enqueue.
2. **Untested idempotency guard**: none of the original tests patched `gatekeeper_inbox_split._redis`, and Redis is unreachable in this environment — `_split_already_routed`/`_mark_split_routed` were silently swallowing connection errors and always returning "not marked," so the guard that's supposed to stop a duplicate forward on the second (enrich) pass was completely inert and unverified. Added `_patch_split_redis` (a real fake store) to every test that calls `maybe_auto_split_inbox`, plus a dedicated `test_second_pass_does_not_duplicate_route` that calls the function twice and asserts the forward Celery enqueue fires exactly once.

Also deliberately did **not** route the confident case through `operator_approve_media`, even though the locked doc says "same path as operator approve": that function's non-approval side effects on the quarantine branch — `record_operator_approve` (pollutes the reject/approve streak that drives source demotion with an event no human performed) and `approve_triggers_micro_pull()` defaulting to `1` (`enqueue_micro_pull_for_lane` per item) — would mean a 200-item bulk dump auto-splitting fires 200 SCRP micro-pull tasks, all wanting the one Telethon admin session, against the root CLAUDE.md's "one Telethon admin session at a time for heavy scrapes." Read "same path" as "same Telethon reuse point" (`enqueue_lane_route_for_media`), not "same function call." Flagging for explicit ACK since it's a interpretation of locked wording, not a bug fix.

## Files touched

- `tbcc/backend/app/services/gatekeeper_inbox_split.py` (new)
- `tbcc/backend/app/services/media_gatekeeper.py` (edit — `apply_gatekeeper_after_ingest` hook + ordering)
- `tbcc/backend/app/services/auto_tag_enrich.py` (edit — `clip_labels`/`clip_slug` enrich keys)
- `tbcc/backend/tests/test_gatekeeper_inbox_split.py` (new, 16 tests)

## Verification run

```
cd tbcc/backend
py -3.13 -m pytest tests/test_media_gatekeeper_service.py tests/test_gatekeeper_inbox_split.py tests/test_gatekeeper_lane_picker.py tests/test_gatekeeper_review.py -x -q --tb=short
# 38 passed in 369.43s
```

Also re-ran the full Phase 1 command to confirm no regression from the `media_gatekeeper.py`/`auto_tag_enrich.py` edits:

```
py -3.13 -m pytest tests/test_aof_lane_tag_map.py tests/test_media_gatekeeper_spec.py tests/test_gatekeeper_clip_lane_map.py -q --tb=short
# 46 passed in 13.09s
```

`test_storage_deposit_auto_approve.py` (7 passed) — the other existing caller of `auto_tag_enrich`'s enrich pipeline — also re-run clean.

## Risks / open questions

- **Deviation, needs explicit ACK — not via `operator_approve_media`.** See "Self-caught regressions" above. This is the biggest interpretation call in this phase.
- **Deviation, needs explicit ACK — `out["clip_slug"]` in `auto_tag_enrich.py` was never populated before this change.** `MediaGatekeeperInput.clip_slug` was always `None` from that caller, meaning `glob_lane_fit`'s CLIP-override-`detected` branch and `glob_quality`'s `clip_lane_match` boost could never fire on the enrich pass. Fixing it (because the locked design explicitly names `clip_slug` as an enrich key `apply_gatekeeper_after_ingest` should accept) is a behavior change beyond the inbox-split path itself — it can now also affect named-topic-deposit quality scoring on the enrich pass. Flagging exactly like the Phase 1 `suggest_lane_keys_from_tags` drop.
- **`no_signal` is the majority path in default config, same root cause named once, not twice.** Untagged captions score `caption_confidence == 0.0`; `TBCC_CLIP_CATEGORIZE_URL` is typically unset (`clip_classifier_enabled() == False`), so `enrich["clip_labels"]` never gets populated by `auto_tag_enrich`'s CLIP-niche-classify block, and separately `TBCC_ENRICH_ON_IMPORT` often gates that Celery pass off entirely for `/deposit`. Both gates default to "off" in the environment this doc describes, so on the majority path `resolve_proposed_lanes` returns `[]` and the item sits exactly where it does today (untagged trusted inbox still approves at ~75, no lane, same as before this phase). That is correct behavior — no threshold was lowered, no signal invented — but "mixed dump is classified per item" is only true with the sidecar on. This is a config/infra dependency, not a code gap.
- **Rule D's inbox shortcut channel (`INBOX_CHANNEL_IDENT`) does not auto-split.** Verified: `queue_inbox_channel_deposit` (`storage_topic_deposit.py:853`) sets `source_channel = "telegram:{INBOX_CHANNEL_IDENT}"` — no `#topic:` suffix, and a different chat id than `STORAGE_HUB_IDENT`. `expected_lane` *does* still resolve to `"inbox"` (via the pool-id fallback in `build_gatekeeper_input`, since `queue_inbox_channel_deposit` assigns the inbox pool directly) — my earlier assumption that it wouldn't was wrong. The actual blocker is `resolve_ingest_origin` → `is_storage_hub_source_label` doesn't recognize `INBOX_CHANNEL_IDENT`, so origin resolves to `OTHER` and the `not_trusted_hub_origin` guard blocks it. Extending origin-trust to the shortcut channel touches core trust-doctrine code shared well beyond this feature; leaving it out of Phase 2 scope and flagging for Cursor's call rather than silently narrowing rule D.
- **`route_media_to_lane_topics` needs `telegram_message_id > 0`** — bails with `no_telegram_message_id` for the local-bytes pool-import ingest path. The Redis "already routed" marker is set *before* that Celery task runs, so such an item would end up approved, lane-stamped, pool-assigned, but never actually forwarded — and un-retryable, since the marker blocks a second attempt. Pre-existing limitation for operator approve too, but silent here since there's no card/human to notice. One risk bullet, not fixed.

## Operator smoke (Tray only)

Not applicable — no bot Start, no live Telegram calls made or tested. All 38 tests use mocked DB rows, mocked Redis, and monkeypatched `enqueue_lane_route_for_media`/`pool_id_for_network_key`. First real-world exercise happens only when CLIP sidecar + a live inbox deposit are both present, which needs Cursor/operator judgment on when to flip `TBCC_CLIP_CATEGORIZE_URL` on, not a Tray smoke here.

## Do not

- push / start bots / touch `.env` / Phase 3 until Cursor ACK
