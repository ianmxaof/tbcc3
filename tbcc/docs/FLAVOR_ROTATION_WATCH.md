# Flavor rotation watch (baseline 2026-08-13)

Post-resync baseline after `024b594` + island execute (`local-20260813-0415`).

## Scheduler banks (live after resync)

| Lane | unique_hooks |
|------|--------------|
| main | 99 |
| ai | 148 |
| blowjob–bop | 93–97 |
| inbox | 91 |
| full_length | 105 |
| **PACKS** | **101** |

Buffer X DB: **500** templates (`seed_social_copy_templates --execute --replace-category`).

## 7-day send volume (pre-resync era)

~1,272 outbound events / 7d (`scheduled_post_sent` + `pool_album_posted`). Top lanes: Loot Room 226, ABG 132, Goon 127, AI 113.

## 48h watch snapshot (2026-08-13 ~06:30 PT)

| Metric | Value |
|--------|-------|
| Outbound (2d) | **355** sends (349 ok, 6 failed) |
| Aug 11 | 77 |
| Aug 12 | 185 |
| Aug 13 (partial) | 93 |
| Top lanes | Loot Room 65, ABG 38, Goon 36, AI 30 |
| PACKS (14) | 9 sends in window — watch Planet Express motif |
| Checkout List (21) | 1 send — bulletin refreshed island deploy |

## Sitrep pulse (2026-08-13 ~09:10 PT)

| Metric | Value |
|--------|-------|
| Outbound (MCP days=2 rollup) | **354** (348 ok, 6 failed) |
| By day | Aug 11: 56 · Aug 12: 185 · Aug 13: 113 |
| Top lanes | Loot Room 65, ABG 38, Goon 36, AI 30 |
| PACKS | 9 · Checkout List 1 |
| Flavor dry-run unique_hooks | main 103 · ai 152 · lanes 95–109 · **PACKS 101** (no change) |
| Buffer X sample | **skipped** — Buffer API 429 (Retry-After ~2.6h) |

Status: **watch active** — hook banks healthy; no resync. Re-check Buffer openers after rate-limit clears.


1. **Network lane** — 2–3 posts: opening hook text changes; footer block (`Join the full AOF stack` …) identical.
2. **PACKS** — confirm Planet Express / NEW DELIVERY motif appears sometimes, not every send.
3. **Buffer X** — queue posts: first sentence diversity (no 5× repeat of same opener in a row).
4. **Goblin** — ~5 teaser slots per ~90-hook lane rotation (`TBCC_GOBLIN_TEASER_EVERY_NTH=10`, 5 body variants).

## Evidence commands

```bash
# Island dry-run (read-only)
docker compose ... exec api python scripts/resync_flavor_captions.py --dry-run

# Post analytics (MCP or API)
GET analytics post events summary, days=2
```

Re-run resync only if hook padding regresses (affiliate footer multiplication).
