# Lane readiness audit — island snapshot

**When:** 2026-07-17  
**Source:** `content_pools` × `media` (status=`approved`) on revenue island  
**Thresholds:** subtopic min 2,500 img + 2,500 vid; median target 5,000 each; aspire 10,000

| Lane (pool) | Images | Videos | Ready subtopic? | At median? | Gap to median (img+vid) |
|-------------|-------:|-------:|:---------------:|:----------:|------------------------:|
| AOF ASS | 155 | 487 | no | no | 9858 |
| AOF PUBLIC / VOYEUR | 41 | 425 | no | no | 10034 |
| ABG / LBFM | 214 | 199 | no | no | 9587 |
| AOF TABOO | 0 | 370 | no | no | 12130 |
| AOF BLOWJOB | 0 | 354 | no | no | 12146 |
| AOF BIG TITS | 0 | 349 | no | no | 12151 |
| AOF MILF | 0 | 279 | no | no | 12221 |
| AOF BOP | 62 | 207 | no | no | 9731 |
| AOF AI | 210 | 40 | no | no | 9750 |
| AOF GOON | 24 | 225 | no | no | 9751 |
| AOF FULL LENGTH | 0 | 0 | no | no | 10000 |

**Verdict:** **Zero lanes** meet the 2,500/2,500 subtopic floor. Deepest lane (ASS) is ~642 approved total. Network-wide approved inventory ≈ **886 photos + 3,340 videos**.

**Scrape priority (toward 5k median):**
1. Photo-starved video lanes: TABOO, BLOWJOB, BIG TITS, MILF (0 approved photos)
2. Thin video lanes: AI (40 videos), ABG (199)
3. Overall depth: every lane needs ~4–5k more of each format — scrapers should bias **photos into video-heavy lanes** and **videos into AI/ABG**

**Operator note:** Loot Room floor pools hold only ~40 items each (shared-library band). Channel pools above are the readiness source of truth for subtopic gates.

Re-run: `py -3.13 scripts/audit_lane_readiness.py` (after GHCR bake) or island SQL in this doc’s companion script.
