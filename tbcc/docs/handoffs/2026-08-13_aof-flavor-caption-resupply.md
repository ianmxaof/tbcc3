# Claude Code handoff — AOF flavor caption resupply + rotation fix

**Date:** 2026-08-13  
**Topic:** `aof-flavor-caption-resupply`  
**Reverse reports:**  
- Phase 1 → `tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase1_report.md`  
- Phase 2 → `tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase2_report.md`  
- Phase 3 → `tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase3_report.md`  

Paste the fenced block in the next section into Claude Code. After each phase: write the report, **stop**, wait for Cursor `/cc-report` ACK.

---

## Paste into Claude Code

```
GOAL
Make AOF Telegram lane + PACKS + Buffer/X posts cycle through many DISTINCT flavor hooks every send — same energy as the gold PACKS sample — while headers/footers/affiliate/links stay untouched. Fix the fake "~400–500 variations" padding so unique hooks actually rotate.

GOLD FLAVOR (match this voice — do NOT change footer below the fold):
💥 NEW DELIVERY 💥
🚀 PLANET EXPRESS 🚀
🟡 Another curated dump cleared the pipeline — no apology.

Then (UNCHANGED — never rewrite these blocks):
🔗 Unlock below ↘️
📦 pack body / size / mega / Linkvertise / AdMaven lines
━…━
📌 Join the full AOF stack
addlist | aofmainhub | support
@aofsubscriptions_bot · /loot · /subscribe · /referral

VOICE RULES
- High-energy, edgy, short, emoji-led openers
- Pipeline / delivery / curated dump / no-apology energy (Planet Express OK as a motif, not every line)
- Porn-first, no corporate bird-speak, no essay
- HTML ok for Telegram (<b>, <i>); plain text + {hub} placeholders for Buffer X
- Never invent new bot usernames; keep @aofsubscriptions_bot / @aof_lootgod_bot / telegram.me/aof_lootgod_bot
- Never change FOOTER_MARKER text "Join the full AOF stack" or build_addlist_footer structure
- No fake FOMO that claims false scarcity quotas; filtration/gate language OK

REPO
c:\Powercore-repo-main\telegram_bot2\tbcc
(work under tbcc/; backend tests from tbcc/backend)

DIAGNOSIS (already measured on island — treat as fact)
- Network lane schedulers have ~440–520 content_variations but only ~13–25 unique flavor prefixes
- Top 3 hooks alone (~125+123+123): "Skip the gates…", "⭐ AOF VIP — ad-free…", "💳 VIP from $6/mo…"
- Cause: aof_growth_hub._append_sponsor_promo_variations multiplies SAME promo_html × every affiliate footer
- Rotation is sequential over padded list → same opening for dozens of posts
- PACKS (id=33) already has 50 unique templates via aof_packs_caption_templates.py — good architecture; operator still saw one live line (need MORE hooks + refresh scheduler after expand). Gold Planet Express line may be missing from bank — add a strategy for it.
- Buffer X: app/data/buffer_x_copy/*.json (100×5) is combinatorial; many share same short stems → feels repetitive

SCOPE — IN
1) Structural fix: stop sponsor-footer padding from inventing duplicate flavor slots
2) Expand PACKS hook bank to ≥100 distinct hooks (keep existing 50 + add ≥50 new, including Planet Express / delivery motifs)
3) Expand lane flavor banks so each network scheduler rotates ≥50 distinct hooks (lane-specific + VIP/gate mix) WITHOUT duplicating the same hook across affiliate footers
4) Expand Buffer X hook stems / templates so each category feels fresh (target: unique first-sentence diversity ≥60 per category, or document equivalent)
5) Tests for: unique-hook counting helper, no sponsor-padding duplicates, pack template count ≥100
6) Script or documented API path to re-sync live schedulers after code change

SCOPE — OUT
- Do not change checkout buttons, Stars plan IDs, Gumroad URLs structure
- Do not rewrite addlist/hub/donate footer builders except to keep them attached once per variation
- Do not start Telegram bots / tray processes
- Do not commit .env or session files
- Do not push to remote unless told
- Do not redesign PACK_BODY / {{PACK_BODY}} injection
- Do not touch dashboard/extension UI

KEY FILES
- backend/app/services/aof_growth_hub.py
  (_append_sponsor_promo_variations, _append_gate_fomo_variations, _append_gumroad_vip_variations, sync_network_schedulers, build_telegram_footer_variants)
- backend/app/services/aof_packs_caption_templates.py
- backend/app/services/loot_pack_pool.py (refresh_aof_packs_scheduler)
- backend/app/services/aof_gate_promo_copy.py
- backend/app/services/aof_main_group_copy.py (vip_promo_minimal_bodies)
- backend/app/data/aof_network.py (per-lane promo_html — expand into multi-hook banks OR new module)
- backend/app/data/buffer_x_copy/*.json + backend/scripts/generate_buffer_x_copy_catalog.py + seed_social_copy_templates.py
- backend/app/services/social_copy_rotation.py
- backend/app/services/scheduled_post_service.py (resolve_scheduled_caption — sequential; keep unless you add hook-level rotation)
- Tests: backend/tests/test_aof_packs_send_time.py, add new tests as needed

ARCHITECTURE REQUIREMENTS
A. Affiliate footers: rotate sponsor line WITHOUT cloning flavor.
   Preferred: keep ONE promo+base-footer slot per flavor hook; pick affiliate at send time OR cycle footer separately.
   Acceptable: at most 1 full caption per unique (hook_prefix). Prune existing duplicates on sync.
B. New module recommended: backend/app/services/aof_flavor_hooks.py (or data/aof_flavor_hooks.py)
   - pack_delivery_hooks() → ≥50 new + integrate into PACK_STRATEGIES
   - lane_flavor_hooks(network_key) → ≥40–60 per lane (or shared bank + lane-colored openers)
   - vip_flavor_hooks() / gate_flavor_hooks() expanded (≥15 each, all used — not [:1])
C. sync_network_schedulers must rebuild variations as:
   [bulletin?] + unique(hook_i + footer_base_or_rotating) + unique gate + unique vip
   Deduplicate by hook prefix before FOOTER_MARKER ("Join the full AOF stack")
D. After code: provide script backend/scripts/resync_flavor_captions.py that:
   - dry-run prints before/after unique_hook counts per scheduler
   - --execute calls sync_network_schedulers + refresh_aof_packs_scheduler
E. Buffer X: regenerate catalog with more distinct HOOKS (not only MID×closer). Prefer editing generate_buffer_x_copy_catalog.py then regenerate JSON; document seed command.

WORKING AGREEMENT
- Uncommitted local work OK; do not push
- After EACH phase: write reverse report under tbcc/docs/handoffs/ then STOP for Cursor ACK
- Prefer small focused commits only if user asks later

PHASE 1 — Structure + unique-hook helper + stop padding (no mass copy yet)
1. Add helper unique_flavor_hook(caption: str) -> str (split on FOOTER_MARKER)
2. Change sync path so sponsor variants do not multiply identical hooks
3. Expand vip_promo_minimal_bodies usage to all bodies (not [:1])
4. Unit tests proving padded list collapses / unique count rises under mock affiliates
5. Verification:
   cd tbcc/backend && py -3.13 -m pytest tests/test_aof_flavor_hooks.py -x -q --tb=short
   (create that file; also keep packs send-time tests green)
6. Write: tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase1_report.md
7. STOP

PHASE 2 — PACKS + lane flavor banks (≥50 new packs + ≥50 unique per lane after sync design)
1. Add ≥50 new PACK hooks matching gold voice (include Planet Express / NEW DELIVERY motifs as ONE strategy among many — variety required)
2. pack_caption_template_variations() must return ≥100 distinct templates (or raise clear cap change + document)
3. Build lane flavor banks; wire into sync_network_schedulers
4. refresh path documented
5. Verification:
   cd tbcc/backend && py -3.13 -m pytest tests/test_aof_flavor_hooks.py tests/test_aof_packs_send_time.py -x -q --tb=short
   python -c "from app.services.aof_packs_caption_templates import pack_caption_template_variations; v=pack_caption_template_variations(); print(len(v), len(set(v)))"
6. Write: tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase2_report.md
7. STOP

PHASE 3 — Buffer X refresh + resync script + dry-run docs
1. Expand Buffer X unique hook stems; regenerate JSON catalogs
2. Document: py -3.13 backend/scripts/seed_social_copy_templates.py (or actual seed flags)
3. Add backend/scripts/resync_flavor_captions.py with --dry-run / --execute
4. Verification:
   cd tbcc/backend && py -3.13 -m pytest tests/test_aof_flavor_hooks.py -q --tb=short
   py -3.13 scripts/resync_flavor_captions.py --dry-run
5. Write: tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase3_report.md
6. STOP — operator runs --execute on island after Cursor ACK (do not SSH/deploy unless asked)

DONE WHEN
- PACKS template set ≥100 unique hooks including gold-style delivery lines
- Network sync no longer creates 100+ slots of the same VIP opening
- Each lane designed for ≥50 unique flavor hooks after sync
- Buffer X catalogs have visibly more distinct openings
- Tests green; reverse reports written per phase
```
