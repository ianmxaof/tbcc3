# Reverse handoff — gatekeeper-lane-split-train

- Branch: `lane-c/gatekeeper-lane-split`
- Head commit(s) this phase (hash + subject):
  - `e4fa9f9` feat(gatekeeper): CLIP/caption -> AOF lane mapper for mixed-bulk split (Phase 1)
  - `5aa1e34` fix(gatekeeper): keep inbox lane_fit semantics safe, guard caption_confidence
  - Note: `3b5e938` ("feat(secretary): G11 silent business replies...") sits between these two on the branch. It is **not** my commit — a concurrent session appears to be committing secretary work to this same checked-out branch/working tree. Flagging in case Cursor wants it split off before merge; not touched or altered here.
- Status: Phase 1 complete

## Done

- `app/data/clip_slug_lane_map.py` (new): `CLIP_SLUG_TO_LANE` maps ~90 high-volume slugs sampled from `tbcc/data/clip-categories.json` (1260 total) onto the 11 AOF split lanes (`ass`, `big_tits`, `blowjob`, `bop`, `goon`, `ai`, `milf`, `voyeur`, `taboo`, `abg`, `full_length`). Not exhaustive — only the obvious high-confidence slugs, per the locked instruction to sample rather than map all 1260.
  - `SPLIT_LANE_KEYS` derived as `CONTENT_LANE_NETWORK_KEYS - {"inbox", "packs"}` (not hardcoded) so it stays in sync with `aof_storage_hub_map.py` if a lane is ever added/removed there.
  - `map_clip_slugs_to_lanes(slugs, *, scores=None)` — direct dict hit wins; unmapped slugs fall back to a word-boundary-guarded `LANE_TAG_MAP` fragment match; returns lanes ranked by score (default weight 1.0 per hit, real scores respected when passed).
  - `map_text_to_lanes(caption, filename="")` — word-boundary-guarded scan of `LANE_TAG_MAP` fragments, filtered to `SPLIT_LANE_KEYS`, returns *all* plausible lanes ranked (not just top-1, unlike the existing `detect_lane_from_text`).
  - `caption_confidence(caption, filename="")` — 1.0 for an exact hashtag/token match, 0.55 for a fragment/substring match, 0.0 for no match — **only** when the matched tag resolves to a split lane. This is the number Phase 2's auto-split threshold will consume per locked rule E.
- `app/data/media_gatekeeper_spec.py`: `glob_lane_fit` extended (no signature change, **pass/fail/score_delta semantics byte-identical to pre-Phase-1** — verified against `d923e6b`):
  - New `extra["proposed_lanes"]` — ranked union of caption-mapped and CLIP-mapped lanes (caption first), attached on **every** return path, including `pass_=False`.
  - New `lane_ambiguous` flag when caption's top lane and CLIP's top lane disagree.
  - No change to when `lane_fit.pass_` is `True`/`False`, to `score_delta`, or to the `LANE_UNKNOWN_ALLOW_KEYS` short-circuit for inbox/ai. A tagged inbox item still hits the `lane_mismatch` branch (`pass_=False`) exactly as before, which still forces `quarantine` in `aggregate_verdict` — Phase 1 adds the lane *signal*, it does not add a routing *decision*. That decision belongs to Phase 2's `maybe_auto_split_inbox`.

### Self-caught regressions (advisor review, before this landed on Cursor's desk)

An earlier draft of this phase let `glob_lane_fit` short-circuit `pass_=True` for *any* `expected_lane in {None, "inbox"}`, including tagged content. That looked correct against the spec text ("lane_fit.pass_ stays True for inbox unknown") but actually meant a trusted hub inbox deposit with a caption tag (e.g. `#ass`) skipped straight past the quarantine gate to `approve` — with no lane and no Phase 2 routing logic to catch it, since that logic doesn't exist yet. Caught via `advisor()` before commit, verified empirically with `git show d923e6b:...` (true pre-Phase-1 baseline) vs. current, and reverted so only the *untagged* case (already `LANE_UNKNOWN_ALLOW_KEYS`-exempt, already `approve`-eligible pre-Phase-1) is unaffected.

A second round caught `caption_confidence`/`map_text_to_lanes` false-matching plain English via 2-3 letter `LANE_TAG_MAP` fragments (`"ai"` inside `"waiting"`, `"abg"` inside `"i think this is great"` via the now-removed `suggest_lane_keys_from_tags` fallback) — fixed with a word-boundary guard for fragments under 4 chars.

A third round caught `caption_confidence` returning `1.0` for tags that resolve in `LANE_TAG_MAP` but have no AOF split lane (`#amateur`, `#packs`, `#cosplay`, `#homemade`) — a max-confidence score with zero proposed lanes, which is exactly the silent-misroute shape Phase 2's rule E ("a 1.0 caption hit may auto-route") would have exploited. Fixed by gating both branches on `SPLIT_LANE_KEYS`; added an explicit test plus a structural invariant test (`caption_confidence(c) > 0 iff map_text_to_lanes(c)` is non-empty) that holds by construction as `LANE_TAG_MAP` grows.

## Files touched

- `tbcc/backend/app/data/clip_slug_lane_map.py` (new)
- `tbcc/backend/app/data/media_gatekeeper_spec.py` (edit — `glob_lane_fit` only)
- `tbcc/backend/tests/test_gatekeeper_clip_lane_map.py` (new)

## Verification run

```
cd tbcc/backend
py -3.13 -m pytest tests/test_aof_lane_tag_map.py tests/test_media_gatekeeper_spec.py tests/test_gatekeeper_clip_lane_map.py -x -q --tb=short
# 46 passed in 13.40s
```

Also ran the downstream gatekeeper suites not in the Phase 1 command list, to check the `glob_lane_fit` extras addition didn't regress anything that reads `classification_json.gatekeeper`:

```
py -3.13 -m pytest tests/test_media_gatekeeper_service.py tests/test_gatekeeper_lane_picker.py tests/test_gatekeeper_review.py -q --tb=short
# 22 passed in 362.63s — re-run after the caption_confidence fix landed (was also 22 passed
# in 362.82s before it, as expected: caption_confidence has zero callers yet)
```

`grep` confirmed `glob_lane_fit` has no callers outside `media_gatekeeper_spec.py` and the new test file.

## Risks / open questions

- **Spec deviation — needs explicit ACK:** Phase 1 text says `map_text_to_lanes` should "wrap `detect_lane_from_text` / `suggest_lane_keys_from_tags`." I dropped the `suggest_lane_keys_from_tags` call entirely — its `token in fragment` fallback (built for short scrape hashtags) false-positives on ordinary caption sentences, and under the word-boundary guard its output is a strict subset of the direct `LANE_TAG_MAP` fragment scan, so keeping the call would have been dead code with a bug risk attached. Flagging as a deviation rather than letting it pass silently.
- **`CLIP_SLUG_TO_LANE` coverage:** curated sample (~90 of 1260 slugs), not exhaustive — fragment fallback covers the rest, but quality on the untabulated slugs is unverified without a live CLIP sidecar run. In scope was "sample the catalog," not "map every slug."
- **`scores` kwarg on `map_clip_slugs_to_lanes` is unused by any caller today** — a bare slug list scores every hit at 1.0 (certainty). Phase 2/3 must pass real CLIP softmax/cosine scores; stating this as a hard rule rather than an open question, since defaulting to 1.0 would clear `AUTO_SPLIT_MIN`/margin unconditionally.
- **`caption_confidence` returns 0.0 for real-but-unroutable tags** (`#amateur`, `#packs`, `#cosplay`, `#homemade`) — this is deliberate (those tags have no AOF split lane), but it means "tagged with something real" and "no tag at all" are indistinguishable in the score Phase 2 consumes. Under rule E, 0.0 falls through to CLIP/prototype or quarantine, which is the safe default — but it's a design choice Cursor should see stated, not discover later.
- **Forward risk for Phase 2, not a Phase 1 defect:** untagged trusted-hub inbox deposits already reach `approve` at quality_score 75 today (pre-existing behavior, unchanged by this phase — `50 base − 5 lane_unknown + 20 trusted + 10 HD resolution`). Bulk dumps are frequently caption-free, so this is likely the *majority* path through the inbox, not an edge case. Phase 2's `maybe_auto_split_inbox` will need to hook items that already landed on `approve` (not only `quarantine`), or the common case skips the split entirely. Question for Cursor, not solved here.
- Named-topic deposits (expected_lane = real content lane) are untouched — mismatch still quarantines exactly as before, per locked design.

## Operator smoke (Tray only)

Not applicable — Phase 1 is pure functions only (no Telegram, no DB, no worker wiring). Nothing to smoke-test on Tray yet. First operator-visible behavior lands in Phase 2 (auto-split + review card preselect).

## Do not

- push / start bots / touch `.env` / Phase 2 until Cursor ACK
