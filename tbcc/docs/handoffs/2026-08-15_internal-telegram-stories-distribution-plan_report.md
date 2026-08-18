# Internal Telegram Distribution Plan — Stories + Telethon promo (Track I)

**Date:** 2026-08-15
**Author:** Claude Code (Lane C), responding as one panelist in the mixture-of-experts internal-traffic brief
**Scope:** Read-only research. No story sent, no code changed, no Telethon session touched.
**Data provenance:** repo grep for `stories.`/`SendStoryRequest`/`getStoriesViews`/`postStory`/`StoryArea`/`canSendStory` (zero matches — confirms the brief's "zero Stories implementation" claim); `telethon_session_lock.py`, `telethon_session.py`, `poster_worker.py`, `telegram_forum.py`, `forum_topics.py`, `aof_topic_mirror.py`, `main_group_topic_resolve.py`, `click_beacon.py`, `gate_funnel.py`, `aof_manual_gate_links.py`; grep for `FloodWait`/`STORIES_TOO_MUCH` (zero matches — confirms no flood-handling exists anywhere in the codebase today, not just for stories). Telegram Stories API mechanics below come from my own knowledge of `core.telegram.org/api/stories` and the Bot API changelog, not a live fetch — anything I'm not fully certain of is flagged `verify Telegram:` / `verify Telethon:` rather than stated as fact, per the brief's own instruction.

---

## Corrections to the brief's stated facts, before the deliverables

**The session model is "one Telegram account, several session files," not "one SQLite session."** `telethon_session_lock.py`'s own docstring: copied session files (`admin_poster`, `admin_import`, `admin_album` — all bootstrapped from `admin.session` via `shutil.copy2`) *"share one Telegram auth key — only one MTProto connection may be live at a time."* That's why `TBCC_TELEGRAM_ACCOUNT_LOCK` exists as a global lock nested *under* every per-file lock (admin/import/poster) — it's not protecting one file, it's serializing every connection on one identity. This matters directly for the story capacity math: **verify in repo/ops before building on it — are "Poster A" and "Poster B" two genuinely different Telegram accounts (two phone numbers, two auth keys), or is "Poster B" a second local session file copied from the same account?** If the latter, they cannot post concurrently at all — they're one MTProto identity serialized by the same account lock, and "two-poster budget" is really "two queue slots on one flood-limit pool," not two independent rate budgets. This single fact should be confirmed before any cadence plan is built on it; §5 below designs for either answer but flags where it changes the plan.

**Forum-topic infrastructure is more built-out than the brief implies.** `forum_topics.py`, `telegram_forum.py`, `aof_topic_mirror.py`, `main_group_topic_resolve.py`, and `aof_main_group_topic_map.py` all exist — topic resolution, Bot-API-vs-Telethon thread-id quirks, and topic mirroring are already real subsystems. This is a stronger, lower-build-cost surface for pillar 3/4 than the brief's phrasing ("topic pins unused") suggests — it's not unused infrastructure, it's an underused *promo* surface on top of already-shipped plumbing.

**No flood-wait handling exists anywhere in this codebase**, for any Telethon send path, story or otherwise (confirmed by grep — zero `FloodWaitError`/`STORIES_TOO_MUCH` references). This isn't a stories-specific gap to design around; it's a gap in the whole Telethon layer that story automation would be the first caller to actually need. Building it is in scope for this plan (§5), not a pre-existing capability to reuse.

---

## 1. Stories capability card

| Surface | Peer type | Boost required? | Link sticker | Analytics |
|---|---|---|---|---|
| **User story** | Own user account (Poster A/B) | No | Yes (`mediaAreaUrl`, any account can attach a link as of Telegram's 2024 loosening of that restriction — `verify Telegram:` confirm current account-tier requirement is gone, it was Premium/verified-only historically) | `stories.getStoriesViews` (aggregate) + `stories.getStoryViewsList` (per-viewer list, retention/size caps for non-Premium — `verify Telegram:` current limits) |
| **Channel/supergroup story** | Channel you admin | **Yes** — `stories.canSendStory` returns `BOOSTS_REQUIRED` below the channel's boost threshold; exact boost-count tiers for post count/duration change over time (`verify Telegram:` current thresholds) | Yes | `stories.getStoryViewsList` → per Telegram, reactions list for channel stories (`verify Telethon:` exact method name distinction from user-story views) |
| **Business-bot-posted story** | A Business-connected personal account, posted *by* a bot | No (it's a user peer under the hood) | Yes | **Bot cannot pull views.** Bot API `postStory`/`editStory`/`deleteStory` exist for Business connections, but there is no Bot API `getStoriesViews` equivalent — you still need a Telethon session on the connected user account for view data. This is the brief's own stated constraint (fact #4), confirmed against the shape of the API: views/reactions are MTProto-only client methods with no Bot API mirror as of the changelog window given. |
| **Live story (RTMP)** | User or channel | Channel: yes | n/a mid-stream | Real-time moderation/ops burden; Stars-paid comments add a payments surface. High cost for a team that hasn't shipped a static story yet. |

**Key mechanics to internalize:**
- `stories.canSendStory` (`verify Telethon: functions.stories.CanSendStoryRequest`) — call before every send, not just once. Returns `BOOSTS_REQUIRED` for under-boosted channels, or a flood error if the account is rate-limited.
- **Period:** the brief's stated fact — non-Premium accounts get `period=86400` (24h) only, even though the API field accepts 6h/12h/24h/48h. Premium unlocks the shorter/longer options. Confirmed as given, not re-derived here.
- **`media_areas`:** `MediaAreaUrl` (the swipe-up link — the only one this plan needs), `MediaAreaSuggestedReaction`, `MediaAreaChannelPost` (embeds a channel post into a story — a legitimate "story teases the channel post" pattern worth knowing about even if unused in 30 days), `MediaAreaGeoPoint`/weather/star-gift areas (irrelevant to this brief).
- **Pinned / archive:** posted stories can be pinned to a profile (the "highlights" grouping the brief calls "story albums" — `verify Telegram:` current official term and whether a distinct "album" object exists beyond pinned/archived story collections).
- **Repost:** forwarding another peer's story to your own (`verify Telethon: functions.stories.SendStoryRequest` `fwd_from_story`-shaped parameter — exact Telethon kwarg name unconfirmed in this pass).
- **Share story as message:** `InputMediaStory` (peer, story id) used as message media — this is real and lets a story be dropped into a chat/lane as a message bubble. Directly usable for pillar 3 ("cross-post story shares into lanes") with no new API surface.
- **Reply to story:** replying to someone's story with a normal message, linked back to that story (`verify Telethon:` exact `InputReplyToStory`-shaped parameter name). Useful only for engaging people who already viewed a story — not a cold-outreach tool, and the brief's spam red line explicitly excludes using this on strangers.
- **`exportStoryLink`** — gets a shareable `t.me/…` deep link for a story; useful for cross-posting a story reference into a caption without re-uploading media.
- **Stealth mode / `searchPosts`** — irrelevant to posting (stealth is viewer-side privacy; hashtag search across stories is a newer, low-priority discovery feature).

**TBCC gap:** zero of the above is implemented. Confirmed by repo grep — no `stories.*` reference anywhere in the backend.

**What to use in 30 days vs. later vs. never:**

| Tier | Item |
|---|---|
| **30 days** | User stories from Poster A/B, single `MediaAreaUrl` → `loot_free` or Named Vault, `InputMediaStory` share-as-message into lanes, `getStoriesViews` polling |
| **Later (needs boosts or more data first)** | Channel stories on Loot Room/lanes, `MediaAreaChannelPost` embeds, reply-to-story on engaged viewers |
| **Never (for this team, this brief)** | Live stories (RTMP + Stars comments), Business-bot `postStory` as a *replacement* for Telethon, Mini App `web_app_share_to_story` (no Mini App exists to hang it on), hashtag `searchPosts` discovery plays |

---

## 2. Internal surface matrix

| Surface | Poster (A / B / bot) | Story? | Message? | Dest | Cannibalization | Ship / Kill |
|---|---|---|---|---|---|---|
| Poster A — user profile | A | **Yes, today, zero build** | n/a (personal profile) | `telegram.me/aof_lootgod_bot?start=src_story_lootgod` | None — new surface, doesn't touch X's clearnet card | **SHIP first** |
| Poster B — user profile | B | **Yes, today, zero build** — *pending the account-identity question in the corrections above* | n/a | Same pattern | None | **SHIP second**, after confirming B is a distinct identity |
| Loot Room (`-1003927742839`) | verify in repo/ops which account owns `admin_poster.session` | No — needs boosts | Yes (existing scheduler) | LV gate or `telegram.me` per doctrine | Low | Message: **ship as-is.** Story: **kill until boost plan priced (week 4)** |
| Lane channels (14: ai/ass/blowjob/big_tits/taboo/voyeur/milf/abg/goon/bop/packs/main_group + mainhub/addlist) | Telethon poster session | No — needs boosts | Yes (existing scheduler) | LV manual gates | Low | Story: **kill until boosts**, same as Loot Room |
| Forum topics (per-lane) | poster session | n/a | **Underused today** — pins exist as infra, not exercised as a promo surface per this brief's framing | topic pin CTA → loot_free | None | **SHIP** — lowest build cost item on this whole list, infra already exists |
| Bots (loot/payment/secretary/album_composer) | bot | Only via Business connection (setup cost, no analytics win — see §1) | Yes (native bot messaging, unrelated to this brief) | n/a | n/a | **KILL for 30 days** — no advantage over Poster A/B via Telethon |
| Goblin drops (footer surface) | n/a — automated spawn | No | Yes (existing) | Claim = clearnet, footer = gate-eligible | n/a to stories | **Out of scope here** — 4 drops/0 claims (live, 2026-08-15) is a claim-conversion problem, not a stories problem; flagged, not solved, by this plan |

---

## 3. 30-day internal calendar — session-safe, boosts before channel stories, analytics before cadence

**Week 1 (days 1–7): capability confirmation, one story total, build the join before scaling.**
- Day 1 — `canSendStory` check only (no send) against Poster A's own peer and against the Loot Room channel peer, from a read-only script. Confirms the boost gate empirically instead of assuming.
- Day 2 — Extend the existing `source_ref` convention (already live: `src_lv_*` for gates, `src_aff_*` for X affiliate) with `src_story_*` — zero new subsystem, just new prefixes on the existing `ClickLink`/beacon pattern.
- Day 3 — Send **one** test user story from Poster A: vertical glimpse creative, one `MediaAreaUrl` → `telegram.me/aof_lootgod_bot?start=src_story_lootgod_test`, `period=86400`.
- Day 4 — Pull `getStoriesViews` on that one story; confirm the story-id → `source_ref` → click beacon → `UserFunnelTouch` → `IncomeEntry` chain actually joins end-to-end before sending a second story.
- Days 5–6 — Repeat once from Poster B. This send is itself the discriminating test for the account-identity question in the corrections above: if it contends with Poster A's session on the account-level Redis lock, they're the same identity.
- Day 7 — Week 1 review, split exactly as the brief demands: reach (views) vs. start (`src_story_*` touches) vs. restrict (boost/flood errors hit) vs. session (lock contention observed).

**Week 2 (days 8–14): cadence under flood limits, user stories only.**
- One story per poster per day, conservative by default since no documented weekly ceiling exists to plan against — back off hard and stop (don't retry-loop) on the first `STORIES_TOO_MUCH`/`FloodWaitError`. Every story: exactly one link sticker, always `loot_free` or a Named Vault checkout, never a locker.
- One story per week shared as a message into a lane channel (`InputMediaStory`) — tests the share-as-message surface without needing boosts.

**Week 3 (days 15–21): forum topics and native surfaces, still no channel stories.**
- Days 15–17 — Pin a fresh `loot_free`-CTA message per lane's forum topic, each with its own `src_topic_pin_{key}` ref.
- Days 18–19 — If an Inner-Circle-style theme vote exists by then, screenshot it into a Poster A/B story with a link sticker back to the vote channel/poll.
- Days 20–21 — Compare topic-pin click→start against story click→start on real numbers — that answer, not intuition, decides where week 4 effort goes.

**Week 4 (days 22–30): channel stories only if a boost plan is priced.**
- Days 22–24 — If Loot Room or a lane would need boosts, price the plan (self-boosting owned channels from the operator's own account(s) is the cheapest path, contingent on Premium status — `verify in repo/ops`) before writing any code for it.
- Days 25–27 — If viable, one test channel story with the same single-link-sticker discipline as user stories.
- Days 28–30 — Full-month reach→start review across every `src_story_*`/`src_topic_pin_*` ref; decide whether channel stories earned their boost cost.

No new user accounts. No bought members. No channel story before a priced boost plan exists.

---

## 4. Analytics spec

- **Reuse, don't rebuild, the join.** `gate_funnel.py`'s click → touch → revenue join already works on any `source_ref` prefix — `src_story_*` and `src_topic_pin_*` slot into the existing `ClickLink`/`UserFunnelTouch`/`IncomeEntry.traffic_source_ref` pipeline with zero schema change, as long as the story's link sticker itself is a beaconed `api.powercore.app/r/…` URL (same pattern already used for the 16 LV lane gates), not a bare `telegram.me` link.
- **New, genuinely missing piece:** a small table for story-level view/reaction telemetry — `story_id`, `peer_id`, `poster` (A/B), `source_ref`, `sent_at`, `period_s`, `views_count`, `forwards_count`, `reactions_count`, `pulled_at`. Nothing like this exists today (confirmed by grep). Shape it exactly like `income_poll_worker.py`'s Celery Beat pattern — periodic pull, not real-time.
- **Bot API cannot serve this task at all** — `getStoriesViews` is MTProto-only (brief's own stated fact, and there's no Bot API mirror in the changelog window given). The poll worker must run through the existing Telethon session lock (`telethon_session_lock.py`), which means it queues behind admin/import/poster/album operations exactly like any other Telethon call. Size the poll interval generously — this is one more consumer of an already-contended shared lock, not a free lookup.
- **Viewer lists vs. aggregate counts:** full per-viewer lists may be capped for non-Premium accounts (`verify Telegram:` current retention/size limits — don't assume unlimited). Treat aggregate `views_count`/`forwards_count`/`reactions_count` as the reliable baseline metric and viewer lists as a bonus signal, not the core measurement — this avoids building an analytics pipeline that silently degrades if the account's Premium status changes.
- **Do not treat view count as revenue**, per the brief's own diagnostic split — a story's success metric chain is reach (views) → start (`src_story_*` touch) → revenue (`IncomeEntry`), and each link should be reported separately, the same way `gate_funnel_report()` already refuses to conflate clicks with revenue for gate links.

---

## 5. Telethon automation design

- **Don't add a fifth session file without a reason.** The existing pattern (`admin`, `admin_poster`, `admin_import`, `admin_album`) is: one dedicated session per *workload*, all sharing one auth key, all serialized by `telethon_session_lock.py`'s nested account lock. Two real options: (a) add `admin_story` as a new dedicated file for this workload, following the exact same bootstrap/lock pattern as `admin_album`, or (b) send stories from whichever session already represents each poster's identity (if Poster A/B are genuinely separate accounts, each already has its own session somewhere in this family; if not, see the correction above — there's only one identity to route through regardless of file count).
- **Worker shape:** a new Celery task type mirroring `poster_worker.py` exactly — per-task event loop via `asyncio.run()` (no client reuse across tasks, per the existing `_poster_client_lock` pattern), session acquired via `telethon_session_lock.py`, disconnected after I/O per `telethon_disconnect_admin_after_io()`'s existing logic. This is a new task on an existing architecture, not a new architecture.
- **Flood handling — build from scratch, nothing to reuse.** Grep confirms zero `FloodWaitError`/`STORIES_TOO_MUCH` handling anywhere in this codebase today. Catch `errors.FloodWaitError` / the story-specific too-much error (`verify Telethon:` exact exception class for `stories.sendStory`), back off past the reported wait, and **stop and alert rather than retry-loop** — a flood storm on the shared account lock would stall every other Telethon-dependent surface (imports, scheduled posts, album composer) behind it, not just stories.
- **`canSendStory` gate before every send**, not just once at design time — treat `BOOSTS_REQUIRED` as a hard stop for channel targets, never a retry condition.
- **Copy-from-admin forbidden while the island holds the session** — per this repo's own operator policy (root `CLAUDE.md`: never spawn a second bot process locally) and per the exact failure mode `telethon_session_lock.py` exists to prevent (`AuthKeyDuplicated`, "wrong session ID" storms from concurrent logins of the same account). Any story-automation testing must run against the island's live session state, not a fresh local login of the same account.

---

## 6. Red-line appendix

| Technique | Verdict | Why |
|---|---|---|
| Cold group spam with Poster A/B | **Rejected** | Brief's own constraint; matches this repo's general no-unsolicited-mass-action posture |
| LV as the primary story link sticker | **Rejected** | Same doctrine as Track T's `is_protected_clearnet_url`/`prompt_gate_placement` guards — a story's one link sticker is the story-surface equivalent of the sacred checkout/claim slot |
| Dual session / second login of the same account | **Rejected** | The exact failure mode `telethon_session_lock.py` was built to prevent; violates root `CLAUDE.md`'s "never spawn a second bot process" |
| Fake viewers / bought story views | **Rejected** | No code path exists, none should be added — consistent with the fake-FOMO rejection in the other two panelist briefs in this thread |
| Live stories (RTMP + Stars comments) | **Rejected for 30 days** | Real-time moderation cost for a team that hasn't shipped a *static* story yet; revisit only after the static-story click→start path is proven |
| Mini App `web_app_share_to_story` | **Rejected for now** | No Mini App exists in this repo (confirmed by grep); building one solely to unlock this mechanic is out of scope for an internal-distribution brief |
| Business-bot `postStory` as primary posting path | **Rejected for 30 days** | Adds a new setup surface (enabling Business, connecting a bot) that still doesn't solve analytics — Business `postStory` has no `getStoriesViews` equivalent either, so it buys nothing over Poster A/B via Telethon directly |
| Channel stories without a priced boost plan | **Rejected until week 4** | Matches the brief's own scoring rule — loses to user stories from Poster A/B by default |
| A third user account | **Rejected** | Operator constraint — every idea needing a third account is out of budget, not designed around |
