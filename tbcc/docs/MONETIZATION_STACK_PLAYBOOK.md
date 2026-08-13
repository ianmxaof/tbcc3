# Monetization stack playbook

Legitimate ways TBCC (and AOF surfaces) can stack **measurement → gate → affiliate → owned bot** without breaking publisher ToS.  
**Not included:** wrapping the same outbound URL in two lockers, invisible double-redirects, or mislabeled buttons — networks ban that and it burns domains.

Reference: [AdMaven — Create your first tag](https://publishers-help.ad-maven.com/en/article/create-your-first-tag-7sm30n/) (site tag → placement type → paste between `<head>` tags). TBCC today uses the **Content Locker API** (`link_gate_provider.wrap_admaven_url`), not pop/push tags on a owned site.

---

## Layer model (one user click = one primary gate)

| Layer | What earns | TBCC hook | Typical touchpoint |
|-------|------------|-----------|-------------------|
| **L0 — Beacon** | Attribution only (not CPM) | `click_beacon` + `affiliate_beacon_wrap` | `api.powercore.app/r/{slug}` → 302 |
| **L1 — Content locker** | CPM / CPA per completion | `link_gate_provider`, `pack_gate_wrap` | Linkvertise, AdMaven, Work.ink |
| **L2 — Owned bot** | Stars, keys, subs | `payment_bot`, `loot_bot`, `companion_bot` | `?start=src_*` deep links |
| **L3 — External affiliate** | Rev-share % | `promo_affiliate_rotation`, `seed_promo_affiliate_links` | AI tools, undress bots |
| **L4 — Display / push** | CPM (separate inventory) | *Not wired in TBCC yet* | AdMaven pop / in-page push on **owned** HTML |

**Rule:** Each *click* should complete **one** L1 locker (user choice). Revenue stacks across **steps** in a funnel, not across **two lockers on the same hop**.

---

## Patterns that work (ranked)

### 1. Dual-button tree (already shipped)

Same destination, **two independent gates** — user picks one; you earn on whichever they complete.

- **Where:** PACKS posts (`aof_packs_post_copy`), loot pack pool buttons (`loot_pack_pool.py`)
- **Shape:** `🔗 Linkvertise` + `🔗 AdMaven` under one album
- **Why it’s clean:** Two offers, one completion, no nested wrap

### 2. Beacon → affiliate → bot funnel (already shipped)

- **Where:** `TBCC_AFFILIATE_BEACON_WRAP=1`, Buffer `{spicy}` / `{affiliate}` rotation
- **Shape:** X/Buffer → `r/aff-…` hit row → 302 → `t.me/bot?start=src_aff_…` → funnel touch → Stars/sub
- **Measure:** `revenue_watch_snapshot.py`, `gate_funnel_report`, `analytics/companion-margin`

### 3. Ingest-time parallel gate URLs (already shipped)

- **Where:** `wrap_pack_gates_on_ingest` — LV → AdMaven → work.ink **first success wins** for primary; siblings stored as `gate_adm_url` / `gate_lv_url`
- **Use:** Mega/pack flywheel — one ingest, multiple post-time buttons

### 4. Hub matrix + per-lane gates (already shipped)

- **Where:** `aof_links_hub_menu_variants` + `aof_manual_gate_links`
- **Shape:** PNG menu + inline keyboard **or** HTML blockquote lane list — each lane = its own LV gate
- **Not double-dip:** 12 lanes = 12 chances at **different** sessions, not one URL wrapped twice

### 5. Sequential funnel CTAs (companion → loot → VIP)

- **Where:** `companion_monetize_cta`, `undress_surge`, post-trial Stars upsell
- **Shape:** After reveal exhaustion → loot free roll + VIP checkout buttons
- **Earn:** L2 Stars then L2 loot key then L3 affiliate if they bounce to undress partner

### 6. Forum / landing + AdMaven **site tag** (frontier — not in repo)

Per [AdMaven tag setup](https://publishers-help.ad-maven.com/en/article/create-your-first-tag-7sm30n/): create site → pick vertical → add tag type (pop, push, in-page push, interstitial, lightbox, content blocker) → paste script in `<head>`.

- **Fit:** `docs/AOF_FORUM_DOMAIN.md` static hub, prompt-gate HTML, R2 landing pages
- **Stack:** Page load = L4 CPM **plus** outbound links can still use L1 lockers (different inventory)
- **Do not:** Run pop-under **and** content locker on the **same** click without user-visible choice

### 7. Creator `/model` pool (owned inventory, indirect $)

- **Where:** `loot_creator_platforms`, tier 5+ modifier slots
- **Earn:** Retention + paid rolls, not CPM on creator URL (creator links are **un-gated** by design)

---

## Anti-patterns (do not ship)

| Idea | Why it fails |
|------|----------------|
| LV wrap inside AdMaven wrap on same URL | Second network often strips/blocks; users bounce; account risk |
| Fake “Continue” that fires two lockers | ToS violation |
| Beacon 302 chain through locker before affiliate | Breaks Telegram in-app browser; kills conversion |
| Gate on `/model` creator submissions | Rejected by `loot_creator_platforms` blocked hosts |
| Auto-open pop on Telegram channel posts | Telegram WebView limits; policy risk |

---

## “2–3 in one journey” (legal version)

One **session**, multiple **surfaces**:

1. User clicks Buffer X spicy link → **beacon hit** (L0)
2. Lands spicy bot → trial reveal → **Stars invoice** (L2)
3. Declines → **loot free** CTA (L2) → rolls → sees **LV-gated** hub addlist in tease modifiers (L1 later)
4. Same week, opens **PACKS** channel → completes **AdMaven** on a zip (L1) — different intent, second earn

That is **three revenue types**, not three lockers on one href.

---

## Programs to prioritize in rotation

| Program | TBCC status | Payout | Notes |
|---------|-------------|--------|-------|
| Telegram Stars / subs | Live island | High trust | Primary internal |
| Linkvertise | Live | Mid | Dynamic gates, scrape unwrap |
| AdMaven locker API | Env-ready | Mid | `TBCC_ADMAVEN_API_TOKEN`; dual buttons with LV |
| Work.ink | Env-ready | Mid | Override API |
| Undress / nudify affiliates | Seeded (`nudify.now`, `nudify.systems` Cherry, `braundress`, spicy owned) | Rev-share | Beacon-wrap for measurement |
| **nudify.systems** Cherry-style | **Seeded** (`priority_tier` 8 · `links_hub_ai`) | Crypto withdraw | Operator ref `link.nudify.systems/?r=…` |
| AdMaven pop/push tags | Not wired | CPM | Needs owned page + tag paste |

---

## Operator checklist — add a new stack layer

1. **Placement** — name it (`links_hub_ai`, `x_buffer`, `packs_post`, `forum_head`)
2. **Beacon** — `TBCC_AFFILIATE_BEACON_WRAP=1` + seed `promo_affiliate_links`
3. **Gate** — only if leaving Telegram webview; pick **one** primary locker per button
4. **Income** — `record_income_payout.py` / dashboard sync for external CSV
5. **Watch** — `revenue_watch_snapshot.py` + `source_ref` on beacon

---

## Telegram bot storefront (Telehop-style)

**Verdict:** Good **UX reference**, weak **business fit** as a replacement product.

TBCC already runs a multi-bot storefront (payment, loot, companion, secretary). Telehop sells *hosting* for generic shops. AOF’s moat is **content pools + gates + flywheel**, not white-label SaaS.

**Do borrow:** SKU cards, wallet top-up flow, reseller API for affiliates.  
**Don’t build:** Second parallel shop engine — extend `subscription_plans` + `loot` API instead.

---

## Changelog

- **2026-07-31** — Initial playbook (beacon, dual-button, forum tag frontier, anti-patterns).
