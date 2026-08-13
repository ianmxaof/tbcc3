# AOF Connect — SextingFinder parity plan (Claude Code handoff)

Forward prompt for Claude Code. Reverse report: `tbcc/docs/handoffs/2026-08-10_aof-connect-sextingfinder-parity-plan_report.md`

**Lane:** Plan/Ask first (Frontier judgment) — **no implementation** until Cursor ACKs the plan report.

---

## Operator blocker (auth) — not part of CC scope but operator must fix

Supabase **"email rate limit exceeded"** = project auth email quota hit (default ~4/hr on free tier when using built-in SMTP).

**Fix (pick one):**
1. Wait 60 minutes, then retry once.
2. Supabase Dashboard → **Authentication → Rate Limits** — review/signup/email limits (adjust if plan allows).
3. **Authentication → SMTP Settings** — configure custom SMTP (Resend, SendGrid, etc.) for dev; raises practical limits.
4. Use a **different test email** domain if one address is throttled.
5. For local-only dev bypass (optional): create test user in Supabase **Authentication → Users → Add user** with password, add password sign-in route — only for localhost, never prod.

Auth code fixes already in repo: client-side `SignInForm`, `/auth/callback` PKCE + `token_hash`. Ensure redirect URLs include `http://localhost:3001/auth/callback` and `http://127.0.0.1:3001/auth/callback`.

---

## Quota reminder

Run `/usage` in Claude Code. This pass is **read-heavy** (product + schema design). Do not implement until plan ACK.

## Lane note

This is **Frontier Plan/Ask** (revenue model + UGC moderation + multi-system). Claude Code writes the plan report only. Implementation phases belong in Cursor Auto or Lane C **after** ACK, split by phase (schema → grid → shop).

---

## Handoff block (paste into Claude Code)

```
# AOF Connect — SextingFinder / SextFun parity plan (Plan/Ask only)

## Goal

Produce a full product + technical plan to add an owned **Connect** community directory to AOF Hub (`aof-forum/`) with feature parity to sextingfinder.com / sextfun.com-style services — **plan only, no code commits**.

Done when `tbcc/docs/handoffs/2026-08-10_aof-connect-sextingfinder-parity-plan_report.md` exists with: feature matrix, schema, IA, phased build (P-A…P-N), monetization wiring to TBCC, compliance checklist, operator vs agent split, and recommended first implementation slice.

## Context (zero prior chat — read these)

1. `tbcc/docs/handoffs/2026-08-10_aof-hub-frontier-plan-ask_report.md` — hub doctrine, phases P0–P10
2. `aof-forum/README.md` — stack, local dev
3. `aof-forum/supabase/migrations/` — existing `profiles`, `tags`, `groups`, `forum_*`, `flags` (0010)
4. `aof-forum/app/(site)/` — existing routes (tube, live, galleries, groups, forum)
5. `aof-forum/components/ModeStrip.tsx`, `lib/aof-cta.ts` — hub modes + Telegram conversion
6. `tbcc/docs/MONETIZATION_STACK_PLAYBOOK.md` — beacons, gates, bots
7. `tbcc/backend/app/data/aof_network.py` — live bot URLs (loot, VIP, spicy)
8. Reference competitor UX (operator screenshots + public pages):
   - Browse grid: sextingfinder.com/snapchat-usernames — filters (age, gender, orientation, country, has picture, VIP, tags), card grid (photo, bulletin, username, demographics, last active)
   - Add listing: platform dropdown (Snapchat/Telegram/Kik…), username, age/gender/orientation, bio, tags (cap ~15), paid-content checkbox, captcha
   - Dashboard: My Usernames, Add Username, Local Swipes, Favorites, Buy Top-Up, VIP Promotion, Create Group, Orders, Account Settings
   - Shop: top-up packs (20/50/100), VIP, Fire Pin, Stealth Fire Pin, Auto Top-Up, Studio Account
   - Local Swipes: geo discovery landing
   - Nav: Sexting, Telegram, Kik, Nudes, Local Swipes, Shop, LIVE CAMS

## Product vision (operator)

Active community where users create **listings** (Snapchat/Telegram handles + photo + short **bulletin**). Main page shows a **cycling/ranked bulletin feed** with rich filters. Monetization: VIP badge, top-up credits, fire pins (bump to top), stealth pins, auto top-up, studio tier. Groups optional. Must funnel to **owned Telegram bots** (loot, VIP, companion) as primary revenue — not only external Snap adds.

## Doctrine (non-negotiable)

- Telegram owns conversion — every listing card should offer owned-bot CTAs (beacon-wrapped via `NEXT_PUBLIC_TBCC_BEACON_BASE` + `api.powercore.app/r/…`)
- Listings are **UGC contact directories** — not hosted cam streams (Live stays Awempire `/live`)
- 18+ only; moderation required from day one (extend `flags` table pattern)
- No scraping competitor sites at scale
- Plan must call out Snap Inc. / Telegram ToS affiliate disclaimers
- Do not commit `.env`, secrets, or session files

## Existing AOF Hub assets to extend (do not reinvent)

| Asset | Reuse for Connect |
|-------|-------------------|
| `profiles` | Account owner; link 1 user → N listings |
| `tags` | Listing tags (may need `listing_tags` junction or separate tag namespace) |
| `groups` | Optional: user-created Telegram groups (already have groups schema) |
| `flags` + `ReportButton` | Report listing / user |
| `UploadPanel` / B2 | Listing avatar image |
| `ModeStrip` | Add **Connect** tile |
| `gate_funnel` / web beacons | Attribute listing → bot clicks |

## Competitor feature matrix (required in report)

For each feature below, mark: **built / partial / missing** in aof-forum today, and **phase** to ship.

### Browse & discovery
- Filterable card grid (platform, age range, gender, orientation, country, has photo, VIP, tags)
- Sort: last active, bumped, VIP first
- Bulletin text on card (status line)
- “Active X ago” / last_seen
- Platform badge (Snap / Telegram / Kik)
- Paid / VIP visual badge on card
- Refresh control
- SEO landing pages per platform (`/connect/snapchat`, `/connect/telegram`) — mirror sextingfinder URL pattern

### Listing CRUD
- Add listing wizard (platform, external username, demographics, bio, tags, paid flag)
- Edit limits (e.g. 2 edits / 24h non-VIP)
- Avatar upload (1 image)
- hCaptcha or Turnstile on create
- My Listings dashboard
- Delete / pause listing

### Ranking & bulletin cycling
- Fire Pin — bump to top of feed for N hours
- Stealth Fire Pin — bump without obvious pin badge (competitor feature — plan ethics + disclosure)
- Top-up credit — spend 1 credit per bump
- VIP — permanent badge + higher sort weight + relaxed edit limits
- Auto top-up — scheduled bumps (studio tier)
- Algorithm: document sort key formula (bumped_at, vip_weight, last_active, created_at)

### Monetization / shop
- Credit packs (20/50/100 top-ups) — map to TBCC payment (Stars, crypto, Gumroad keys) or new SKUs
- VIP subscription / promotion
- Fire pin / stealth pin SKUs
- Studio / agency multi-listing account
- Orders tab + private key redemption flow (competitor pattern) — plan TBCC equivalent
- Integrate with existing `api.powercore.app` beacons for attribution

### Social / groups
- User-created groups (Telegram invite links)
- Favorite listings / swipes
- Local Swipes (geo) — plan privacy model (coarse geo only, no exact GPS storage)

### Account
- Dashboard nav matching competitor sidebar
- Account settings
- NO VIP / NO TOP-UPS status badges on dashboard

### Compliance & trust
- 18+ interstitial on `/connect`
- AUP, DMCA, 2257 notes (operator legal pages)
- Moderation queue (admin)
- Rate limits on create/listing spam
- Email auth (Supabase) — note operator rate-limit gotcha

### Hub integration
- Mode strip tile + nav link
- Cross-links: tube tags → connect listings? performer bridge?
- Telegram conversion footer on listing detail pages
- Sitemap/SEO for public listing pages (when approved)

## Technical deliverables (report sections)

### 1. Current-state audit
- What aof-forum already has vs competitor (file evidence)
- What blocks local dev today (auth rate limit, B2 keys, migrations)

### 2. Recommended IA (sitemap)
```
/connect                    — main bulletin grid (default sort)
/connect/snapchat           — platform-filtered SEO landings
/connect/telegram
/connect/new                — add listing (auth)
/connect/me                 — dashboard
/connect/me/listings
/connect/shop               — boosts / VIP (phase B+)
/connect/[id]               — listing detail
/connect/groups             — optional reuse of /groups or alias
```
Propose URL scheme; justify vs nesting under `/g` or `/u`.

### 3. Data model (SQL sketch — no migration file yet)
Proposed tables at minimum:
- `connect_listings` (owner_id, platform enum, external_handle, bulletin, age, gender, orientation, country, avatar_b2_key, is_vip, is_paid_content, last_active_at, bumped_at, fire_pin_expires_at, is_paused, created_at…)
- `connect_listing_tags` (listing_id, tag text or tag_id)
- `connect_credits` or reuse TBCC ledger for top-ups
- `connect_orders` / bumps log
- `connect_favorites` (user_id, listing_id)
- RLS policies sketch
- Indexes for filter queries (platform, gender, age, tags GIN, sort columns)

### 4. API / Next.js routes sketch
- `GET /api/connect/feed` — filtered paginated grid
- `POST /api/connect/listings` — create (auth)
- `PATCH /api/connect/listings/[id]` — edit with rate limit
- `POST /api/connect/listings/[id]/bump` — spend credit / fire pin
- Admin: `GET /api/connect/moderation` (admin only)

### 5. UI component list
- `ConnectFilterSidebar` (competitor left filters)
- `ConnectListingCard` (photo, bulletin, badges, active time)
- `ConnectListingForm` (add/edit)
- `ConnectDashboard` (sidebar nav like screenshots)
- `ConnectShop` (product grid)
- Extend `ModeStrip` + `TopBar` + `LeftNav`

### 6. Monetization plan
- Map each shop SKU to TBCC: payment bot Stars, crypto, companion credits pattern, or Gumroad private keys
- Beacon slugs: `web-connect-listing`, `web-connect-vip`, etc.
- Revenue attribution via `gate_funnel` / `expects_touch` (bare t.me vs ?start=)

### 7. Phased implementation (numbered, independently shippable)

Minimum phases (expand with effort S/M/L and file lists):

| Phase | Scope | Effort |
|-------|-------|--------|
| **P-A** | Schema + RLS + migration; `/connect` grid + basic filters; create listing; report | M |
| **P-B** | Ranking (bumped_at), last_active, VIP flag (manual admin grant first) | M |
| **P-C** | Shop + credits + fire pin + orders (TBCC payment integration) | L |
| **P-D** | Favorites, platform SEO landings, dashboard polish | M |
| **P-E** | Groups integration / create group from listing | M |
| **P-F** | Local Swipes (geo) — only if compliance section approves | L |
| **P-G** | Studio / auto top-up / multi-listing automation | L |

For each phase: files to touch, env vars, tests, operator steps, rollback, verify command.

### 8. Compliance & risk
- 18+ gate, moderation, CSAM reporting path, paid content rules
- Competitor disclaimer patterns
- Why Local Swipes is high-risk (defer default)

### 9. Anti-patterns
- Building full shop before grid works
- Hosting Snap DMs on-site
- Competing with Telegram bots instead of funneling to them
- Copying competitor pricing without TBCC cost model

### 10. Agent vs operator split

### 11. Open questions for operator (max 5)

### 12. Recommended first slice after plan ACK
Suggest: **P-A only** — schema + `/connect` grid + create listing + flags, no shop.

## Out of scope (this pass)

- Writing migrations or React components (plan only)
- Island deploy, live bots, Telethon
- Awempire / live cam changes
- Scraping sextingfinder.com
- Fixing Supabase email rate limits (operator)

## Verification (plan pass only)

Done = report file exists with all sections above + feature matrix + phased plan + schema sketch.

No `tsc`, no `pytest` — documentation only.

## Working agreement

- Branch: plan-only — **no code commits** unless operator later says "implement P-A"
- Write report to `tbcc/docs/handoffs/2026-08-10_aof-connect-sextingfinder-parity-plan_report.md`
- **STOP** after report for Cursor ACK via `/cc-report`
- Implementation: separate handoff per phase after ACK

## Reverse report structure

# Reverse handoff — AOF Connect SextingFinder parity plan
- Status: complete | blocked | needs operator input
- Executive summary (≤12 bullets)
- Competitor feature matrix (built/partial/missing)
- IA + wireframe (ASCII)
- Schema sketch (SQL)
- API routes
- Phased plan P-A…P-G with file lists
- Monetization → TBCC mapping
- Compliance checklist
- Operator decisions needed (numbered)
- Recommended first implementation slice
- Risks / anti-patterns
- Files read (list)
```
