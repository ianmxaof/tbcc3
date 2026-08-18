# Handoff: Gatekeeper mixed-bulk lane split + online labels

**Date:** 2026-08-17  
**Lane:** Claude Code (Sonnet) — mechanical implement of a **locked** design  
**Reverse report:** `tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train_report.md` (Phase 1); later phases append `_p2` / `_p3` / `_p4` before `_report.md`

Operator goal: dump mixed NSFW into Storage Hub inbox; gatekeeper splits into the **same categories the AOF channels / hub topics already use**; every operator-labeled item trains a prototype bank so visual split improves over time.

Doctrine in this file is **locked**. Do not invent new channels, GPU fine-tunes, or vision-LLM judges.

**Handoff v1.1 (2026-08-17):** folded three cheap robustness bits (running centroid, Redis invalidate-on-write, caption-confidence as a number + CLIP∩prototype agreement boost). Explicitly rejected: album k-means, spaCy/TF-IDF, softmax-entropy auto-route, float16 quantization, Prometheus `/gatekeeper/health`, operator rate-limits/trust scores, `lane_parents.json` sub-lanes, trimmed-mean/variance auto-recalibrate. Those are architecture tourism for a single-operator hub.

**Cursor ACK — Phase 1 (2026-08-17):** go. Commits `e4fa9f9` + `5aa1e34` match git; pytest 46 passed re-run here. Spec deviations ACK'd: drop `suggest_lane_keys_from_tags` (false-positives); `caption_confidence==0` for unroutable tags (`#amateur`/`#packs`); mapper sample ~90 slugs is enough. Phase 2 constraints from the report (must follow):

1. `maybe_auto_split_inbox` runs on **inbox-origin items even when gatekeeper already `approve`d** (untagged trusted hub + HD already scores ~75 and auto-approves today — that is the majority mixed dump). Do not only hook quarantine.
2. Always pass real CLIP scores into `map_clip_slugs_to_lanes(..., scores=...)`. Bare slugs default to 1.0 and would clear `AUTO_SPLIT_MIN` unconditionally.
3. Route from `proposed_lanes` + caption/CLIP/prototype scores, **not** raw `clip_slug` (`detected` still stores the catalog slug).
4. Do not start Phase 2 until the operator says so. Do not push. Secretary commits `3b5e938` / `9070fff` are on this same branch — leave them; do not mix more unrelated work into gatekeeper commits.

---

**Hermes ACK — Phase 3 (2026-08-17):** go. Phase 1 report (46 pytest), Phase 2 report (38 pytest, incl. 16 new inbox-split tests + idempotency guard), Phase 3 report (27 pytest + 17 inbox-split, 49 combined) read in full against the diffs. Commit chain on branch matches the handoff (`e4fa9f9`, `5aa1e34`, `3fd6f17`, `3f81412`). Standing rule reaffirmed: no push, no bot Start, no `.env`, no island deploy.

**Deviations ACK'd (all accepted as-is):**

- **Phase 1 — drop `suggest_lane_keys_from_tags`.** Word-boundary-guarded direct `LANE_TAG_MAP` fragment scan is strictly better; keeping the call would be dead code with false-positive risk on ordinary captions. Keep the drop.
- **Phase 1 — `caption_confidence==0.0` for unroutable tags** (`#amateur`/`#packs`/`#cosplay`/`#homemade`). Those tags resolve in `LANE_TAG_MAP` but have no AOF split lane. 0.0 is the safe score and falls through to CLIP/prototype or quarantine under rule E. Deliberate design choice, not a bug — stated here so it's visible, not discovered later.
- **Phase 2 — auto-route does NOT call `operator_approve_media`.** Same Telethon reuse point (`enqueue_lane_route_for_media`) is satisfied. The alternative — routing 200 bulk items through `operator_approve_media` — would fire 200 SCRP micro-pull tasks against the one Telethon admin session and pollute the approve/reject streak with events no human performed. Read "same path" as "same Telethon reuse point," not "same function call." **Constraint carried into Phase 4:** do not reintroduce the `operator_approve_media` call for bulk auto-route without re-auditing that cascade.
- **Phase 2 — `auto_tag_enrich.py` now populates `out["clip_slug"]`.** Behavior change beyond the split path: `glob_lane_fit`'s CLIP-override-`detected` branch and `glob_quality`'s `clip_lane_match` boost can now fire on the enrich pass (they were always `None` from that caller before). Accept exactly as flagged.
- **Phase 2 — inbox shortcut channel (`INBOX_CHANNEL_IDENT`) does not auto-split.** Origin resolves to `OTHER`, not trusted hub, because `is_storage_hub_source_label` doesn't recognize that channel id. Trust-doctrine change, not a split-logic change — leave out of scope.
- **Phase 3 — centroid cache invalidated on every embedding-bearing write**, not only "as soon as that lane's count >= PROTOTYPE_MIN." Strict superset of the literal instruction; harmless (a stale-but-valid cache below `PROTOTYPE_MIN` doesn't matter since `load_centroids` filters by that threshold) and avoids an off-by-one risk in a conditional invalidate. Keep.
- **Phase 3 — no synchronous CLIP embed on either operator hook.** `operator_approve_media` / `operator_reject_media` both call `record_label` with `embedding=None`. Embedding a fresh image synchronously inside an operator's Telegram tap would add sidecar-HTTP latency to an interactive action. Embedding for approved items still arrives later via the `hub_topic` hook if/when `auto_tag_enrich` runs. Same reasoning as the Phase 2 report's identical deviation.

**Confirm (not blockers, stated for visibility):**
- Migration `114_gatekeeper_lane_labels` verified against throwaway local SQLite only (stamp-from-113, upgrade, downgrade) — never against the real Postgres island DB. Reasonable ask for Phase 4 handoff before any island deploy of this branch; not an ACK gate.
- "`no_signal` is the majority path in default config" — untagged captions + `TBCC_CLIP_CATEGORIZE_URL` typically unset means most inbox items still won't auto-split today. Correct behavior (no threshold lowered, no signal invented), but "mixed dump is classified per item" is only true with the sidecar on. Config/infra dependency, not a code gap. If Phase 4 wants to improve it, the lever is CLIP sidecar on + caption presence, not lowering `AUTO_SPLIT_MIN` to manufacture volume.

**New constraints Phase 4 must follow:**

1. Same standing rule: no push, no bot Start, no `.env`, no island deploy.
2. Docs: add P5 section to `MEDIA_GATEKEEPER.md` (env vars, status table P5 done, keep red lines); add TEST_MAP.md row **Gatekeeper lane split** → the pytest files above.
3. Optional `export_aof_lane_clip_catalog.py` is fine (code + test only; do not overwrite `tbcc/data/clip-categories.json`).
4. If review-card text can cheaply show "proposed: 🍑 ass 0.41 / 🍒 big_tits 0.22", add one line to the existing quarantine card formatter only — no panel redesign.
5. Do not reintroduce `operator_approve_media` for bulk auto-route (per Phase 2 deviation constraint above).
6. Migration 114 must land before gatekeeper traffic + env enablement on any environment running the split path. `record_label` rolls back on failure, but a missing table under load is a deployment-order risk — call it out in deploy docs.
7. Before any island deploy of this branch, operator should verify migration 114 against the real Postgres island DB (not just throwaway SQLite) — reasonable ask for Phase 4 handoff, not a hard gate here.
8. Synthetic fixtures only — no real NSFW media in git; keep `AGE_ADJACENT_PATTERNS`; never CSAM/underage samples in tests or docs.
9. Do not start Phase 5 until Hermes/Cursor ACK on Phase 4.

---

## Paste this into Claude Code

```
Goal
----
Make the TBCC media gatekeeper split a mixed bulk dump (AOF INBOX) into the existing AOF content-lane categories, using caption tags + CLIP (when the sidecar is up) + a growing prototype bank trained from operator/hub labels. Auto-route only when confident. Otherwise quarantine with lanes pre-selected for the operator. Visual split must get better as labeled media accumulates — without fine-tuning OpenCLIP weights and without using a vision LLM as judge for age/zoo/illegal.

Definition of done (all phases):
1. CLIP catalog slugs and caption fragments map onto AOF network_key lanes (not the raw 1400-slug catalog).
2. Mixed dump into AOF INBOX (topic 22569) is classified per item; confident items are forwarded into the matching Storage Hub lane topics via the existing route_media_to_lane_topics path.
3. Operator approve/reject + named-topic deposits write gold labels; a per-lane centroid/kNN prototype bank updates from CLIP embeddings when available.
4. Hard blocks (age-adjacent / zoo / seller-proof) and scrape-never-auto-approve doctrine are unchanged.
5. Pytest for new modules green. No .env commit, no bot Start, no push, no island deploy.

Repo
----
Git root: C:\Powercore-repo-main\telegram_bot2
Work in: tbcc/
Python: py -3.13 from tbcc/backend
Create branch: lane-c/gatekeeper-lane-split (from current HEAD). Do not push.

Read first (in this order)
--------------------------
- tbcc/docs/MEDIA_GATEKEEPER.md
- tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train.md (this file — locked design)
- tbcc/backend/app/data/media_gatekeeper_spec.py
- tbcc/backend/app/data/aof_storage_hub_map.py
- tbcc/backend/app/services/aof_lane_tag_map.py
- tbcc/backend/app/services/media_gatekeeper.py
- tbcc/backend/app/services/gatekeeper_lane_route.py
- tbcc/backend/app/services/gatekeeper_lane_picker.py
- tbcc/backend/app/services/gatekeeper_review.py (operator_approve_media)
- tbcc/backend/app/services/clip_classifier.py
- tbcc/backend/app/services/media_niche_classify.py
- tbcc/backend/app/services/auto_tag_enrich.py
- tbcc/backend/app/services/telegram_storage.py (_post_media_ingest)
- tbcc/services/clip_categorize_app.py
- tbcc/backend/tests/test_media_gatekeeper_spec.py
- tbcc/backend/tests/test_media_gatekeeper_service.py
- tbcc/backend/tests/test_gatekeeper_lane_picker.py
- tbcc/backend/tests/test_aof_lane_tag_map.py

Current state (do not rediscover from scratch)
---------------------------------------------
Gatekeeper is a metadata sorter (five globs: hard_block → trash → lane_fit → quality → enrich). Verdicts: reject | quarantine | approve. Stored under classification_json.gatekeeper (merge only).

Lane categories already exist. Canonical split targets = CONTENT_LANE_NETWORK_KEYS minus inbox and packs:

  ass, big_tits, blowjob, bop, goon, ai, milf, voyeur, taboo, abg, full_length

Storage Hub (Storage & Bot Hangar, -1003812457581) already has one forum topic per lane (AOF_STORAGE_TOPIC_MAP). Named-topic deposits are already "roughly categorized." AOF INBOX is topic 22569 / network_key=inbox / INBOX_CHANNEL_IDENT=-1003874330989.

Today mixed INBOX dumps do NOT split:
- expected_lane for inbox is "inbox", which is in LANE_UNKNOWN_ALLOW_KEYS, so untagged media PASSES lane_fit.
- Operator split is MANUAL: quarantine card emoji toggles (gk:t:) then Approve → route_media_to_lane_topics (Telethon forward into dest thread_id).
- CLIP sidecar (OpenCLIP ViT-B/32, port 8002) scores a ~1400-slug generic catalog (just-boobs, thick-booty, …). Those slugs are NOT AOF network keys. glob_lane_fit compares clip_slug == expected_lane, so CLIP almost never matches.
- telegram_storage._post_media_ingest calls apply_gatekeeper_after_ingest WITHOUT enrich. CLIP/NSFW only arrive later if auto_tag_enrich Celery runs (often off for /deposit via TBCC_ENRICH_ON_IMPORT).
- TBCC_CLIP_CATEGORIZE_URL is typically commented out in .env. Code must work with CLIP missing (caption-only) and improve when CLIP is on.
- clip_categorize_app has /classify and /classify-path only — no /embed yet.
- Alembic head is 113_secretary_draft_candidates. Next revision = 114_*.
- Vision LLM is NEVER the judge for age / zoo / illegal (MEDIA_GATEKEEPER.md red lines). CLIP is an optional SIGNAL into lane_fit/quality only.

Locked design (do not reopen)
-----------------------------
A. Taxonomy = existing AOF lanes listed above. Do NOT add ebony/bimbo/ssbbw/etc. as new network keys (those hub topics are STORAGE_OTHER_TOPICS / unmapped). Multi-lane is allowed (operator already multi-selects).

B. Training method = labeled prototype bank, NOT GPU fine-tune of OpenCLIP, NOT LoRA, NOT a new foundation model, NOT vision-LLM as judge. Store CLIP image embeddings + gold lane labels. Maintain per-lane **running sum + count** (centroid = sum/count). Do NOT rebuild from all rows every N labels (racy and slower). Min examples per lane before prototype votes (TBCC_GATEKEEPER_PROTOTYPE_MIN, default 8). Redis cache key tbcc:gk:centroids MUST be deleted inside record_label as soon as that lane's count ≥ PROTOTYPE_MIN — do not wait for a 24h TTL. Optional later (NOT this grind): trimmed mean / variance gauges.

C. Gold labels (positive):
   1. Deposit into a named storage topic → expected_lane is gold (not inbox/packs/General).
   2. Operator approve with one or more lane_keys → those lanes are gold.
Negative labels: operator reject (do not add embedding to any lane centroid; optional "reject" bucket unused for routing).
Never label age-adjacent / zoo hard_block items into the prototype bank.

D. Mixed-bulk target = AOF INBOX (and the inbox shortcut channel). Per-item classify; do not treat a Telegram album as one category. Album members may go to different lanes. If every item in an album maps to the same lane, they naturally stay together — do NOT add intra-album k-means / clustering.

E. Auto-route (trusted hub inbox origin ONLY — never scrape):
   - Score used for the threshold is the **same number** whether the source is CLIP, prototype, caption, or blended. Caption-only must not look like un-scored guesswork.
   - Caption confidence (no spaCy, no TF-IDF): exact hashtag/token in LANE_TAG_MAP → 1.0; fragment/contains match → 0.55; no match → 0.0. Store as enrich.caption_confidence. A 1.0 caption hit may auto-route if margin also clears (second proposed lane must be 0.0 or far below).
   - If top lane score ≥ TBCC_GATEKEEPER_AUTO_SPLIT_MIN (default 0.28) AND margin ≥ TBCC_GATEKEEPER_AUTO_SPLIT_MARGIN (default 0.04) AND no hard_block → enqueue_lane_route_for_media + approve (same path as operator approve).
   - If two+ lanes both ≥ AUTO_SPLIT_MIN and margin is small → do NOT auto-route; quarantine with BOTH lanes pre-selected on the picker. (This already covers the “three lanes all ≈0.27” case. Do NOT add softmax/entropy.)
   - Agreement boost (Phase 3+): if CLIP-mapped top lane == prototype top lane, multiply the blended score by 1.15 (cap 1.0). If they disagree on top lane → treat as small-margin: quarantine with both pre-selected. Do not invent product-of-experts libraries.
   - If low confidence → quarantine with best-guess lane(s) pre-selected (set_picked_lanes).
   - Named-topic deposits keep today's behavior (expected_lane from topic); CLIP mismatch still quarantines (existing glob). Optionally still record a gold label for the topic lane.

F. CLIP slug → lane: a frozen mapper CLIP_SLUG_TO_LANE plus LANE_TAG_MAP fragment match on slug/name. Direct slug==network_key wins. Example fragments: blowjobs→blowjob, just-boobs/tittydrop/busty-*→big_tits, thick-booty/ass-clap/pawg/cute-butts→ass, horny-cougars/milf→milf, upskirt/voyeur/public→voyeur, hanime/rule-34/deepfake→ai, pinay/filipina/malay/thai/korean-nsfw/busty-asians→abg. Keep the map in code + tests; do not scrape live Telegram to invent mappings.

G. Bytes for CLIP: photos and video thumbs only. Do not download full video files on the island for classification. If no thumb bytes, fall back to caption/filename only.

H. Sidecar /embed: add POST /embed on clip_categorize_app returning {ok, dim, embedding: float[]} (same encode_image path as classify, no catalog required). clip_classifier.py gets embed_image_bytes(). If sidecar down, skip prototypes, still use caption mapper.

I. Island / home: do not spawn payment/loot/API bots. Do not commit .env. Do not push. Do not run deploy-island-live.ps1. CLIP sidecar is optional and typically Windows-home; island may lack torch — degrade gracefully.

Out of scope
------------
- New AOF public channels or hub topics
- Fine-tuning CLIP / NSFW_Detection_API / any GPU training job
- Vision LLM as age/zoo/illegal judge (existing hard_block metadata only)
- Changing SCORE_APPROVE_MIN / scrape-never-auto-approve / source demote
- Extension, loot economy, secretary, Zeus
- Real NSFW fixtures in git (synthetic captions + fake embeddings only)
- CSAM / underage samples in tests or docs (keep AGE_ADJACENT_PATTERNS; never add media)
- Tray bot Start, .env, *.session*, push, island deploy
- REJECTED (do not implement even if a review suggests them): intra-album k-means; spaCy/TF-IDF caption classifier; softmax/entropy auto-route; float16/base64 embedding quantization; Prometheus counters or GET /gatekeeper/health; operator gold-label rate-limits / per-lane trust scores; lane_parents.json / sub-lanes (big_tits/asian); trimmed-mean + variance auto-recalibrate. Single-operator hub; those are future polish after split actually ships.

Constraints & gotchas
---------------------
- merge_gatekeeper_json only — never wipe classification_json
- One Telethon admin.session at a time — lane route already uses run_telegram_io; do not open a second client
- TBCC_BOT_RUNTIME_ADAPTER / 409: never start bots
- Windows PowerShell: no && chaining if you shell; use working_directory
- Alembic: 114_gatekeeper_lane_labels.py, down_revision = 113_secretary_draft_candidates
- Store embeddings as JSON float lists (512-d). Do not quantize. Thousands of labels is fine at this scale.
- Pre-select lanes via existing set_picked_lanes / Redis — do not invent a new callback namespace
- Update docs/MEDIA_GATEKEEPER.md with a P5 section in Phase 4 only
- Add a TEST_MAP.md row in Phase 4

Verification (run from tbcc/backend)
------------------------------------
Phase 1:
  py -3.13 -m pytest tests/test_aof_lane_tag_map.py tests/test_media_gatekeeper_spec.py tests/test_gatekeeper_clip_lane_map.py -x -q --tb=short

Phase 2:
  py -3.13 -m pytest tests/test_media_gatekeeper_service.py tests/test_gatekeeper_inbox_split.py tests/test_gatekeeper_lane_picker.py tests/test_gatekeeper_review.py -x -q --tb=short

Phase 3:
  py -3.13 -m pytest tests/test_gatekeeper_prototypes.py tests/test_gatekeeper_review.py -x -q --tb=short

Phase 4:
  py -3.13 -m pytest tests/test_media_gatekeeper_spec.py tests/test_media_gatekeeper_service.py tests/test_gatekeeper_clip_lane_map.py tests/test_gatekeeper_inbox_split.py tests/test_gatekeeper_prototypes.py tests/test_aof_lane_tag_map.py -x -q --tb=short

Working agreement
-----------------
- Commit once per phase (session scope only). Message: feat/fix prefix, why not what.
- Never stage: .env, *.session*, .tbcc-run/, __pycache__, credentials.
- After EACH phase: write the reverse report (structure below), then STOP. Do not start the next phase until Cursor ACKs.
- Reverse report path:
  Phase 1 → tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train_report.md
  Phase 2 → tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train_p2_report.md
  Phase 3 → tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train_p3_report.md
  Phase 4 → tbcc/docs/handoffs/2026-08-17_gatekeeper-lane-split-train_p4_report.md

Reverse report structure (markdown only):
# Reverse handoff — gatekeeper-lane-split-train
- Branch:
- Head commit(s) this phase (hash + subject):
- Status: Phase N complete | blocked | needs Cursor review
## Done
## Files touched
## Verification run
## Risks / open questions
## Operator smoke (Tray only)
## Do not
- push / start bots / touch .env / Phase N+1 until Cursor ACK

Phases
------
Phase 1 — CLIP/caption → AOF lane mapper (pure, no Telegram)
* Add tbcc/backend/app/data/clip_slug_lane_map.py:
  - CLIP_SLUG_TO_LANE: dict[str, tuple[str, ...]] covering high-volume slugs in tbcc/data/clip-categories.json that clearly map to the 11 split lanes. Sample the catalog; do not map every 1400 slugs — map the obvious ones + fragment fallback via LANE_TAG_MAP.
  - def map_clip_slugs_to_lanes(slugs: list[str], *, scores: dict[str, float] | None = None) -> list[tuple[str, float]]
  - def map_text_to_lanes(caption: str, filename: str = "") -> list[str]  (wrap detect_lane_from_text / suggest_lane_keys_from_tags; return all plausible, not just top-1)
  - def caption_confidence(caption: str, filename: str = "") -> float  (1.0 exact tag, 0.55 fragment, 0.0 none — locked rule E)
* Extend glob_lane_fit extras: proposed_lanes: list[str] (ranked). When expected_lane in {None, inbox}, lane_fit.pass_ stays True for inbox unknown (do not reject mixed dumps) BUT extras.proposed_lanes is populated from caption + mapped CLIP. Caption still wins over CLIP when both present and they disagree → proposed_lanes includes both, flag lane_ambiguous.
* When expected_lane is a real content lane and mapped CLIP/caption disagrees → keep today's quarantine mismatch behavior.
* Tests: tests/test_gatekeeper_clip_lane_map.py — blowjobs→blowjob, just-boobs→big_tits, thick-booty→ass, milf caption→milf + caption_confidence 1.0, untagged caption confidence 0.0, inbox expected + ass hashtag → proposed ass, no real images.
* Verify Phase 1 command. Commit. Write Phase 1 reverse report. STOP.

Phase 2 — Inbox mixed split + preselect + auto-route
* NEW Phase 1 ACK constraints (do not skip):
  - Hook inbox-origin after gatekeeper **regardless of verdict** (approve AND quarantine). Untagged trusted hub inbox already auto-approves at quality ~75; if you only split quarantine, mixed dumps skip the feature.
  - Pass CLIP label scores into map_clip_slugs_to_lanes(..., scores={slug: score}). Never call it with a bare slug list for auto-route decisions.
  - Consume proposed_lanes / mapper output, not MediaGatekeeperInput.clip_slug as a network_key.
  - caption_confidence already exists in clip_slug_lane_map.py — import it; do not reimplement.
* New service tbcc/backend/app/services/gatekeeper_inbox_split.py:
  - resolve_proposed_lanes(media, enrich, caption) → ranked lanes + scores + source (caption|clip|prototype|mixed)
  - maybe_auto_split_inbox(db, media_id, ...) implements locked rule E. Uses enqueue_lane_route_for_media / operator_approve_media internals — do not duplicate Telethon. Prefer calling existing functions.
  - For quarantine: set_picked_lanes(media_id, proposed[:2]) so the review card already shows selected emojis.
* Wire CLIP enrich into ingest for inbox (and only then for split):
  - apply_gatekeeper_after_ingest should accept/merge enrich.clip_slug, clip_confident, clip_labels (list).
  - After metadata gatekeeper, if origin is storage_hub AND expected_lane is inbox, call a lightweight classify if clip_classifier_enabled() and photo/thumb bytes are already in hand. Do NOT block ingest if CLIP is down. Do NOT download full videos.
  - If bytes are not in hand at ingest, enqueue a Celery task on telegram queue (new gatekeeper_split_worker or extend gatekeeper_review_worker) that classifies then maybe_auto_split_inbox. Keep it off the payment/loot processes.
* Auto-split env:
  TBCC_GATEKEEPER_INBOX_SPLIT=1 (default on)
  TBCC_GATEKEEPER_AUTO_SPLIT_MIN=0.28
  TBCC_GATEKEEPER_AUTO_SPLIT_MARGIN=0.04
* Tests: tests/test_gatekeeper_inbox_split.py with mocked CLIP + mocked enqueue_lane_route. Cases: confident single lane auto-routes; two strong lanes quarantine with both preselected; CLIP down + "#milf" caption still proposes milf AND caption_confidence==1.0 may auto-route; CLIP down + untagged caption does not auto-route; **already-approved untagged inbox still enters maybe_auto_split_inbox** (must not return early on verdict==approve); scrape origin never auto-splits; age_adjacent never auto-routes; video with no thumb bytes takes caption-only branch (no download).
* Verify Phase 2 command. Commit. Write p2 reverse report. STOP.

Phase 3 — Online prototype bank
* Alembic 114_gatekeeper_lane_labels:
  table gatekeeper_lane_labels:
    id, media_id (nullable int), file_unique_id (str, indexed),
    lanes_json (text, JSON list of network_keys),
    source (str: hub_topic | operator_approve | operator_reject),
    embedding_json (text, nullable JSON float list),
    dim (int, nullable),
    created_at
  No unique on media_id (operator can relabel). Index file_unique_id + created_at.
* Service tbcc/backend/app/services/gatekeeper_prototypes.py:
  - record_label(...); skip if hard_block age/zoo (never persist those rows)
  - keep per-lane running sum_vector + count (in Redis JSON alongside centroids, or derived: on read, if cache miss, ONE scan to rebuild sums then cache). Incremental update on each embedding label: sum += vec; count += 1; centroid = sum/count.
  - load_centroids() / score_embedding(vec) → list[tuple[lane, cosine]] (pure python + math; numpy ok if already a backend dep — do not add a new dependency for this)
  - redis.delete("tbcc:gk:centroids") (and the sums key) immediately after a record_label that writes an embedding. TTL 24h is a safety net only, not the invalidation strategy.
  - maybe_recalc() is only the cache-miss full scan, not a periodic job.
* Hook record_label:
  - media_gatekeeper apply / storage ingest when expected_lane is a split target
  - operator_approve_media (positive)
  - operator reject path (source=operator_reject, lanes_json=[])
* CLIP /embed:
  - services/clip_categorize_app.py POST /embed (upload file) and optional /embed-path
  - clip_classifier.embed_image_bytes()
  Record embedding when sidecar up; labels without embedding still count as caption-side truth but do not move centroids.
* Inbox split (Phase 2) should blend prototype scores with CLIP-mapped scores when centroids exist (max of the two, then apply agreement boost from rule E). Prototype vote never overrides hard_block. Prototype-only auto-route only if that lane has ≥ PROTOTYPE_MIN labels AND cosine ≥ AUTO_SPLIT_MIN.
* Tests: tests/test_gatekeeper_prototypes.py with synthetic 8-d vectors (do not call torch). Cases: approve hook writes a row; age-adjacent caption+embed is NOT stored; running sum/count matches centroid; second label invalidates Redis (mock); CLIP vs prototype disagree → no auto-route in the split helper.
* Verify Phase 3 command. Commit. Write p3 reverse report. STOP.

Phase 4 — Docs, TEST_MAP, optional AOF-lane CLIP catalog helper
* docs/MEDIA_GATEKEEPER.md: add P5 "Inbox mixed split + prototype bank". Document env vars. Status table: P5 done. Keep red lines.
* tbcc/docs/TEST_MAP.md: add row **Gatekeeper lane split** → the pytest files above.
* Optional helper (code + test only, do not overwrite tbcc/data/clip-categories.json):
  tbcc/backend/scripts/export_aof_lane_clip_catalog.py writes a SMALL catalog (one/few prompts per split lane) to stdout or tbcc/data/clip-categories-aof-lanes.example.json. Operator can point TBCC_CLIP_CATEGORIES_FILE at it later. Default remains the big catalog + mapper.
* If review-card text can cheaply show "proposed: 🍑 ass 0.41 / 🍒 big_tits 0.22", add one line to the existing quarantine card formatter — do not redesign the panel.
* Verify Phase 4 command. Commit. Write p4 reverse report. STOP. Do not deploy.

If blocked
----------
Stop and write the reverse report with Status: blocked and the exact missing piece. Do not invent taxonomy, do not start Phase N+1, do not lower AUTO_SPLIT to force volume.
```
