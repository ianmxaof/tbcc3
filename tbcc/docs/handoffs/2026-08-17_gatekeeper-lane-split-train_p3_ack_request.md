# Directive for Hermes — review gatekeeper-lane-split-train Phase 1-3, ACK for Phase 4

Repo: `C:\Powercore-repo-main\telegram_bot2`
Branch: `lane-c/gatekeeper-lane-split` (not pushed)
Work done by: Claude Code (Sonnet), Lane C — mechanical implementation of a
locked design. Every phase went through advisor review before landing;
several real bugs were caught and fixed pre-commit (see each report's
"Self-caught regressions" section).

## Read in this order

1. `tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train.md`
   — the locked design doc. Cursor's Phase 1 ACK is already appended near the
   top (search "Cursor ACK — Phase 1"). That ACK block is the pattern to
   follow for your own Phase 3 ACK: a short dated section prepended to this
   same file, with a go/no-go and any new constraints for Phase 4.
2. `tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train_report.md`      (Phase 1)
3. `tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train_p2_report.md`   (Phase 2)
4. `tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train_p3_report.md`   (Phase 3 — most recent, read closely)

Each report has the same structure: Done / Files touched / Verification run /
Risks / Operator smoke / Do not. The "Risks / open questions" section in each
is where every deliberate deviation from the locked spec is flagged for
explicit ACK — do not treat silence on those as approval.

## Commits this work spans (newest first, HEAD is 217babe)

```
217babe docs: reverse handoff report — phase 3
3f81412 feat(gatekeeper): online prototype bank + CLIP embeddings (Phase 3)
3fcc4c7 docs: reverse handoff report — phase 2
3fd6f17 feat(gatekeeper): inbox mixed-split auto-route + preselect (Phase 2)
96c6cb8 docs: reverse handoff report — phase 1
5aa1e34 fix(gatekeeper): keep inbox lane_fit semantics safe, guard caption_confidence
e4fa9f9 feat(gatekeeper): CLIP/caption -> AOF lane mapper for mixed-bulk split (Phase 1)
```

Note: `3b5e938` and `9070fff` (secretary work) sit interleaved on this same
branch — not mine, a concurrent session committed them. Flagged in the
Phase 1 report; not touched, not to be attributed to this work.

## Open deviations needing your explicit ACK

Pulled from the three reports — verify against the diffs, don't just take
this document's word for it.

**Phase 1:**
- Dropped `suggest_lane_keys_from_tags` from `map_text_to_lanes` (false-positives
  on ordinary captions under its fuzzy token-in-fragment fallback).
- `caption_confidence` returns 0.0 for tags that resolve in `LANE_TAG_MAP` but
  have no AOF split lane (`#amateur`, `#packs`, `#cosplay`, `#homemade`).

**Phase 2:**
- Confident auto-route does NOT call `operator_approve_media` — reasoned as
  "same Telethon reuse point" (`enqueue_lane_route_for_media`), not "same
  function call," to avoid firing N micro-pull Celery tasks against the one
  Telethon admin session on a bulk auto-split.
- `auto_tag_enrich.py` now populates `out["clip_slug"]` (previously always
  `None` from that caller) — a behavior change beyond the split path itself,
  since it also unlocks `glob_quality`'s `clip_lane_match` boost on that pass.
- Inbox shortcut channel (`INBOX_CHANNEL_IDENT`) does not auto-split — origin
  resolves to `OTHER`, not trusted hub, because `is_storage_hub_source_label`
  doesn't recognize that channel id. Left out of scope (trust-doctrine
  change, not a split-logic change).

**Phase 3:**
- Centroid cache is invalidated on every embedding-bearing write, not only
  "as soon as that lane's count >= PROTOTYPE_MIN" as literally worded.
- Neither operator hook (approve/reject) makes a synchronous CLIP embed
  call — avoids adding sidecar HTTP latency to an interactive Telegram tap;
  embeddings for operator-approved items still arrive later via the
  `hub_topic` hook if/when `auto_tag_enrich` runs.

## Also worth independently confirming, not just trusting the report

- Migration `114_gatekeeper_lane_labels` was verified against a throwaway local
  SQLite DB only (stamp-from-113, upgrade, downgrade) — never against the
  real Postgres island DB. If you want stronger confidence before Phase 4,
  that's a legitimate ask.
- "`no_signal` is the majority path in default config" — untagged captions +
  `TBCC_CLIP_CATEGORIZE_URL` usually unset means most inbox items still won't
  auto-split today. This is stated as expected/correct in the Phase 2 and 3
  reports, not a bug — worth deciding whether that's acceptable to ship as-is
  or whether Phase 4 (or a later phase) should address it.

## What to send back

Prepend a dated "Hermes ACK — Phase 3" section to the top of
`2026-08-17_gatekeeper-lane-split-train.md` (same location/format as the
existing Cursor ACK block), containing:

1. go / no-go on Phase 4
2. explicit ACK or override on each deviation listed above
3. any new constraints Phase 4 must follow (mirrors how Cursor's Phase 1
   ACK added numbered constraints into the Phase 2 section)
4. confirmation of what NOT to do (no push, no bot Start, no `.env`, no
   island deploy — same standing rule as every prior phase)

Claude Code will pick up Phase 4 from that ACK block once you're done.
