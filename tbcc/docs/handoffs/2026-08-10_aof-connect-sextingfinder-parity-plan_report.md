# Reverse handoff — AOF Connect (SextingFinder / SextFun parity) plan

**Date:** 2026-08-10
**Mode:** Plan / Ask only — no code, no migrations, no commits in this pass.
**Source task:** `tbcc/docs/handoffs/2026-08-10_aof-connect-sextingfinder-parity-plan.md`
**Status:** Draft plan, awaiting Cursor ACK on the 5 open questions in §12 before any implementation starts.

---

## Executive summary

AOF Hub (`aof-forum/`) already has every primitive **Connect** needs except the listing itself: auth (`profiles`), a tag system, presigned direct-to-B2 upload with dedupe (P4), a moderation `flags` table, a beacon-wrapped CTA library (`lib/aof-cta.ts`), and a Stars-based payment rail in TBCC (`loot_lane_economy.py`, `subscriptions.py`) that the monetization playbook explicitly says to extend rather than duplicate. Connect is closer to "clone the `groups/new` + `/upload` + `flags` patterns onto a new `connect_listings` table" than greenfield work — see §3–§5.

Two things are **not** reusable and need new work: (1) a shop/credit system, because nothing today lets a web user spend money and have it reflected as a durable balance — TBCC's Stars economy lives entirely inside Telegram bots today; and (2) a listing ranking formula (fire pin / stealth pin / VIP / auto-bump), because nothing in the repo currently reorders content by paid tier — `score` columns everywhere are engagement-only.

The single biggest open question this report surfaces is **where the credit/wallet balance of record lives** (TBCC Postgres vs. Supabase) — see §12 Q1. Everything in P-C hangs off that answer.

**Site-wide compliance gap found during this audit, independent of Connect:** AOF Hub has **no age gate anywhere** — grepped `app/layout.tsx` and the whole `aof-forum/` tree for `18+`/`AgeGate`/`adult confirm`, zero matches. The existing tube already serves NSFW media with no gate. Connect raises the stakes further because listings expose real people's live contact handles, not just licensed/ingested media. This is called out as a P-A blocker in §8, not a Connect-specific nice-to-have — it should arguably be fixed for the whole hub regardless of whether Connect ships.

Recommended first slice: **P-A (schema + grid + filters + create + report), after Cursor ACK on §12.** See §13.

---

## 1. Feature matrix

Rows are taken verbatim from the task doc's "Report must include §1" checklist (the authoritative source), not reconstructed from browsing the competitor sites — this session did not fetch sextingfinder.com/sextfun.com (doctrine: no competitor scraping). Where a row states *how* the competitor implements something rather than *what* it does, it is marked **inferred** — confirm against the operator's screenshots before building.

| Feature | Status in AOF Hub today | Reuse path | Phase |
|---|---|---|---|
| Browse grid + filters (platform/age/gender/orientation/country/photo/VIP/tags) + sort | **Missing.** `MediaGrid`/`/api/feed` exist for media but have no filter sidebar UI at all — filtering today is tag-page-only (`/t/[slug]`). | Grid: clone `MediaGrid` layout conventions. Filters: new `ConnectFilterSidebar`, no precedent component exists. | P-A |
| Cycling **bulletin** + "last active" | **Missing**, no analog. `media_items`/`groups` have no free-text status field or presence timestamp. | New `bulletin text` + `last_active_at timestamptz` columns on `connect_listings` (§3). | P-A |
| Platform badges (Snapchat/Telegram/etc.) | **Missing**, no analog. | New `platform` enum + badge component, styled off existing `.badge` primitive (`app/globals.css`, already used for tag-kind coloring). | P-A |
| Listing CRUD | **Missing** as a listing concept, but the exact shape exists for `groups`: `app/(site)/groups/new/page.tsx` is a complete, working create-flow (slug validation, server action, RLS-checked insert) — the frontier report flagged this as "the pattern to clone" for galleries, and it is equally the pattern to clone for listings. | Clone `groups/new/page.tsx` → `connect/new/page.tsx`. | P-A (create), P-D (edit/dashboard) |
| Edit limits | **Missing**, no analog for *edit* throttling (upload has *quota* throttling — different shape). | New `lib/connect-limits.ts`, same shape as `lib/upload-limits.ts` (daily-counter check against a `connect_listing_edits` timestamp column or a lightweight audit table). | P-A |
| Captcha | **Missing entirely.** Grepped `aof-forum/` for `captcha`/`turnstile`/`recaptcha`/`hcaptcha` — zero hits anywhere in the repo. This is a new dependency, not a wiring task. | New. Recommend **Cloudflare Turnstile** — free, and Cloudflare is already the operator-confirmed host/CDN (frontier report §11 decision #1), so no new vendor relationship. | P-A |
| Avatar upload | **Reusable almost as-is.** `app/api/upload/presign/route.ts` + `lib/server/finalize-b2-upload.ts` already do presigned-PUT → head-verify → dhash-dedupe → `media_items` insert. A listing avatar is just a `media_items` row referenced by `connect_listings.avatar_media_id`, same as `galleries.cover_media_id`. | Reuse `/api/upload/presign` + `/api/upload/complete` verbatim; UI reuses `UploadPanel` single-file mode. | P-A |
| Ranking: fire pin, stealth pin, top-ups, VIP, auto bump, sort formula | **Missing**, no analog — every `score` column in the schema (`media_items.score`, `galleries.score`, `groups.score`) is engagement-only; nothing today reorders by paid tier. Draft bucket order + weighted formula in §3 ("Ranking / sort formula"); exact competitor mechanics for "stealth pin" (pin without a visible badge — **inferred**, confirm from screenshots) vs "fire pin" (pin + flame badge — **inferred**) need operator confirmation. | New `connect_listings` columns (`fire_pin_until`, `stealth_pin_until`, `auto_bump_until`, `is_vip`, `vip_until`) + a ranking function reusing the decay shape of `0008_reco_functions.sql`. | P-B |
| Shop SKUs → TBCC payment mapping | **Missing as a web concept.** TBCC has SKUs (`loot_lane_economy.py`: `LanePassSkuSpec`, `PackDropSpec`, `MonthlyMegaPackSpec`, `usd_to_stars()`) and a subscriptions API (`backend/app/api/subscriptions.py`), but 100% Telegram-bot-native — no web-initiated purchase path exists anywhere in the repo. | New SKU cards on `/connect/shop` that deep-link (beacon-wrapped, per `lib/aof-cta.ts`) into the payment bot with an order reference in `?start=`; TBCC grants credits, an internal webhook mirrors the balance back to Supabase. Full flow in §7. **Do not build a card processor** — playbook forbids a second shop engine (`MONETIZATION_STACK_PLAYBOOK.md:128`). | P-C |
| Dashboard sidebar (my listings, orders, groups, favorites) | **Partially reusable.** `/u/[handle]` already has an owner-only view with tabs (uploads/galleries, extended in P4 for private uploads). Groups membership exists (`group_members`). Orders and favorites are net-new. | Extend `/u/me`-style dashboard pattern with a `/connect/me` tab set. | P-D |
| Local Swipes (geo) | **Missing**, no analog — no geo columns anywhere in the schema. | **Defer — see §6.** No lat/long anywhere in the schema, it's a doxxing/stalking vector on an 18+ personal-contact directory (materially worse than gallery/media geo would be), and it repeats the exact anti-pattern the frontier report already flagged for Awempire P9: "adding more integrations before proving the simplest funnel works" (`photos_sold=0` finding). | Deferred past P-G |
| Hub integration: ModeStrip tile, nav, SEO landings, sitemap | **Pattern exists, not wired for Connect.** `components/ModeStrip.tsx` is a 4-tile launcher (Live/Tube/Galleries/Upload); `app/sitemap.ts` already gates thin content (pulled `/live` until `liveEmbedsConfigured()`, per the frontier report's P5 implementation log). | Add a 5th tile; gate `/connect/[platform]` SEO routes into the sitemap the same way `/live` is gated — only once listings exist for that platform. | P-A (nav), P-D (SEO landings) |

---

## 2. IA / sitemap

```
/connect                     Browse grid + filter sidebar (default sort: hot)
/connect/new                 Create-listing wizard (auth required) — clone of groups/new pattern
/connect/me                  Dashboard: my listings / orders / favorites / groups link-out
/connect/shop                SKU cards → beacon-wrapped bot deep link (Stars checkout happens in Telegram)
/connect/[id]                Listing detail (numeric bigserial id, e.g. /connect/4821)
/connect/snapchat            SEO landing, platform=snapchat prefilter — gated out of sitemap until it has listings
/connect/telegram            SEO landing, platform=telegram prefilter — same gating
```

**Route-collision constraint:** `/connect/[id]` sits alongside static segments (`/connect/new`, `/connect/me`, `/connect/shop`, `/connect/snapchat`). Next.js App Router resolves static segments before the dynamic `[id]` catch, so this is safe **only if listing ids stay numeric** (`bigserial`, matching every other table in the schema — `media_items.id`, `galleries.id`, `groups.id`). Do not introduce string slugs for listings, or `/connect/snapchat` becomes ambiguous with a listing slug.

**Nav:** add a 5th `ModeStrip` tile ("💌 Connect") next to Live/Tube/Galleries/Upload, and a `LeftNav`/`TopBar` link, following the exact pattern the frontier report's P1 log used for the Live tile (`components/ModeStrip.tsx`, `TopBar.tsx`, `LeftNav.tsx`).

**Sitemap:** `app/sitemap.ts` already caps and gates buckets (tags, galleries, media, groups, and conditionally `/live`). Add a `connect_listings` bucket (public + approved only, capped, sorted by score) and gate each `/connect/[platform]` landing the same way `/live` is gated — present only when `listingsExistForPlatform(platform)` is true, mirroring the `liveEmbedsConfigured()` thin-content fix already shipped (frontier report P5/P1.5 second-pass corrections, item 4).

---

## 3. Schema sketch

Modeled directly on `galleries`/`group_media`/`flags` (junction + counters + RLS), not invented from scratch.

```sql
-- connect_listings: one row per UGC contact listing
create type public.connect_platform as enum ('snapchat', 'telegram', 'instagram', 'other');
create type public.connect_gender as enum ('female', 'male', 'trans', 'couple', 'other');
create type public.connect_orientation as enum ('straight', 'gay', 'lesbian', 'bi', 'other');
create type public.connect_status as enum ('pending', 'approved', 'rejected', 'removed');

create table public.connect_listings (
  id bigserial primary key,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  platform public.connect_platform not null,
  handle text not null,                      -- the Snap/Telegram/etc. username, not a slug
  display_name text,
  age int not null check (age >= 18),
  age_attested boolean not null default false, -- explicit per-listing attestation, distinct from site-wide 18+ gate
  gender public.connect_gender,
  orientation public.connect_orientation,
  country text,                               -- ISO 3166-1 alpha-2
  bio text,
  bulletin text,                              -- short cycling status line
  bulletin_updated_at timestamptz,
  avatar_media_id bigint references public.media_items(id) on delete set null,
  status public.connect_status not null default 'pending',
  is_public boolean not null default false,   -- flips true only after moderation approval
  is_vip boolean not null default false,
  vip_until timestamptz,
  fire_pin_until timestamptz,
  stealth_pin_until timestamptz,
  auto_bump_until timestamptz,                -- scheduled re-bump active through this timestamp (see ranking notes below)
  last_active_at timestamptz not null default now(),
  views_count bigint not null default 0,
  click_count bigint not null default 0,
  score double precision not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index connect_listings_score_idx on public.connect_listings (score desc)
  where status = 'approved' and is_public = true;
create index connect_listings_platform_idx on public.connect_listings (platform, status);
create index connect_listings_country_idx on public.connect_listings (country) where status = 'approved';
create index connect_listings_owner_idx on public.connect_listings (owner_id, created_at desc);
create index connect_listings_handle_trgm_idx on public.connect_listings using gin (handle gin_trgm_ops);
create index connect_listings_pending_idx on public.connect_listings (created_at) where status = 'pending';
-- Same Snap/Telegram handle can't be listed twice on the same platform — blocks impersonation + grid-slot spam.
create unique index connect_listings_platform_handle_uq
  on public.connect_listings (platform, lower(handle))
  where status <> 'removed';

-- durable identity link between a Supabase profile and the TBCC/Telegram user who pays for it.
-- Populated on first confirmed order (§7) — this is the linking mechanism, not just a payment log.
create table public.connect_account_links (
  profile_id uuid primary key references public.profiles(id) on delete cascade,
  telegram_user_id bigint not null unique,
  linked_at timestamptz not null default now(),
  linked_via_order_id bigint references public.connect_orders(id) on delete set null
);

-- reuse the existing tags system for free-form descriptors (not platform/gender/etc., which are columns)
create table public.connect_listing_tags (
  listing_id bigint references public.connect_listings(id) on delete cascade,
  tag_id bigint references public.tags(id) on delete cascade,
  added_by uuid references public.profiles(id) on delete set null,
  added_at timestamptz not null default now(),
  primary key (listing_id, tag_id)
);
create index connect_listing_tags_tag_idx on public.connect_listing_tags (tag_id);

-- favorites: dedicated table, not an extension of `bookmarks` (media-only) or `follows`
-- (follows is polymorphic via a two-column FK already handling 4 target kinds with a check
-- constraint — adding a 5th is possible but the simple pk(user_id, listing_id) shape used by
-- gallery_items/group_media is a closer, lower-risk precedent for "favorite this listing").
create table public.connect_favorites (
  user_id uuid not null references public.profiles(id) on delete cascade,
  listing_id bigint not null references public.connect_listings(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, listing_id)
);
create index connect_favorites_listing_idx on public.connect_favorites (listing_id);

-- orders: web-initiated shop intents. This table is a *request/receipt* record, not the
-- credit ledger of record — see §7 for why the balance lives in TBCC.
create type public.connect_order_status as enum ('pending', 'confirmed', 'failed', 'refunded');

create table public.connect_orders (
  id bigserial primary key,
  user_id uuid not null references public.profiles(id) on delete cascade,
  sku_key text not null,                      -- 'credits_10' | 'vip_30d' | 'fire_pin_24h' | 'stealth_pin_24h' | ...
  usd_amount numeric(10,2) not null,
  stars_amount int,                           -- filled once TBCC quotes it (usd_to_stars())
  tbcc_payment_ref text,                      -- TBCC-side charge/invoice id, set on confirm
  applied_to_listing_id bigint references public.connect_listings(id) on delete set null,
  status public.connect_order_status not null default 'pending',
  created_at timestamptz not null default now(),
  confirmed_at timestamptz
);
create index connect_orders_user_idx on public.connect_orders (user_id, created_at desc);
create index connect_orders_pending_idx on public.connect_orders (status) where status = 'pending';

-- read-only cache of the TBCC-side credit balance, refreshed by the confirm webhook (§7).
-- Never written from a user-authenticated request path.
create table public.connect_wallet_cache (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  credits_balance int not null default 0,
  synced_at timestamptz not null default now()
);
```

**Ranking / sort formula (draft — weights operator-tunable, stealth-pin position inferred):**

1. **Bucket order** (coarse, always wins over score): `fire_pin_until > now()` → top → `stealth_pin_until > now()` (elevated but not flame-badged — **inferred**, confirm from screenshots) → `is_vip and vip_until > now()` → everyone else.
2. **Within a bucket**, sort by `score`, computed as:
   `score = w1 * recency(last_active_at) + w2 * engagement_decay(views_count, click_count) + w3 * bump_recency(last bump timestamp)`
   — `recency()`/`engagement_decay()` follow the same exponential-decay shape as `0008_reco_functions.sql`'s existing feed scoring, not a new statistical model. Default weights `w1=0.5, w2=0.3, w3=0.2`, operator-tunable per §12 Q4.
3. **Free listings with no pin/VIP/bump activity** sort by `score` alone (recency + engagement, no bump term) — this is the bucket that "auto bump" (below) exists to let a paying user climb out of.

**Per-owner listing cap:** P-A default is **one active (non-removed) listing per `owner_id`** — enforced app-side (a count check in the create route, same shape as `checkUploadQuota()`), not a schema constraint, so it can be raised without a migration. This is also the free-tier boundary `studio_slot` (P-G) sells past — sharpens §12 Q5 into "what's the studio cap," not "should there be one at all."

**"Auto bump" vs. "auto top-up" — two different features, both named in the task doc, easy to conflate:**
- **Auto bump** (task item 1, matrix row "ranking … auto bump"): a **listing** feature — a scheduled re-bump that refreshes `last_active_at` (and thus the `bump_recency` term above) on a timer without the owner manually clicking. SKU: `auto_bump_7d` (§7), applies a `connect_listings.auto_bump_until timestamptz` column (add to the P-A/P-B migration) that a scheduled job checks to re-bump on a cadence (e.g. every 12h) until it expires.
- **Auto top-up** (`auto_topup_toggle`, §7, P-G): a **wallet** feature — recurring credit refill so the user doesn't run out of spendable credits. Requires TBCC-side recurring-charge support; confirm that exists before promising the SKU.

**Existing migration that must change:** `supabase/migrations/0010_flags.sql:7` constrains `target_kind` to `('media', 'gallery', 'group', 'thread', 'post')`. Listing reports (P-A) require adding `'connect_listing'` to that CHECK — this is a real migration, not just a new "Report" button; `app/api/report/route.ts:8`'s Zod enum needs the same addition.

**RLS (pattern: `galleries`/`flags`):**
- `connect_listings`: `select` where `status='approved' and is_public=true`, or `owner_id=auth.uid()`. `insert` with check `owner_id=auth.uid()`. `update` using `owner_id=auth.uid()` — but **exclude** `status`, `is_vip`, `*_until`, `score` from client-writable columns (enforce via a trigger or a narrower `update` policy + column-level grants, not just RLS, since RLS alone doesn't restrict *which* columns a permitted `update` touches).
- `connect_listing_tags`: mirrors `media_tags` (`select using true`, `insert with check auth.uid() is not null`).
- `connect_favorites`: `all using/with check user_id = auth.uid()`, mirrors `bookmarks_self`.
- `connect_orders`: `select using user_id = auth.uid()` only. **No client-side insert/update policy** — orders are created and confirmed exclusively by server-side routes running under the service role (prevents a user from crafting `status='confirmed'` or an arbitrary `credits_delta` themselves — this is the same class of gap the frontier report flagged for `from-telegram.ts`'s header mismatch: authenticated cross-system writes need the gate designed in from day one, not patched in after).
- `connect_wallet_cache`: `select using user_id = auth.uid()`; writes service-role only.

---

## 4. API routes

| Route | Method | Purpose | Phase |
|---|---|---|---|
| `/api/connect/feed` | GET | Filtered/sorted/paginated grid query | P-A |
| `/api/connect/listings` | POST | Create listing (captcha-verified, `status='pending'`) | P-A |
| `/api/connect/listings/[id]` | GET | Listing detail | P-A |
| `/api/connect/listings/[id]` | PATCH | Edit own listing, rate-limited via `lib/connect-limits.ts` | P-A |
| `/api/connect/listings/[id]/bump` | POST | Free manual bump (resets `last_active_at`), cooldown-limited via `lib/connect-limits.ts` (e.g. once per 4h) — not credit-consuming in v1; a paid `auto_bump_7d` SKU is a P-C add, not a P-A prerequisite | P-A |
| `app/api/report/route.ts` (extend) | POST | Add `connect_listing` to the existing `targetKind` Zod enum + `flags.target_kind` CHECK — **not a new route**, extends the file that already exists | P-A |
| `/api/connect/favorites` | POST/DELETE | Toggle favorite | P-D |
| `/api/connect/me` | GET | Dashboard payload: my listings, orders, favorites | P-D |
| `/api/connect/shop/skus` | GET | Static SKU catalog (mirrors `loot_lane_economy.py` pricing, not a live TBCC call in v1) | P-C |
| `/api/connect/shop/checkout` | POST | Creates `connect_orders` row (`status='pending'`), returns beacon-wrapped `t.me` deep link carrying the order id in `?start=` | P-C |
| `/api/connect/internal/payment-confirmed` | POST | **TBCC → aof-forum webhook**, `X-TBCC-Internal-Key` required, marks order confirmed, applies credits/VIP/pin to the listing, refreshes `connect_wallet_cache` | P-C |
| `/api/connect/admin/queue` | GET/POST | Moderation queue: list pending, approve/reject — reuses the `profiles.is_admin` check already used by `flags_read_admin` | P-A |

**Auth header discipline:** the frontier report's §1 finding — `from-telegram.ts` sent `X-Internal-Key` while every real backend consumer expects `X-TBCC-Internal-Key` — must not repeat here. The payment-confirmed webhook is a new authenticated cross-system route from day one; build it with `X-TBCC-Internal-Key` and confirm it's excluded from `internal_api_auth.py`'s `_PUBLIC_GET_PREFIXES`-style public allowlist (it's a POST, but the same "public by default" trap that bit `/media/` GETs is worth checking explicitly against whatever prefix logic exists for POST routes before this ships).

---

## 5. UI components

| Component | Notes |
|---|---|
| `ConnectFilterSidebar` | Platform/age-range/gender/orientation/country/has-photo/VIP checkboxes + tag multiselect. No existing precedent — net new. |
| `ConnectListingCard` | Avatar, handle, platform badge, bulletin snippet, "last active", fire/VIP badges. Styled off existing `.card`/`.badge` primitives (`app/globals.css`), same reuse move the frontier report made for `.mode-strip`. |
| `ConnectGrid` | Paginated grid wrapper, same layout conventions as `MediaGrid`. |
| `ConnectListingForm` | Create/edit form. Avatar field reuses `UploadPanel` in single-file mode → `/api/upload/presign` + `/api/upload/complete`. Includes age input + attestation checkbox + Turnstile widget. |
| `ConnectDashboard` | Tabs: My Listings / Orders / Favorites / Groups (link-out to existing `/groups`). |
| `ConnectShopPanel` | SKU cards, beacon-wrapped CTA buttons via `lib/aof-cta.ts`'s `contextualCtas()` pattern extended with a `surface: "connect_shop"` case. |
| `ConnectReportButton` | Thin wrapper around the existing `ReportButton.tsx`, parameterized `targetKind="connect_listing"`. |
| `TurnstileWidget` | New — first captcha in the repo. Site/secret key env vars, server-side verify in `/api/connect/listings` POST handler. |

---

## 6. Local Swipes — explicit defer

Not specced beyond this paragraph. Three grounded reasons: (1) no geo column exists anywhere in the schema today — this is greenfield infra, not a filter add; (2) it is a materially worse doxxing/stalking vector than any existing AOF Hub surface, since Connect listings already expose a live external contact handle tied to a self-reported location — precise or coarse geo compounds that risk on real people, not licensed media; (3) it repeats the exact anti-pattern the frontier report already flagged for Awempire's Video Promotion API (P9): adding a second high-risk integration before the first, simpler funnel (P-A/P-C: does anyone create a listing, does anyone buy a top-up) is proven. Revisit only after P-C's conversion data exists.

---

## 7. Monetization wiring to TBCC

Per `MONETIZATION_STACK_PLAYBOOK.md:128`: *"Don't build: Second parallel shop engine — extend `subscription_plans` + `loot` API instead."* Combined with the standing doctrine "Telegram owns conversion," Connect's shop is a **quote-and-redirect** flow, not a web payment form:

1. User picks a SKU on `/connect/shop` → `POST /api/connect/shop/checkout` creates a `connect_orders` row (`status='pending'`) and returns a beacon-wrapped deep link: `t.me/aof_payment_bot?start=connect_order_<id>` (beacon via `lib/aof-cta.ts`'s existing `sourceRef`/`botHref` machinery, extended with a `connect_shop` surface).
2. User completes the purchase **inside Telegram** — TBCC's existing Stars flow (`usd_to_stars()` in `loot_lane_economy.py:118`, `subscriptions.py`'s `create_subscription`) handles pricing and payment exactly as it does today for loot/VIP/packs. No new payment code in TBCC beyond recognizing the `connect_order_<id>` start-param and validating it against `POST /api/connect/internal/payment-confirmed`.
3. On confirmation, TBCC calls the aof-forum webhook (`X-TBCC-Internal-Key`) → marks the order confirmed, applies the SKU's effect (credit delta, VIP flag + expiry, fire/stealth pin expiry) to the listing or wallet cache. **This confirm call is also the identity-linking mechanism**, not just the payment mechanism: the webhook payload carries the TBCC/Telegram user id that completed the Stars charge, and on first confirmation for a given `profile_id` the handler upserts a `connect_account_links` row (§3) tying the web account to the Telegram user permanently. Without this, `auto_topup_toggle`, any VIP granted organically from inside a bot, and cross-system refund/support lookups have no way to resolve which web listing(s) a Telegram user's payment applies to.
4. `/connect/me` and listing ranking read from Supabase (`connect_wallet_cache`, `connect_listings.is_vip`/`*_until`) — never call TBCC live on the read path, matching the "cache hot-path reads off Telegram I/O" lesson already learned the hard way (`tbcc-telegram-io-serialized` memory: the global Telegram lock is the documented root cause of a prior "Could not load pools" timeout — the same discipline applies here even though this path doesn't touch Telegram I/O directly, because it's the same "don't make user-facing reads block on a slower system" principle).

**Where the credit balance of record lives** is the load-bearing decision (§12 Q1) that this whole flow depends on — recommended answer: **TBCC Postgres**, because payment, refunds, and support tooling already live there, with `connect_wallet_cache` in Supabase as a denormalized read-mirror for ranking/display only, refreshed by the same webhook. The alternative (Supabase as source of truth) would mean building refund/dispute handling twice.

**SKU catalog (draft, USD, convert via `usd_to_stars()`):**

| SKU key | What it does | Notes |
|---|---|---|
| `credits_10` / `credits_50` / `credits_200` | Top-up credit packs | Spent on pins/bumps below |
| `vip_30d` | 30-day VIP badge + ranking boost | Mirrors `LanePassSkuSpec` pricing shape |
| `fire_pin_24h` | 24h top-of-feed pin + flame badge | Consumes credits or direct Stars purchase |
| `stealth_pin_24h` | 24h elevated sort weight, no visible badge (**inferred mechanic — confirm from screenshots**) | Same |
| `auto_bump_7d` | 7 days of scheduled re-bumps (sets `auto_bump_until`, a job re-touches `last_active_at` on a cadence) | **Listing** feature — distinct from `auto_topup_toggle` below, see ranking notes in §3 |
| `auto_topup_toggle` | Recurring credit refill so the wallet doesn't run dry | **Wallet** feature, P-G. Requires TBCC-side recurring charge support and the `connect_account_links` identity row (§3/§7) to know which Telegram user to charge — confirm recurring-charge support exists before promising this SKU |
| `studio_slot` | Multi-listing management for studios/agencies | P-G, deferred — no multi-listing-per-owner concept in the P-A schema yet |

---

## 8. Compliance checklist

- **Site-wide 18+ gate — currently missing, blocking.** No age-gate component exists anywhere in `aof-forum/` (verified by grep, zero hits). Connect cannot ship without one; recommend fixing this at the hub level (interstitial or persistent cookie-gated splash) rather than a Connect-only gate, since the tube already needs it too.
- **Per-listing age attestation**, distinct from the site gate: `age int not null check (age >= 18)` at the schema level (hard floor) plus a required `age_attested boolean` checkbox at creation time — a schema constraint alone doesn't capture "the creator affirmed this," which matters for moderation/legal review.
- **2257-adjacent posture:** Connect listings are UGC contact directories, not hosted/produced content — but they do carry a photo + claimed age. Moderation queue (`status='pending'` default, admin-only approve) is the control; document that Connect does not host explicit media of the listed person beyond the avatar, and any explicit content stays on the platform being advertised (Snap/Telegram), not on AOF.
- **Snap/Telegram platform disclaimers**, mirroring the Live page's existing Awempire disclaimer pattern (`AwempireDisclaimer` component, frontier report P5 log) — "Connect listings link out to third-party platforms not operated by AOF."
- **AUP risk:** the frontier report already flagged that Vercel/Cloudflare Pages have shifting adult-content AUPs (operator ACK'd Cloudflare + private B2 for the hub generally); Connect doesn't change that decision but raises the stakes if the host's AUP distinguishes "adult media hosting" from "adult contact/dating directory" — worth a direct question to Cloudflare's ToS team before P-A ships publicly, not assumed clear because the general hub AUP was already cleared.
- **Moderation queue is P-A, not a later phase** — every listing defaults `status='pending', is_public=false` until an admin approves it. This mirrors the P4 decision to default uploads `is_public=false` until attached to a public gallery (frontier report operator ACK #5).
- **Report flow ships with P-A**, not bolted on later — extends the existing `flags` table/`app/api/report/route.ts` rather than building a parallel moderation surface.

---

## 9. Anti-patterns

- **Shop before grid.** Building `/connect/shop` before `/connect` has real listings to rank means there's nothing to spend a fire pin on — sequence per §10, P-C strictly after P-A/P-B.
- **Competing with the bots.** Connect's job is to be a discovery surface that funnels to Telegram, not a second monetization product — every shop SKU either boosts a listing's visibility or grants a Telegram-side benefit; it must never become an independent revenue stream disconnected from the owned-bot economy (playbook's core doctrine).
- **Hosting DMs / becoming a messaging product.** Connect lists a handle; it does not add in-app messaging, chat, or media exchange. That would turn a discovery directory into a hosted adult chat platform — a different, much higher compliance/liability tier the task doc's scope doesn't ask for and this report doesn't recommend.
- **Building a second payment engine.** Flagged twice already (§7) because it's the single easiest way to accidentally violate the playbook's explicit "don't" — any web-native Stripe/card-processor temptation for `/connect/shop` should be treated as an immediate stop-and-ask, not a convenience shortcut.
- **Geo before the funnel is proven.** Local Swipes deferred per §6 — do not let "SextingFinder has it" pull it forward ahead of proving P-A/P-C convert.
- **Client-writable ranking fields.** `is_vip`, `fire_pin_until`, `score`, and order `status` must never be reachable from a user-authenticated `update`/`insert` — this is the same class of gap (unauthenticated/under-authenticated cross-system write) the frontier report found and fixed for `from-telegram.ts`. Design the RLS/webhook boundary in from P-A, not after a exploit report.

---

## 10. Phased build (P-A … P-G)

| Phase | Scope | Effort | Files (new/changed) | Env | Tests | Verify |
|---|---|---|---|---|---|---|
| **P-A** | Schema + grid + filters + create + report (MVP) | **L** | `supabase/migrations/0011_connect.sql` (listings/tags/favorites-table-only, no orders yet), `0010_flags.sql`-equivalent CHECK migration, `app/(site)/connect/page.tsx`, `connect/new/page.tsx`, `connect/[id]/page.tsx`, `components/Connect*`, `app/api/connect/{feed,listings,report}/route.ts`, `app/api/connect/admin/queue/route.ts`, `lib/connect-limits.ts`, `TurnstileWidget`, site-wide age-gate component | `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | RLS policy tests (own vs public vs pending), edit-limit unit test, captcha-fail rejection test | Create a listing → shows `pending` → admin approves → appears in `/connect` grid filtered by platform |
| **P-B** | Ranking + VIP (admin grant first, no purchase flow yet) | **M** | `connect_listings` ranking columns already in P-A schema; new scoring function (`0012_connect_ranking.sql`), admin-only "grant VIP" action in queue UI | — | Ranking function unit test (fire pin > VIP > score) | Admin-grants VIP to a test listing, confirms it sorts above non-VIP at equal engagement |
| **P-C** | Shop + credits + fire pin + TBCC pay | **L**, **highest-risk phase** | `connect_orders`, `connect_wallet_cache` migrations, `/connect/shop`, `ConnectShopPanel`, `/api/connect/shop/checkout`, `/api/connect/internal/payment-confirmed`, TBCC-side: recognize `connect_order_<id>` start-param, call the webhook on confirm | `TBCC_INTERNAL_API_KEY` (shared, already exists per P2 log), `NEXT_PUBLIC_BEACON_SLUG_CONNECT_SHOP` | Order lifecycle test (pending→confirmed→applied), webhook auth-rejection test (missing/wrong key) | Buy a test SKU end-to-end in a sandbox/dev bot, confirm listing gets fire-pinned and wallet cache updates |
| **P-D** | Favorites + SEO landings + dashboard polish | **M** | `connect_favorites` migration, `/connect/me`, `/api/connect/favorites`, `/api/connect/me`, `/connect/[platform]` SEO routes + `generateMetadata`, sitemap gating | — | Favorite toggle test, sitemap gate test (empty platform excluded) | Favorite a listing, see it on `/connect/me`; `/connect/snapchat` absent from sitemap until it has ≥1 approved listing |
| **P-E** | Groups tie-in | **S** | Link Connect listings to existing `groups` (e.g. "listings from members of this group"), no schema change if done as a query join on `group_members` | — | Query test | Group page shows a "Connect listings from members" rail |
| **P-F** | Local swipes (geo) | **L, high risk — deferred** | Not specced (§6) | — | — | — |
| **P-G** | Studio / auto top-up | **M** | Multi-listing ownership model (studio account owns N listings), `auto_topup_toggle` SKU wired to a recurring TBCC charge | — | — | — |

---

## 11. Operator vs agent split

| Work | Owner |
|---|---|
| P-A schema/grid/filters/create/report, P-B ranking function, P-D favorites/SEO/dashboard, P-E groups tie-in | **Agent** — standard code against an existing, well-understood codebase, same split the frontier report used |
| Turnstile account creation + site/secret keys | **Operator** — third-party account the agent cannot create |
| Site-wide 18+ age gate — build vs launch-blocking priority call | **Operator** — product/compliance decision, not purely technical |
| P-C TBCC-side changes (recognizing `connect_order_<id>` start-param, calling the webhook) | **Agent**, but gated on operator answering §12 Q1 (ledger location) first |
| Cloudflare AUP confirmation for a "contact directory" (not just adult media) product surface | **Operator** — legal/ToS confirmation, mirrors the frontier report's unresolved NSFW-hosting flag |
| Studio/multi-listing account model (P-G) scope decision | **Operator** — §12 Q5 |
| Island deploy of any new backend routes (payment-confirmed webhook, subscription start-param handling) | **Operator** — per standing doctrine, agent does not deploy to the island unprompted |

## 12. Open questions (5, hard cap)

1. **Where does the credit/wallet balance of record live — TBCC Postgres or Supabase?** This report recommends TBCC (payment/refund/support tooling already lives there), with a Supabase read-cache for ranking. Confirm or override before P-C schema is finalized — this is the single most load-bearing decision in the plan.
2. **Site-wide 18+ age gate: build it as part of Connect P-A, or as a separate, faster hub-wide fix first?** The gap exists today independent of Connect; Connect just makes it more urgent (real contact handles, not just media).
3. **Captcha vendor: Cloudflare Turnstile (this report's recommendation, free, matches the existing Cloudflare host decision) vs. another provider?**
4. **"Stealth pin" exact mechanic** — pin without a badge, or something else (higher position but excluded from "featured" rail, different sort tie-break, etc.)? Marked inferred throughout this report; needs the operator's screenshots to confirm before P-B's ranking function is built.
5. **Studio/multi-listing accounts (P-G) — in scope for v1 at all, or defer indefinitely?** Affects whether `owner_id` should be uuid-single-owner (this report's P-A default) or designed for multi-owner from the start, which is materially harder to retrofit than to add later if the answer is "not yet."

---

## 13. Recommended first slice

**P-A**, after Cursor ACK on §12. Rationale: P-A is pure extension of already-proven patterns (`groups/new` clone, `flags` extension, upload-presign reuse) with one genuinely new dependency (captcha) and one compliance blocker (site-wide age gate) that should be fixed regardless of Connect. It produces a working, moderated, filterable directory with zero payment-system risk — P-B/P-C can wait for real usage signal before the harder ranking-formula and money-movement work begins, consistent with the "prove the simple funnel first" doctrine this report leaned on twice (§6, §9).

---

## 14. Risks

- **Compliance exposure is the dominant risk**, not engineering complexity — a UGC directory of real people's live contact handles + photos + claimed age is a materially different liability surface than a licensed/ingested media tube, even though the codebase reuse is high. Do not let the high code-reuse score understate the compliance review this needs before public launch.
- **Credit-ledger split-brain** if P-C ships with Supabase and TBCC both able to write balance state — mitigated by the "TBCC is the ledger, Supabase is a cache" design in §7, but only if that design is actually enforced (RLS blocking client writes to `connect_orders`/`connect_wallet_cache`, confirmed in P-A's RLS test suite even though those tables don't exist until P-C — i.e., write the RLS pattern once, correctly, don't patch it in after a bug report).
- **Ranking formula becomes a second monetization surface** if not tightly scoped to "boost visibility only" — see anti-patterns §9.
- **Turnstile is a new operational dependency** (site/secret keys, uptime) — low risk given Cloudflare is already the host, but not zero.

---

## Files read (this session)

- `tbcc/docs/handoffs/2026-08-10_aof-hub-frontier-plan-ask_report.md` (full)
- `aof-forum/README.md` (full)
- `aof-forum/supabase/migrations/0001_init.sql`, `0002_galleries.sql`, `0004_groups.sql`, `0005_engagement.sql`, `0007_rls.sql`, `0010_flags.sql`
- `aof-forum/components/ModeStrip.tsx`, `lib/aof-cta.ts`
- `aof-forum/app/(site)/groups/new/page.tsx`
- `aof-forum/lib/upload-limits.ts`
- `aof-forum/app/api/report/route.ts`
- `aof-forum/app/api/upload/presign/route.ts`
- `tbcc/docs/MONETIZATION_STACK_PLAYBOOK.md` (full)
- `tbcc/backend/app/data/aof_network.py` (structure scan)
- `tbcc/backend/app/data/loot_lane_economy.py` (structure scan — `usd_to_stars`, SKU specs)
- `tbcc/backend/app/api/subscriptions.py` (structure scan)
- `tbcc/backend/app/models/promo_affiliate_link.py` (structure scan)
- `tbcc/backend/app/middleware/internal_api_auth.py` (grep — `_PUBLIC_GET_PREFIXES`, `X-TBCC-Internal-Key`)
- Grep-only checks: no `*connect*` handoff doc pre-existing; no captcha/turnstile/age-gate code anywhere in `aof-forum/`

**Not fetched:** sextingfinder.com / sextfun.com — doctrine forbids competitor scraping. The feature matrix (§1) is sourced from the task doc's own enumerated checklist, with competitor-specific mechanics explicitly marked **inferred** pending the operator's screenshot review.

---

**STOP — awaiting Cursor ACK on §12 before any implementation.**
