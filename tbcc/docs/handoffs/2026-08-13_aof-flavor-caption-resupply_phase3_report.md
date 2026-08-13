# Phase 3 report — AOF flavor caption resupply (Buffer X + resync script)

**Date:** 2026-08-13
**Scope:** `tbcc/backend/scripts/generate_buffer_x_copy_catalog.py`,
`tbcc/backend/app/data/buffer_x_copy/*.json`, `tbcc/docs/samples/buffer_x_copy/*.json`,
`tbcc/backend/scripts/resync_flavor_captions.py` (new),
`tbcc/backend/tests/test_buffer_x_copy_diversity.py` (new)
**Status:** done, tests green (40 passed, 0 failures), STOP for Cursor ACK — operator runs
`--execute` on the island after ACK, per the working agreement (no SSH/deploy performed
here)

## 1. Buffer X hook stem expansion

**Root cause confirmed:** `generate_buffer_x_copy_catalog.py`'s `HOOKS` list had 20
entries. `_build()` took the full `product(HOOKS, MID, closers)` (20 × 10 × 5-7), shuffled
it, and deduped on the **full body string** down to 100. Since only 20 distinct openers
exist, a 100-body category averaged ~5 repeats of every hook — the "many share same short
stems" symptom, confirmed by inspecting the pre-change JSON.

**Fix, two parts:**
1. **Expanded `HOOKS` from 20 → 90** distinct stems, in the same gold delivery/pipeline/
   curated-dump/no-apology voice as the Telegram lane hooks (Phase 2) and PACKS hooks,
   translated to Buffer X's plain-text style (lowercase, short, no emoji/HTML — per the
   voice rule "plain text + {hub} placeholders for Buffer X").
2. **Rewrote `_build()` to round-robin across hooks** instead of shuffle-and-dedup. Each
   hook's `product(MID, closers)` combos are shuffled independently, the 90 per-hook
   groups are interleaved via `itertools.zip_longest`, then the first 100 unique bodies
   are taken. This **guarantees** (not just makes likely) that the first `len(HOOKS)`
   bodies each open with a distinct hook — diversity is structural, not a shuffle-luck
   outcome.

**One real bug found while measuring, not assumed away:** first regeneration run reported
89/90 diversity, not 90/90, in every category. Traced it to a genuine prefix collision —
a newly-added hook ("you weren't invited. you stayed.") shares its first sentence with the
pre-existing hook ("you weren't invited."), so a naive "text up to the first period"
diversity metric conflated the two. Reworded the new hook to "not on the list. showed up
anyway." — no other collisions exist (checked all 90 hooks pairwise). Regenerated: **90/90
unique first-sentence hooks in every one of the 5 categories**, comfortably past the ≥60
target.

```
wrote lootgod.json: 100 templates, 90 unique first-sentence hooks -> .../docs/samples/buffer_x_copy + .../backend/app/data/buffer_x_copy
wrote spicy.json: 100 templates, 90 unique first-sentence hooks -> ...
wrote paired_dual_cta.json: 100 templates, 90 unique first-sentence hooks -> ...
wrote network.json: 100 templates, 90 unique first-sentence hooks -> ...
wrote affiliate.json: 100 templates, 90 unique first-sentence hooks -> ...
```

### Second fix, incidental but real: the generator now writes both locations
Discovered while tracing where the live-loaded catalog actually lives:
`generate_buffer_x_copy_catalog.py` only ever wrote to `tbcc/docs/samples/buffer_x_copy/`,
but `seed_social_copy_templates.py`'s `DEFAULT_DIR` (the path it actually loads from) is
`tbcc/backend/app/data/buffer_x_copy/` — a second, previously-manually-synced copy (byte
identical to `docs/samples` before this change, confirmed via diff). Nothing enforced
those two directories staying in sync; a future regeneration that only ran the generator
and forgot the manual copy step would silently seed stale content. Fixed by having the
generator write both paths in one run. `test_runtime_and_fallback_catalogs_match` in the
new test file now guards this invariant going forward.

### Tests: `tests/test_buffer_x_copy_diversity.py` (new, 5 tests)
Loads the **committed JSON**, not a live-generated sample — catches drift if someone
regenerates without the round-robin fix or hand-edits a file badly:
- Runtime catalogs exist
- Each category's first-sentence diversity ≥ 60 (measured: 90 for all 5)
- No duplicate bodies within a category
- Runtime dir (`backend/app/data/buffer_x_copy`) matches fallback dir (`docs/samples/buffer_x_copy`) byte-for-byte
- Every template has a non-empty `body`, `surface == "x_buffer"`, and a `category`

## 2. Seed command — documented AND verified, not assumed

`seed_social_copy_templates.py` already existed (`DEFAULT_DIR` = `backend/app/data/buffer_x_copy`,
falls back to `docs/samples/buffer_x_copy`). Its `exists` check matches on exact `body`
text. Since every Buffer X body changed in §1, running the plain default command would
**add** ~100 new rows per category **on top of** the ~100 old low-diversity rows — the old
rows never get removed by a body-text match that no longer matches anything, and
`social_copy_rotation.mark_template_used` only demotes (pushes to back of the rotation
queue), never deletes. That would leave the old repetitive stems permanently stuck in
rotation, silently defeating this entire phase.

**Verified this concern for real** rather than leaving it as a worked-out-on-paper risk:
built a throwaway SQLite harness (stubbed `load_tbcc_dotenv()` so it wouldn't overwrite
`DATABASE_URL` back to the real Postgres URL from `tbcc/.env`), seeded 5 fake stale
`lootgod` rows, ran the actual `seed_social_copy_templates.main()` with
`--execute --replace-category` against the real regenerated `backend/app/data/buffer_x_copy`
directory, and confirmed: category ends at exactly 100 rows (not 105, not 200), and **zero**
of the 5 stale bodies survived.

```
before_count=5
after_count=100
stale_survivors=0
ALL --replace-category ASSERTIONS PASSED
```

Note for the operator: `--import-dir` (or the default) points at the whole
`buffer_x_copy/` directory, so a real run reseeds **all five categories**, not just
`lootgod`. The harness's own seeder report showed `"imported": 500` total (100 per
category × 5) — expect that number on the island run, not 100.

**Documented command for the operator (verified, not just inferred from reading the code):**
```
cd tbcc/backend
py -3.13 scripts/seed_social_copy_templates.py --execute --replace-category
```
Dry-run first if preferred (omit `--execute`; the script queries `exists` and prints a
report without writing — rolls back its own transaction): `py -3.13 scripts/seed_social_copy_templates.py`.
**Do not run without `--replace-category`** after this phase's regeneration — see above.

## 3. `backend/scripts/resync_flavor_captions.py` (new)

`--dry-run` / `--execute` script wrapping the two refresh paths documented in the Phase 2
report:
- **Lane schedulers:** `sync_network_schedulers(db, execute=...)` — already returns
  `variations_before_dedupe` / `variations` / `unique_hooks` per lane (added in Phase 1),
  computed even when `execute=False` (read-only query path, confirmed by code review of
  `aof_growth_hub.py`), so dry-run reports real numbers without writing.
- **PACKS scheduler:** `refresh_aof_packs_scheduler(db)` has no dry-run mode of its own
  (unconditional `db.commit()`), so the script's dry-run path never calls it — instead it
  compares `len(pack_caption_template_variations())` (101) against the live scheduler's
  current `content_variations` count via a read-only query, and only calls the real
  refresh function under `--execute`.

Note on the `--dry-run` flag: it's accepted for parity with the brief's literal
verification command, but read-only is already the default behavior with or without it —
only `--execute` changes behavior. `--dry-run --execute` together execute (the flag
doesn't override `--execute`; documented in the script's own `--help`).

### Verification, stated precisely (what ran vs. what didn't)

The brief's literal command failed to connect, as expected in this sandbox:
```
py -3.13 scripts/resync_flavor_captions.py --dry-run
...
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at
"localhost" ... Connection refused
```
No local Postgres is available in this environment — the island's real Postgres instance
is the only place this command has ever actually connected. This is the correct failure
mode (a connection error, not a code exception), not a bug being hidden.

**What was actually verified:** the script's core logic (`_lane_report`, `_packs_report`)
was exercised directly against a real seeded SQLite database (bypassing only the
`load_tbcc_dotenv()` + `SessionLocal`-binding boilerplate at the top of `main()` — copied
unmodified from the pre-existing `seed_social_copy_templates.py` pattern, ~4 lines, not
independently re-verified). Seeded all 13 real lane channels/pools/schedulers, one with
20 fake padded rows sharing a single hook behind different sponsor URLs (the exact island
bug shape), plus a PACKS scheduler with 50 old-style templates:

```
main           before_dedupe=111  after=92   unique_hooks=92
ai             before_dedupe=111  after=92   unique_hooks=92
... (all 13 lanes) ...

PACKS: {'scheduler_found': True, 'bank_size': 101, 'live_before': 50, 'would_change': True}
```

Stated carefully: **this proves the mechanism collapses padding and reports accurate
counts** — it does not predict the island's actual numbers, which depend on the island's
real stale-row shapes and real affiliate candidate list (different from this synthetic
seed). The first real run of this exact CLI command, dotenv-loading included, will be the
operator's island run.

## Verification run (exact commands from the brief)
```
cd tbcc/backend && py -3.13 -m pytest tests/test_aof_flavor_hooks.py -q --tb=short
24 passed in 0.87s

py -3.13 scripts/resync_flavor_captions.py --dry-run
[fails: no local Postgres in this environment — see §3]
```
Broader regression check (not in the brief's literal list, run anyway):
```
py -3.13 -m pytest tests/test_aof_flavor_hooks.py tests/test_buffer_x_copy_diversity.py tests/test_aof_packs_send_time.py tests/test_aof_growth_hub.py tests/test_social_copy_rotation.py -q --tb=short
40 passed, 1 warning (pre-existing unrelated SQLAlchemy deprecation notice) in 0.83s
```

## DONE WHEN — status against the brief's checklist
- PACKS template set ≥100 unique hooks including gold-style delivery lines — **done**, Phase 2 (101).
- Network sync no longer creates 100+ slots of the same VIP opening — **done**, Phase 1/2.
- Each lane designed for ≥50 unique flavor hooks after sync — **done**. Phase 2 measured
  90 via a test-only reimplementation of the merge sequence; this phase's SQLite smoke
  test called the **real** `sync_network_schedulers` (not a reimplementation) with 20
  realistic padded rows seeded and measured 92 — strictly better evidence, superseding
  the Phase 2 number.
- Buffer X catalogs have visibly more distinct openings — **done**, this phase (20 → 90 unique first-sentence hooks per category, structurally guaranteed).
- Tests green; reverse reports written per phase — **done**, all three phases.

## Not done / explicitly out of this effort
- Island resync itself — awaiting operator action per the working agreement.
- Goblin-teaser exposure ratio (flagged in Phase 2, not addressed).
- `MID` / closer template expansion — only `HOOKS` were expanded per the brief's specific
  diagnosis ("many share same short stems" pointed at hooks, not mid/closer text).

## STOP
Awaiting Cursor `/cc-report` ACK. Per the working agreement, the operator runs
`py -3.13 scripts/seed_social_copy_templates.py --execute --replace-category` and
`py -3.13 scripts/resync_flavor_captions.py --execute` on the island — not done here.
