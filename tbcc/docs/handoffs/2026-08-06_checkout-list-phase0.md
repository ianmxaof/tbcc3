# The Checkout List — Phase 0 runbook

**Created:** 2026-08-06  
**Status:** operator setup (no TBCC automation yet)

## Channel record

| Field | Value |
|-------|--------|
| **Title** | The Checkout List |
| **Public link** | https://t.me/thecheckoutlist |
| **Channel ID** | `-1004361597444` |
| **Owner account** | `@powercoreai` (secondary; channel brand stays neutral) |
| **Purpose** | SFW-only affiliate / deals silo — Temu, Revolut, Cursor, Proton, infra |
| **TBCC env (Phase 1)** | `TBCC_CHECKOUT_LIST_CHANNEL_IDENT=-1004361597444` |

## Phase 0 checklist

- [x] **Channel description** — paste from § Description below
- [x] **Channel photo** — simple cart/checkmark icon (no AOF / adult imagery)
- [x] **Post + pin** message 1 — § Pinned welcome (guide + disclosure)
- [x] **Post** message 2 — § Launch bulletin (deals list)
- [x] **Add admin:** `@aof_secretary_bot` — post messages (for Phase 1 automation)
- [ ] **Optional contact:** `@aof_secretary_bot` or leave contact empty until Phase 1
- [ ] **Do not** add to AOF addlist, Loot Room, or @aofmainhub yet
- [ ] **Collect missing URLs:** Temu, Revolut, Proton (paste into bulletin when ready)
- [ ] **Mute** channel on owner account if you don’t want notif noise

## Channel description (Telegram → Manage → Edit)

```
Curated deals & referral links — shopping, finance, dev tools.
SFW only. Links may be affiliate; we may earn a commission.
New picks rotate here. Not affiliated with any single retailer.
```

## Pinned welcome (Message 1 — pin this)

Copy as **plain text** or enable HTML if your client supports it.

```
📌 THE CHECKOUT LIST — start here

Welcome. This channel is a curated list of deals and referral links we actually use or vet — shopping, finance, and dev tools.

HOW IT WORKS
• Pinned board below updates as new offers go live
• Occasional single-deal posts when something’s worth a shout
• Everything here is SFW — no adult content, ever

AFFILIATE DISCLOSURE
Some links are referral or affiliate URLs. If you sign up or buy through them, we may earn a small commission at no extra cost to you. We only list tools and offers we’d recommend anyway.

RULES
• Links open third-party sites — check terms before you buy
• Prices and promos change; we don’t guarantee availability
• No spam, no reselling of this list

Questions or a deal tip? DM @aof_secretary_bot (admin).

— The Checkout List
https://t.me/thecheckoutlist
```

## Launch bulletin (Message 2 — first deals board)

Replace `YOUR_*` placeholders when you have live referral URLs.

```
🛒 THE CHECKOUT LIST — live board
Curated referral links · updated manually until automation ships
━━━━━━━━━━━━━━━━━━

🛠 DEV & PRODUCTIVITY
→ Cursor — AI code editor
https://cursor.com/referral?code=WKMSQ8BYPM1O

→ Claude — AI assistant
https://claude.ai/referral/ve9d3Ki_QA

→ Proton — privacy mail & VPN
YOUR_PROTON_REFERRAL_URL

━━━━━━━━━━━━━━━━━━

💳 FINANCE
→ Revolut — cards & transfers
YOUR_REVOLUT_REFERRAL_URL

━━━━━━━━━━━━━━━━━━

🛍 SHOPPING
→ Temu — deals & coupons
YOUR_TEMU_REFERRAL_URL

━━━━━━━━━━━━━━━━━━

📦 INFRA & MISC
→ Pulsed Media — seedbox & remote storage
https://pulsedmedia.com/clients/aff.php?aff=10812

→ Microsoft Rewards — Bing search rewards
https://rewards.bing.com/welcome?rh=LjD_QLCQ3xc&ref=rafsrchae

━━━━━━━━━━━━━━━━━━

More links added via our intake pipeline (Phase 1).
Suggest a deal: @aof_secretary_bot
```

## URLs already in TBCC seed (safe for this channel)

| Label | URL | Notes |
|-------|-----|--------|
| Cursor referral | `https://cursor.com/referral?code=WKMSQ8BYPM1O` | `manual_only` today |
| Claude referral | `https://claude.ai/referral/ve9d3Ki_QA` | `manual_only` today |
| Pulsed Media seedbox | `https://pulsedmedia.com/clients/aff.php?aff=10812` | `links_hub` partner lane |
| Microsoft Rewards | `https://rewards.bing.com/welcome?rh=LjD_QLCQ3xc&ref=rafsrchae` | `links_hub` + x_buffer |

**Need operator paste:** Temu, Revolut, Proton referral URLs.

## Account hygiene (@powercoreai)

Channel name is neutral; owner username still says `powercoreai`. Options:

1. **Leave as-is** — only admins see owner; subscribers see channel title.
2. **Rename account display name** to `.` or `Checkout List ops` (already minimal).
3. **Later:** dedicated `@checkoutlist` bot for contact if Secretary feels too AOF-branded.

## Phase 1 preview (shipped in code — deploy on island)

1. `links_hub_sfw` placement + `classify_affiliate_lane()` on Secretary `/addsponsor`
2. `build_checkout_list_bulletin()` + `sync_checkout_list_hub()`
3. Env: `TBCC_CHECKOUT_LIST_CHANNEL_IDENT=-1004361597444`
4. Deploy: `python scripts/deploy_checkout_list_bulletin.py --execute --post` (needs Celery post lane + Telethon session)
5. Intake: `/addsponsor sfw https://…` or auto-route Temu/Cursor/Revolut

## Definition of done (Phase 0)

- [x] Pinned welcome live
- [x] Launch bulletin posted (placeholders OK for Temu/Revolut/Proton)
- [x] Secretary bot is channel admin
- [x] Channel not cross-linked from AOF NSFW surfaces
