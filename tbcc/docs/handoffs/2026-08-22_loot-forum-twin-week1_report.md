Track: loot-forum-twin-week1 · Lane C · Phase 0 of 3

# Report: AOF forum-as-library twin — Week-1 (Phase 0)

**Against:** `tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1.md` — ACK locks: forum-as-library · twin (not in-place paywall) · CTA retarget (draft) · 24h loot key = rolls-only · grandfather = yes.
**Date:** 2026-08-22

## Phase 0 — Topic sync + doctrine/CTA docs (no twin required)

**Status: done.**

### I1 — live topic sync (P0)

Ran `scripts/sync_main_group_topic_map.py --list` against Loot Room (`-1003927742839`). **Not** run locally — the script opens `admin.session` via Telethon and needs the shared Redis session lock; running it on the operator PC against local `.env` (localhost Postgres/Redis) would risk a second Telethon connection outside the island's lock coordination (409 risk per operator policy). Ran it the documented way instead:

```
ssh root@5.161.53.91 'cd /opt/tbcc/infra && docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island exec -T api python scripts/sync_main_group_topic_map.py --list'
```

One transient retry (`attempt 1/8`, event-loop reset), self-healed per the script's existing backoff — not a new issue. Result: **every lane thread ID in the static map was stale**, and two live topics (`blowjob`, `bop`) were missing from the map entirely.

| lane | old static id | live id | live title |
|---|---|---|---|
| ai | 17 | 562 | AOF AI 18+ |
| ass | 7 | 405 | AOF ASS 18+ |
| big_tits | 5 | 6 | AOF BIG TITS 18+ |
| abg | 25 | 518 | AOF ABG / LBFM 18+ |
| goon | 182 | 202 | AOF GOON 18+ |
| milf (+ dup gilf row) | 19 / 9 | 523 | AOF MILF / GILF 18+ (now one combined topic) |
| packs | 32 | 204 | AOF PACKS 18+ |
| voyeur | 8011 | 557 | AOF PUBLIC / VOYEUR 18+ |
| taboo | 8888 | 525 | AOF NICEST TABOO 18+ |
| blowjob | *(missing)* | 206 | AOF BLOWJOB 18+ |
| bop | *(missing)* | 200 | AOF BOP 18+ |

Unchanged and confirmed still correct: `MAIN_GROUP_PATCH_NOTES_TOPIC_ID=2408` (live title "PATCH NOTES"), `MAIN_GROUP_GENERAL_TOPIC_ID=1` (live title "RECEPTION / PARTY / TOWNSQUARE"). One live topic has no network-channel match and was left out of the map (not a lane): `COMMONS / BULLETINS` (695).

**Applied:** rewrote `tbcc/backend/app/data/aof_main_group_topic_map.py` — `AOF_MAIN_GROUP_TOPIC_MAP` now holds all 11 live lane thread IDs (added `blowjob`, `bop`; collapsed the milf/gilf duplicate to the one live combined topic), dropped the stale docstring/comment. **Not yet deployed** — this is a local edit; the island still runs the old stale map until a deploy ships it. Sanity-checked the edit imports cleanly and dedupes to 11 rows via a local Python import of the module (no DB/Redis touched — pure dataclass data, safe to import off-island).

### I5 — placement doctrine patched to ACK locks (P0)

Patched `tbcc/docs/AOF_PLACEMENT_DOCTRINE.md` surface matrix: added a **AOF Library (twin)** row (library role, Week-1 = one AI topic + remixer only, no public CTA yet), reframed **Loot Room** as hangout (free, not the paywall — cadenced-checkout language removed), reframed **AOF VIP** as deferred game/vault (not ACK'd as product, unchanged native Stars sub not touched), added a **Free lanes** row (party boards, ties to the CADENCE track's 288min cadence), reframed **Loot God bot** as taste/sampler with the rolls-only key note. Added a "Library access rules (Week-1 ACK)" section stating the 24h key ≠ seat rule and the grandfather-auto-seat/no-hard-cutover rules explicitly.

### I6 — CTA retarget draft (P0)

New file `tbcc/docs/AOF_CTA_RETARGET_DRAFT.md` — one matrix row per current CTA surface (from `GATE_LINK_AUDIT.md`) showing "Week-1 change: None" for every existing live destination, plus a placeholder row for the twin (does not exist yet, no public CTA points at it). Explicit "what this draft deliberately does NOT do" section (no LV dashboard edits, no invite constant changes, no `BULLETIN_CHANNEL_INVITES` entry) and a "trigger for go live" checklist gating the matrix behind three future ACKs. Zero live edits — confirmed no `GATE_LINK_AUDIT.md` or any LV-adjacent dashboard file touched (`git status` below).

### I7 — rolls-only key + grandfather notes

Folded into the doctrine patch above (Library access rules section) rather than a separate addendum — directive allowed either.

## Completion gates

| Gate | Result |
|---|---|
| Tests | No `TEST_MAP.md` entry for `aof_main_group_topic_map.py`; no dedicated test file exists. This is pure dataclass data (no branching logic) — verified by local import + manual dedup check (11 rows, correct network-key grouping) rather than pytest. Suggest a small `test_aof_main_group_topic_map.py` asserting no duplicate `network_key` collisions and PATCH NOTES/RECEPTION ids stay outside the tuple, as a later follow-up — not blocking. |
| Migration | N/A — no schema touched. |
| Stack | No bot/Celery/tray spawn. Topic sync ran read-only inside the island's existing `api` container over SSH — did not start anything new. |
| Extension version | N/A — no `tbcc/extension/` files touched. |
| Git | See below. |
| Scope | 3 files touched (2 modified + 1 new doc) + this report. Under the 8-file halt threshold. |

```
$ git status --short
 M tbcc/backend/app/data/aof_main_group_topic_map.py
 M tbcc/docs/AOF_PLACEMENT_DOCTRINE.md
?? tbcc/docs/AOF_CTA_RETARGET_DRAFT.md
?? tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1.md
?? tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1_report.md
```

Not yet committed — holding for your ACK per the working agreement (commit per phase, message prefix `docs(aof):`).

## Constraints honored

No local Telethon/Redis/Postgres spawned. No LV dashboard edits. No `MAIN_GROUP_INVITE` / addlist / any `aof_network.py` invite constant touched. No twin id invented — Phase 1 stays blocked on you pasting `chat_id` + invite. No doctrine invented beyond the literal ACK locks and the directive's own I5 acceptance text.

## Open item for you

The topic map fix (`aof_main_group_topic_map.py`) is a real, unrelated-to-twin bug fix — the island has been running on stale thread IDs since before this track. It's low-risk to deploy on its own (data-only, no behavior branch changes) but I'm holding it for your ACK rather than shipping mid-report, since deploy wasn't asked for this phase and the directive's default is "no deploy this track."

## ACK received

> ACK'd Phase 0, 2026-08-23. Proceed Phase 1a: operator checklist + inert env/ident pattern only. No twin ids, no scheduler wiring, no Loot Room paywall. Stop for Cursor ACK.

## Phase 1a — twin operator checklist + env pattern

**Status: done.**

### I2a — operator checklist

New section below ("Twin forum — operator checklist") — everything in it is generic setup instruction, no invented Telegram ids. Real bot handles used where the codebase has a fixed public `@handle` (loot: `@aof_lootgod_bot`, payment/subscriptions: `@aofsubscriptions_bot` — both confirmed live via `aof_network.py` / `aof_manual_gate_links.py` promo copy, not guessed). The remixer/album-composer bot has no fixed public handle in code — it's resolved dynamically from `TBCC_ALBUM_COMPOSER_BOT_TOKEN` via BotFather's `getMe` at runtime (`bots/album_composer_bot.py`) — checklist references it by that env var identity instead of inventing a handle. Also flagged: scheduled posts (`scheduled_post_service.send_scheduled_post`) run through Telethon (`client: TelegramClient`, the `admin.session` account), not a bot — so the admin account itself needs membership + post rights in the twin for Phase 2, separate from the three bots.

### I2b — env/ident pattern

New file `tbcc/backend/app/data/aof_library_forum.py` — `TBCC_AOF_LIBRARY_FORUM_IDENT` / `TBCC_AOF_LIBRARY_FORUM_INVITE`, read via `os.getenv`, both return `None` when unset (verified locally: `aof_library_forum_ident()==None`, `aof_library_forum_invite()==None`, `aof_library_forum_registered()==False` with no env set). Modeled on the existing `os.getenv("TBCC_X") or DEFAULT` pattern (`checkout_list_hub.py`, `aof_vip_checkout.py`) but **no default** — unlike VIP/checkout-list, there is no real value to fall back to yet, so unset must resolve to `None`, not a placeholder string. **Zero callers** — not imported by `aof_network.py`, `BULLETIN_CHANNEL_INVITES`, any scheduler, or any service. Purely additive; nothing in the running system changes behavior from this file existing.

`MAIN_GROUP_IDENT` / `MAIN_GROUP_INVITE` in `aof_network.py` are untouched — confirmed via `git diff` (not in this phase's changed-file list below).

### Twin forum — operator checklist

Do these in the Telegram app, then paste the two values back into the next directive (do not paste them into chat as a "just fix it" — they need to land as a proper Phase 1b directive so this stays reversible):

1. **Create a new private group**, not a channel (payment/loot bots need group semantics for topic threads).
2. **Enable Topics** (Group settings → Group Type → Topics on) — this converts it into a forum.
3. **Create one topic**: `AI` — Week-1 scope is exactly one lane feed, don't pre-create the others yet (matches CADENCE/doctrine: don't open empty topics ahead of approved content).
4. **Add these as admins** (post messages + manage topics, at minimum):
   - `@aof_lootgod_bot` (loot)
   - `@aofsubscriptions_bot` (payment/subscriptions)
   - The album-composer/remixer bot tied to `TBCC_ALBUM_COMPOSER_BOT_TOKEN` in `tbcc/.env` — you'll know it by its BotFather name, code never hardcodes a public handle for it
   - The Telegram account behind `admin.session` (your own operator account, most likely) — Phase 2's scheduled AI-topic posts run through this account via Telethon, not through a bot
5. **Copy the chat_id** (Telegram shows it once you view the group's info via a bot/API, or it's derivable the same way `MAIN_GROUP_IDENT` was originally captured) **and the primary invite link**.
6. **Paste both back** as the start of a Phase 1b directive — that's the only way real values enter `aof_library_forum.py`; nothing in this codebase invents or scrapes them for you.

Nothing above pings the codebase — this checklist can be executed at any pace with zero deploy or code risk.

## Completion gates (Phase 1a)

| Gate | Result |
|---|---|
| Tests | `aof_library_forum.py` is pure stdlib (`os.getenv` only), no branching beyond null-checks. No `TEST_MAP.md` entry. Verified by local import (see I2b) rather than pytest — same reasoning as Phase 0's topic-map check. Not blocking. |
| Migration | N/A. |
| Stack | N/A — no bot/Celery/tray spawn, no island contact this phase. |
| Extension version | N/A. |
| Git | See below. |
| Scope | 2 new files (`aof_library_forum.py`, this report section) on top of Phase 0's 3 — 5 total, under the 8-file halt threshold. |

```
$ git status --short (scope-relevant files only)
 M tbcc/backend/app/data/aof_main_group_topic_map.py     (Phase 0)
 M tbcc/docs/AOF_PLACEMENT_DOCTRINE.md                    (Phase 0)
?? tbcc/docs/AOF_CTA_RETARGET_DRAFT.md                    (Phase 0)
?? tbcc/backend/app/data/aof_library_forum.py             (Phase 1a)
?? tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1.md
?? tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1_report.md
```

## Constraints honored (Phase 1a)

No twin `chat_id` / invite invented anywhere — `aof_library_forum.py` returns `None` for both until you set the env vars. `MAIN_GROUP_IDENT`, `MAIN_GROUP_INVITE`, `BULLETIN_CHANNEL_INVITES`, addlist, and every live LV destination are untouched. No scheduler/remixer wiring (that's Phase 2). No Loot Room paywall. No bot spawn, no island contact.

## ACK received

> ACK Phase 1a, 2026-08-23. Proceed Phase 1b: register twin IDENT `-1003790667061` / INVITE `https://t.me/+dTExOHWqbMU5YWFl` + 11 pasted topic thread ids (AI=57 is Week-1's only feed target). No scheduler wiring, no Loot Room paywall, no CTA flips.

## Phase 1b — register twin ident/invite + topic inventory

**Status: done.**

### I2-reg — `aof_library_forum.py` switched from inert-None to VIP-style registered

Rewrote the module to the same pattern as `AOF_VIP_IDENT` / `TBCC_AOF_VIP_CHANNEL_IDENT` (`aof_vip_checkout.py`): a committed default plus env override. `AOF_LIBRARY_FORUM_IDENT_DEFAULT = "-1003790667061"`, `AOF_LIBRARY_FORUM_INVITE_DEFAULT = "https://t.me/+dTExOHWqbMU5YWFl"` — env vars `TBCC_AOF_LIBRARY_FORUM_IDENT`/`INVITE` still win if ever set, matching how every other AOF channel ident in this codebase is overridable.

Verified locally with env unset (defaults resolve, matching the directive's "True when env unset if defaults used" branch):

```
ident: -1003790667061
invite: https://t.me/+dTExOHWqbMU5YWFl
registered: True
```

No display name registered — operator said "no name for now." The invite's Telegram-side preview title (reportedly "TheHoneyGoon") is not written into any doctrine/brand file; `aof_library_forum.py`'s docstring explicitly flags this so a future phase doesn't treat the preview title as a product lock.

**Still zero callers.** Not imported by `aof_network.py`, `BULLETIN_CHANNEL_INVITES`, any scheduler, or any service — same as Phase 1a, just no longer returning `None`.

### I2-map — new `aof_library_forum_topic_map.py`, all 11 pasted thread ids

| title (operator) | thread_id | network_key |
|---|---|---|
| ai | 57 | ai |
| ass | 59 | ass |
| public / voyeur | 61 | voyeur |
| bop | 63 | bop |
| abg / azn | 65 | abg |
| big tits | 67 | big_tits |
| milf / gilf | 69 | milf |
| nicest taboo | 71 | taboo |
| full length | 73 | full_length |
| blowjob | 75 | blowjob |
| webcams | 77 | webcams |

`AOF_LIBRARY_FORUM_WEEK1_FEED_THREAD_ID = 57` is a module-level constant, documented in the file's docstring as the **only** topic scheduled/fed this track. `webcams` (77) carries `network_key="webcams"` — there is no `AofNetworkChannel` with that key in `aof_network.py` (checked: `main, ai, blowjob, big_tits, taboo, voyeur, milf, ass, abg, packs, goon, bop, inbox, full_length`) — the docstring explicitly says this is inventory only, not a product SKU, and adding a real "webcams" channel needs its own doctrine ACK. Not this phase.

This module is **not** synced by `scripts/sync_main_group_topic_map.py` — that script's `MAIN_GROUP_IDENT` target is Loot Room, a different chat than the twin. All 11 rows here came directly from your paste; nothing was scraped or invented.

Verified locally: 11 rows, `library_forum_topic_for_network_key("ai").message_thread_id == 57`.

### I2-fence — no public-surface bleed

`git diff` confirmed to touch only the two new `app/data/aof_library_forum*.py` files plus this report — `aof_network.py` (`MAIN_GROUP_IDENT`, `MAIN_GROUP_INVITE`, `BULLETIN_CHANNEL_INVITES`, `AOF_VIP_*`) has zero diff. No `GATE_LINK_AUDIT.md` edit, no scheduler table touched, no CADENCE interval touched.

## Completion gates (Phase 1b)

| Gate | Result |
|---|---|
| Tests | Both files are pure stdlib (`os.getenv`) / dataclass data, no branching beyond string presence and a linear key lookup. No `TEST_MAP.md` entry. Verified by local import + assertions (see I2-reg/I2-map) rather than pytest — same reasoning as Phase 0/1a. Not blocking. |
| Migration | N/A. |
| Stack | N/A — no bot/Celery/tray spawn, no island contact this phase. |
| Extension version | N/A. |
| Git | 2 new files (`aof_library_forum_topic_map.py` new; `aof_library_forum.py` modified in place, same file as Phase 1a) + this report edit. `aof_network.py` untouched (confirmed above). |
| Scope | 2 files touched this phase, 7 total across the track (Phase 0: 3, Phase 1a: 2, Phase 1b: 2) — under the 8-file halt threshold; flagging since the *track* total is close to it. |

## Constraints honored (Phase 1b)

Values registered are exactly what you pasted — no invented ids, no invented display name, no invented "webcams" product. `MAIN_GROUP_IDENT`, `MAIN_GROUP_INVITE`, `BULLETIN_CHANNEL_INVITES`, addlist, and every live LV destination remain untouched (confirmed via `git diff`). No scheduler or remixer row created for AI(57) or any other topic — that's explicitly Phase 2. No Loot Room paywall, no public CTA edit, no island deploy, no bot spawn.

## ACK received

> ACK Phase 1b, 2026-08-23. Proceed Phase 2: register display name "Archive of Filth"; one supervised/scheduled AI-topic (thread 57) content path; document + enable remixer oversight across ALL twin topics, not AI-only. Stop before grandfather invites, hard cutover, or live LV/CTA flips.

## Phase 2 — display name, AI feed path, remixer-all-topics

**Status: done.**

### I-name — display name locked

Added `AOF_LIBRARY_FORUM_DISPLAY_NAME = "Archive of Filth"` to `aof_library_forum.py` (env override `TBCC_AOF_LIBRARY_FORUM_DISPLAY_NAME` available, same pattern as ident/invite) and a new `aof_library_forum_display_name()` accessor. Doctrine row in `AOF_PLACEMENT_DOCTRINE.md` renamed from "AOF Library (twin)" to "AOF Library — Archive of Filth (twin)". Docstrings on both `aof_library_forum.py` and `aof_library_forum_topic_map.py` explicitly flag that the invite's Telegram-side preview title ("TheHoneyGoon") is not the product name. No other doc references the twin by any other name — checked `AOF_CTA_RETARGET_DRAFT.md` (still name-agnostic, no edit needed there).

### I3 — AI feed path: script written, dry-run only (not executed)

Wrote `tbcc/backend/scripts/seed_library_forum_ai_feed.py` — idempotent, dry-run-by-default / `--execute` pattern (same shape as `apply_lane_cadence.py`). It would create exactly one `channels` row (`identifier=-1003790667061`, name "Archive of Filth (twin)") and one `scheduled_text_posts` row (`name="AOF LIBRARY — AI topic (twin)"`, `message_thread_id=57`, `pool_id=2` — the existing **AOF AI POOL**, same approved media source as the public AI lane — `interval_minutes=288`, `pool_only_mode=True`, `album_size=1`, `scheduler_category="manual"`).

**Did not push this script to the island or run it there.** Pushing it would require a hot-patch/deploy (the script's two new import dependencies, `aof_library_forum.py`/`aof_library_forum_topic_map.py`, aren't on the island's image yet either), and `hot-patch-island.ps1` restarts containers unconditionally by design — more than this phase's "no island deploy" default, and more than "documented or dry-run" requires. Instead I validated the plan against real island state with a read-only query:

```
twin channel rows: []                          (confirms nothing already exists — no dup risk)
AI SCHEDULER template: id=2 channel_id=2 pool_id=2 interval=288 pool_only_mode=True album_size=1
                        scheduler_category='main_lane'
existing twin scheduler rows: []
```

The script's proposed values (`pool_id=2`, `interval=288`, `pool_only_mode=True`, `album_size=1`) intentionally mirror the live public AI scheduler's template — same content source, different destination, same cadence discipline. `scheduler_category="manual"` (not `"main_lane"`) so it stays outside `apply_lane_cadence.py`'s `LANE_SCHEDULER_NAMES` allowlist by construction — confirmed by re-running `apply_lane_cadence.py` (dry-run) after this phase's other work: **still `0/11 rows changed, 11/11 matched`** — the twin path cannot be swept up by that script, and the 11 public rows are untouched.

**This is deliberately a documented-and-ready script, not a live scheduler row.** Running `--execute` (after a hot-patch/deploy makes the script and its dependencies available on the island) is the moment this actually starts posting into the twin — that's a separate, explicit step for you or a future directive, not bundled into this phase.

### I4 — remixer oversees all twin topics, not AI-only

Confirmed by reading `bots/remixer_rebundle.py`: its own docstring is "group loose media into albums in **any chat the bot admins**" — there is no per-channel/per-topic allowlist or registration table gating `/rebundle`; authorization is by operator/admin Telegram user id, not by chat. Since you've confirmed all bots (including album-composer) and all three Telegram accounts are already admin across the whole twin, remixer oversight is **already live on every topic** — no code change was needed or made for this to be true.

What I did change: `aof_library_forum_topic_map.py`'s docstring now explicitly separates the two scopes that were previously conflated in Phase 1b wording — **scheduled auto-feed = AI (57) only**, **remixer curation = all 11 topics** — so a future reader doesn't assume "AI-only" applies to remixer too. Added two small helpers (`library_forum_topic_deep_link()`, `library_forum_smoke_targets()`) that build `t.me/c/{internal_id}/{thread_id}` links for every twin topic — pure formatting, zero callers, exists so you (or a future directive) can print a ready smoke-test list instead of hand-assembling links. Verified locally:

```
('ai', 57, 'https://t.me/c/3790667061/57')
('ass', 59, 'https://t.me/c/3790667061/59')
... (11 rows total, one per topic)
```

**Manual smoke checklist (your action, not automatable from here — I have no live Telegram session into the twin):** run `/rebundle` in the AI topic (57) and at least one other, e.g. blowjob (75), and confirm the bot responds with album grouping in both. That's the acceptance path the directive names as an alternative to a scripted smoke test.

### I-fence — no public-surface bleed

`git diff` this phase touches only: `aof_library_forum.py`, `aof_library_forum_topic_map.py`, `AOF_PLACEMENT_DOCTRINE.md` (one line — the twin's matrix row), the new `seed_library_forum_ai_feed.py`, and this report. `aof_network.py` (`MAIN_GROUP_IDENT`, `MAIN_GROUP_INVITE`, `BULLETIN_CHANNEL_INVITES`, `AOF_VIP_*`) — zero diff, re-confirmed. No `GATE_LINK_AUDIT.md` edit. No non-AI twin scheduler row exists (none were created at all, AI included — see I3). Public 288m cadence re-verified live (see below) — unchanged.

## Completion gates (Phase 2)

| Gate | Result |
|---|---|
| Tests | `aof_library_forum.py`/`aof_library_forum_topic_map.py` additions are pure stdlib/dataclass, no new branching worth a unit test. `seed_library_forum_ai_feed.py` is an idempotent seed script in the same family as `apply_lane_cadence.py`, which also has no dedicated test — matching existing convention. No `TEST_MAP.md` entry. Verified by local import (display name, deep-link helpers) and a real read-only island query (channel/scheduler absence, AI template values) rather than pytest. Not blocking. |
| Migration | N/A — no schema touched; `seed_library_forum_ai_feed.py` writes rows, not schema, and wasn't executed. |
| Stack | No bot/Celery/tray spawn. One read-only DB query via the island's existing `api` container (same pattern as Phase 0's topic sync and this phase's `apply_lane_cadence.py` dry-run re-check). No hot-patch, no deploy, no restart. |
| Extension version | N/A. |
| Git | See below. |
| Scope | 4 files touched this phase (3 modified + 1 new script) on top of Phase 0/1a/1b's 6 (one file, `aof_library_forum.py`, already counted) — **7 distinct files total across the whole track**, still under the 8-file halt threshold but worth flagging before any Phase 3 additions. |

```
$ git status --short (scope-relevant files only)
 M tbcc/backend/app/data/aof_library_forum.py
 M tbcc/backend/app/data/aof_library_forum_topic_map.py
 M tbcc/docs/AOF_PLACEMENT_DOCTRINE.md
?? tbcc/backend/scripts/seed_library_forum_ai_feed.py
 M tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1_report.md
```

## Constraints honored (Phase 2)

No pricing, hard-cutover, VIP=library, or "webcams" SKU invented. No twin topic auto-fed except the documented (not executed) AI path. Remixer's "all topics" scope is a documentation clarification of existing bot behavior, not a new grant of access — the bot already had it via existing Telegram admin rights the operator set up. `MAIN_GROUP_IDENT`, `MAIN_GROUP_INVITE`, `BULLETIN_CHANNEL_INVITES`, addlist, and every live LV destination untouched. No island deploy, no hot-patch, no bot Start. Public 288m cadence re-verified unchanged.

---

**Track: loot-forum-twin-week1 · Phase 2 done — STOP for Cursor ACK. Phase 3 (grandfather dry-run) needs a fresh directive; so does actually executing `seed_library_forum_ai_feed.py --execute` (requires a hot-patch/deploy first, which also needs its own ACK per this phase's "no island deploy" default).**
