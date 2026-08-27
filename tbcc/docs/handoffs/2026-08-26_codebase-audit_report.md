# Codebase audit report — 2026-08-26

**Preset:** `codebase-audit` (sprint “first audit run”)  
**Crew:** readonly · ≤3 makers + coordinator  
**Blast fence:** shared Cursor/CC tool graph + handoffs bus; **no** money/Telegram mutate; **no** Start bots; Mega→R2 = idle not bloat  
**Do-not-touch honored:** secrets/.env · Start bots · Supervisor deep rewrite

---

## Ledger B — Reconnect (cap 10) — rank first

| # | path A | path B | missing link | evidence | proposed wire | unblocks |
|---|--------|--------|--------------|----------|---------------|----------|
| 1 | `app/services/silent_fail_probes.py` | `ops_picture_report.py` | Class-2 verdicts never enter ops-picture blockers | `rg silent_fail ops_picture_report.py` → 0 | Call intake+R2 probes in `derive_blockers` / report build | `/ops-picture` shows zombie without skill hop |
| 2 | `scripts/silent_fail_probe.py` | `tbcc_cli.py` + operator registry | Probe CLI not a hub subcommand | `tbcc_cli` parsers: no `silent-fail` | `tbcc_cli silent-fail …` + registry | `operator silent-fail all` from any cwd |
| 3 | `docs/SILENT_FAIL_REGISTRY.example.json` | `silent_fail_probes.py` | Design registry never loaded | File: DESIGN ONLY; no Python loader | Load watches or promote + drive `all` | Expand watches without code forks |
| 4 | Beat `enrich-backlog-sweep` | `silent_fail_probes.py` | Beat backstop has no last_success probe | Beat registered; no `probe_enrich_*` | Redis stamp + `probe_enrich_backlog` (`*_ENABLED=0` → idle) | Catch silent enrich starvation |
| 5 | `scripts/signal_scout_fanout.py` | `tbcc_cli.py` | Docs/skill claim live; hub silent | `rg signal_scout tbcc_cli.py` → 0 | `tbcc_cli signal-scout draft\|execute` | Discoverable paste fanout |
| 6 | `tbcc-sitrep` skill | `silent_fail_probes.py` | Sitrep never pulls class-2 stops | sitrep skill: no silent_fail | Embed probe/`all` in sitrep | ACK surfaces stale/never_seen |
| 7 | `data/signal_paste_destinations.json` | `scripts/signal_scout_fanout.py` | Notes claim wrong script name | notes: `signal_paste_fanout.py`; CLI is `signal_scout_fanout.py` | Fix note (service name stays) | Agents stop hunting missing script |
| 8 | `scripts/ops_picture_snapshot.py` | `tbcc_cli.py` | Protocols list script; hub no wrap | `rg ops_picture tbcc_cli` → 0 | `tbcc_cli ops picture` | One CLI path for snapshot |
| 9 | `scripts/ship_log_buffer.py` | `tbcc_cli.py` | Compose chain skill-only | not in tbcc_cli parsers | `tbcc_cli ship-log idea\|queue` | Diary → Buffer without path memory |
| 10 | `scheduling_fast_snapshot` | `verdict_from_last_success` | Health = process-up only | 2026-08-24 inventory; no silent-fail import | Fold probe verdicts into scheduling section | “Beat up, work never ran” visible |

**Already wired (not reconnect):** `enrich_backlog`, `storage_hub_op_status`, `telegram_queue_ops`, `openrouter_spend`.

---

## Ledger A — Bloat (cap 20)

| # | path | why | evidence | action | risk |
|---|------|-----|----------|--------|------|
| 1 | `scripts/_probe_telegram_queue.py` | orphan Redis dump | `rg -l _probe_telegram_queue` external 0 | delete | low |
| 2 | `scripts/_probe_inbox_drop.py` | orphan scratch | `rg -l` external 0 | delete | low |
| 3 | `scripts/_probe_clip_route.py` | duplicate CLIP; docstring “safe to delete” | self-only refs | delete | low |
| 4 | `scripts/_probe_clip_vs_vision.py` | duplicate CLIP family | external 0 | archive | low |
| 5 | `scripts/_probe_explain.py` | orphan explain probe | external 0 | archive | low |
| 6 | `scripts/_parse_pc_html2.py` | hard-coded local HTML one-off | external 0 | delete | low |
| 7 | `scripts/_parse_pc_html_lists.py` | sibling one-off | external 0 | delete | low |
| 8 | `scripts/_island_audit_lane_readiness.py` | dup of `audit_lane_readiness.py` | underscore variant external 0 | delete | low |
| 9 | `scripts/_island_count_pending_lv.py` | island one-shot | external 0 | delete | low |
| 10 | `scripts/_island_smoke_flywheel_fomo.py` | island smoke | external 0 | delete | low |
| 11 | `scripts/_island_stop_duplicate_posts.py` | mutator one-shot, no importer | external 0 | archive | med |
| 12 | `scripts/_test_album_session.py` | orphan `_test_*` outside tests/ | external 0 | delete | low |
| 13 | `scripts/_kill_companion_stack.ps1` | orphan kill script | external 0 | archive | med |
| 14 | `scripts/run_openclaw_ops_tick.py` | deprecated alias | docstring + external 0 | delete | low |
| 15 | `scripts/wk30_hub_teaser_once.py` | spent campaign | external 0 | archive | low |
| 16 | `scripts/buffer_ig_carousel_test.py` | zero-importer smoke | external 0 | delete | low |
| 17 | `scripts/discord_webhook_test.py` | zero-importer smoke | external 0 | delete | low |
| 18 | `scripts/probe_linkvertise_*.py` + `probe_lv_posts_table.py` | LV probe cluster | each stem external 0 | archive | low |
| 19 | `extension/reverse-aggregator.{html,js}` | not in MV3 manifest | `Select-String reverse-aggregator manifest` → 0 | archive | low |
| 20 | `TEST_MAP.md` ThisVid row | cites missing scripts | `Test-Path` test_thisvid_upload_policy.py + thisvid_upload_local.py → **False** | trim map / archive row | med |

**Idle (not bloat):** Mega→R2 paused; governor `*_ENABLED=0`; live CLI `silent_fail_probe.py` / `operator_tui.py` / `signal_scout_fanout.py`.

---

## Entropy vertices (innovation lens, ≤5, reconnect yield)

| # | axis | finding | status | one-liner |
|---|------|---------|--------|-----------|
| 1 | agent-workflow / trust | silent-fail probes exist but never surface in ops-picture/sitrep | **missed** | Wire B1+B6 → always-on rule gets a UI stop |
| 2 | unexploited primitives | `tbcc_cli` hub missing silent-fail / signal-scout / ship-log / ops-picture | **missed** | B2+B5+B8+B9 = one slice “hub discoverability” |
| 3 | integration surfaces | `SILENT_FAIL_REGISTRY.example.json` still design-only | **missed** | B3 closes Phase-1→2 named in 2026-08-24 report |
| 4 | leverage left on table | enrich-backlog Beat wired, no class-2 stamp | **missed** | B4 — classic silent-abandon shape |
| 5 | capability gaps | `_probe_*` cluster + wrong paste dest note | **covered** (scouted) | Docs fix B7 is free; deletes need operator pick from A |

---

## Coordinator verdict

- **Refuse mass-delete.** Ledger B ranked above A. Operator picks **1–3** from B (prefer 1→2→4 or hub batch 2+5+8+9), then optional low-risk A deletes.
- **Contradictions resolved:** new services enrich/storage_hub/telegram_queue/openrouter are **wired** — not orphans. Half-wired = silent_fail + signal_paste only.
- **No implement in this crew.** Report only.

**Counts:** Ledger A = 20 · Ledger B = 10 · Entropy missed = 4 / covered = 1

---

## Silent-fail stops (per-row evidence — external)

| watch | claim | stop | verdict |
|-------|-------|------|---------|
| `audit-bloat-probes` | unused `_probe_telegram_queue` / `_probe_inbox_drop` | `rg -l -F _probe_telegram_queue` / `_probe_inbox_drop` → no repo callers beyond self | ok (unused claim holds) |
| `audit-reconnect-ops` | silent_fail absent from ops-picture | `rg silent_fail tbcc/backend/app/services/ops_picture_report.py` → 0 | ok (gap holds) |
| `audit-cli-hub` | no silent-fail/signal-scout in tbcc_cli | parsers list has post/campaign/…/operator — no those names | ok (gap holds) |
| `audit-thisvid-map` | TEST_MAP cites missing files | `Test-Path` both → False | ok (orphan map holds) |
| `audit-ext-revagg` | reverse-aggregator unwired | manifest match count 0; files exist | ok (dead path holds) |
| `audit-paste-note` | wrong script in destinations notes | notes say `signal_paste_fanout.py`; CLI is `signal_scout_fanout.py` | ok (doc gap holds) |

**Forbidden:** auto-delete · Start bots · treating Mega→R2 as bloat.

---

## Next

Operator pick **1–3** from Ledger B → `/preflight` or `/directive`.  
Compose: **/silent-fail** (queued below) → then implement slice.
