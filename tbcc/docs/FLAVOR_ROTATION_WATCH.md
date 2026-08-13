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

## 48h watch checklist

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
