Track: DOCTRINE-IMPL · WEEK1 · Twin forum library · 📋 directive emit

# Forward: Loot forum twin Week-1 (post-ACK)

**Date:** 2026-08-22  
**Against:** Operator ACK — forum-as-library + twin + CTA retarget + rolls-only key + grandfather  
**Doctrine source:** CUR-4c Grok doctrine + Cursor critique (game/vault = design-only, not product lock)  
**Reverse:** `tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1_report.md` after each phase  

Paste the fenced block below into the TARGET.

---

**Literal:** Ship reversible Week-1 for paid forum-as-library via a **new twin** forum: live topic sync, one AI topic feed + remixer, CTA retarget *draft* (no live LV/invite flips), rolls-only 24h key documented, grandfather path for existing VIP — then STOP for ACK before any hard cutover.  
**Ascend:** yes — Week-1 twin slice only; cutover / forward-race / vault = out.  
**TARGET:** Claude Code (Lane C grind) — cold paste; Cursor ACK between phases.

```
## Goal
Implement the reversible Week-1 slice for AOF "forum-as-library" after operator ACK: (1) live-sync Loot Room forum topic map; (2) register/wire a new private twin forum as the paid library destination (operator creates the Telegram chat); (3) feed one healthy lane topic (AI) + remixer cadence into the twin only; (4) write CTA retarget matrix + patch placement doctrine to match ACK locks; (5) document rolls-only 24h loot key + grandfather auto-seat path — dry-run only, no mass invites. Stop before hard cutover, LV dashboard edits, or VIP forward-race.

## Scope
In:
- Live topic list + refresh `aof_main_group_topic_map.py` (or twin-specific map) from Telegram against Loot Room `-1003927742839` and/or the new twin once ident exists
- Operator twin checklist + code registration (env/ident constants, Channel row notes) when operator pastes twin chat id
- One AI topic scheduled path into twin (`message_thread_id`) without changing public lane 288min cadence
- Remixer `/rebundle` smoke plan on that topic (labor already ships — wire/schedule or document beat, do not invent new album engine)
- Docs: patch `AOF_PLACEMENT_DOCTRINE.md` surface matrix to ACK locks; add CTA retarget draft (markdown); note rolls-only key + grandfather in placement or short handoff addendum
- Optional: fulfillment env flag design / dry-run script listing active main-section subscribers who would be auto-seated — **no execute of mass invites** without explicit operator ACK in a later phase

Out of scope:
- Hard cutover (paywall current Loot Room, kill public `+97f4…`, addlist surgery, live Linkvertise destination flips)
- Forward-race / 15-min vault (design-only; not product)
- Native Stars chat-sub as forum ACL (impossible on supergroup — do not attempt)
- Lane Pass $3; game SKUs; price ladder changes; Gumroad reseed
- CADENCE interval re-litigation (288min stays); I3-B rolling prune on free lanes
- Island deploy of money bots / tray starts / payment-loot spawn
- Taboo/BOP kill decision
- Opening paid topics for voyeur/bop/ass while approved=0
- stash@{0} / thisvid arbitrage

## Prior state
Verified / do-not-re-litigate:
- Operator ACK 2026-08-22 locks: **forum-as-library** · **twin** (not in-place paywall) · **CTA retarget** (draft now, live flips later) · **24h loot key = rolls-only, no forum seat** · **grandfather = yes** (existing VIP auto-seated at cutover/beta)
- Game/vault: **not ACK'd as product** — defer until vault inventory named
- INBOX-PIPE (2026-08-22): inbox→classify→route live; commits ce32e86, f9fc9fb, 6d22fe3; gatekeeper_lane_route d93c5ab
- CADENCE (2026-08-22): 11 lanes @ 288min; I3-B deferred; AI ~7d approved runway; voyeur/bop/ass 0 approved
- MAIN_GROUP_IDENT = Loot Room `-1003927742839`; AOF_VIP_IDENT = `-1003982098745` (Stars channel sub target)
- `AOF_MAIN_GROUP_TOPIC_MAP` is STALE (banned Main sync) — PATCH NOTES topic 2408 is live on Loot Room
- Remixer `/rebundle` + `topic_rebundle_service` already ships
- Native Stars `createChatSubscriptionInviteLink` = **channel only**, 30-day — forum ACL = TBCC ledger + invites, not Telegram native group sub
- Public protect_content default ON; Mega→R2 vault PAUSED
- Current Loot Room stays **free hangout** until a later hard-cutover ACK (twin is the library)

Do not invent: twin chat id, member counts, vault file counts.

## Issue cards
| id | symptom | evidence | sev | depends | acceptance |
| I1 | Topic map stale — cannot wire AI thread safely | aof_main_group_topic_map.py STALE note; sync_main_group_topic_map.py | P0 | none | Live `--list` against Loot Room; map refreshed or twin map written with real thread ids; PATCH NOTES 2408 preserved |
| I2 | No paid library chat registered — twin missing in code/env | aof_network.py MAIN_GROUP vs VIP only; operator ACK twin | P0 | operator creates forum | Twin ident + invite documented; Channel/env registration path; current Loot Room NOT paywalled |
| I3 | Twin has no AI topic feed | CADENCE AI pool runway; scheduled_text_posts message_thread_id | P0 | I1, I2 | One scheduler (or documented job) posts to twin AI topic; public 288min lanes untouched |
| I4 | Remixer not on twin topic cadence | topic_rebundle_service; STORAGE_HUB_PANEL_MANUAL | P1 | I3 | Documented or beat/manual smoke: `/rebundle` on twin AI topic; sources delete policy unchanged |
| I5 | Placement doctrine still says Loot Room = public hub / VIP = paid lane | AOF_PLACEMENT_DOCTRINE.md | P0 | none | Surface matrix matches ACK: twin=library; Loot Room=hangout; VIP=deferred game; free lanes=party boards; Loot God=taste |
| I6 | CTA retarget not written — cutover would dead-end | GATE_LINK_AUDIT.md; loot_free; +97f4 invite | P0 | I5 | Markdown CTA matrix: free/teaser/buy paths; **no** live LV or invite edits this track |
| I7 | 24h key vs $18 seat inversion risk / grandfather unspecified in docs | loot bot_section=loot; aof_vip_membership; ACK | P1 | I5 | Docs state: loot key=rolls-only no seat; existing main-section VIP grandfather auto-seat; dry-run seat list optional — no mass invite execute |

## Constraints & gotchas
- Cloud-only money: do **not** start payment/loot/tray locally; no Telethon heavy parallel scrapes
- Do not change `MAIN_GROUP_INVITE`, addlist, or Linkvertise destinations in this track
- Do not rewrite CADENCE 288min intervals
- Do not open empty topics (voyeur/bop/ass)
- Twin chat creation is **operator Telegram UI** — agent stops and asks if twin id missing; do not invent ids
- judgment_ceiling: MAY implement Week-1 wire + docs per ACK locks. MUST NOT invent pricing, enable forward-race, hard-cutover invites, or claim vault inventory
- Prefer smallest commits; no `git add -A`; never commit `.env` / sessions / `.tbcc-run/`
- Push only if `TBCC_AUTO_PUSH=1` or operator asks

## Verification
Done when ALL are true:
1. `py -3.13 scripts/sync_main_group_topic_map.py --list` (from `tbcc/backend`) shows live Loot Room topics OR report documents twin list with real thread ids
2. `AOF_PLACEMENT_DOCTRINE.md` surface matrix matches ACK locks (twin library / hangout / deferred game)
3. CTA retarget draft exists under `tbcc/docs/handoffs/` or `tbcc/docs/` — zero live LV edits (git diff does not touch gate dashboards)
4. Public lane schedulers still 288min (no interval churn) — cite `apply_lane_cadence` idempotent check or DB read
5. If twin ident provided: AI topic post path documented or dry-run; `/rebundle` smoke notes in reverse report
6. Reverse report lists grandfather dry-run counts OR explicit "dry-run skipped — needs island DB" without executing invites
7. No payment/loot bot spawn; health of island untouched unless operator asked deploy (default: **no deploy** this track)

## Working agreement
- Branch: stay on current lane-c / working branch; do not create drive-by branches unless needed
- After each phase: write `tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1_report.md` (append phase), then **STOP for Cursor ACK**. Do not start Phase N+1 until ACK
- Commit per phase when code/docs land; message prefix `feat(aof):` or `docs(aof):`; no secrets
- Operator must paste twin `chat_id` + primary invite before Phase 2 wire

## Phases
### Phase 0 — Topic sync + doctrine/CTA docs (no twin required)
- Run live topic list vs Loot Room; refresh map or write sync output into report
- Patch `AOF_PLACEMENT_DOCTRINE.md` to ACK locks
- Write CTA retarget draft + rolls-only + grandfather notes
- Verify: docs + sync output in report
- Reverse report → STOP for ACK

### Phase 1 — Twin registration (blocked on operator)
- If twin id not in report/env: emit operator checklist (create private forum supergroup, enable topics, add payment/loot/remixer bots as admin, paste ident+invite) → STOP
- If twin id present: register in code/env pattern (prefer env override e.g. `TBCC_AOF_LIBRARY_FORUM_IDENT` over hijacking MAIN_GROUP_IDENT); do not paywall Loot Room
- Verify: constants/env documented; MAIN_GROUP_INVITE unchanged
- Reverse → STOP

### Phase 2 — AI topic feed + remixer on twin
- Resolve AI thread id on twin (create topic if needed — operator or bot API with care)
- Add scheduler row or script targeting twin+thread; do not alter public 288min rows
- Remixer smoke notes (`/rebundle` / `/rebundle go`) on that topic
- Verify: dry-run or one supervised post if operator approves; public cadence untouched
- Reverse → STOP

### Phase 3 — Grandfather dry-run only
- Script or SQL notes: count active main-section subscriptions that would auto-seat
- Print invite plan; **do not** send mass invites
- Verify: counts in report; no Telegram invite blast
- Reverse → STOP — Week-1 complete; hard cutover needs new directive

## Target profile
mode: Agent / grind (multiphase)
tools: files, shell, readonly island queries OK; no MCP bot starts; no live LV
judgment_ceiling: MUST NOT invent doctrine beyond ACK locks; MUST NOT hard-cutover or enable forward-race
context: ZERO prior chat — this fence is the full brief
```

---

## Paste line

Paste into **Claude Code** (repo root `telegram_bot2/`). Feeds `/handoff-cc` if you want Lane C packaging — or paste as-is (sections already match).

## Reverse path

`tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1_report.md` → `/cc-report` → ACK → next phase.
