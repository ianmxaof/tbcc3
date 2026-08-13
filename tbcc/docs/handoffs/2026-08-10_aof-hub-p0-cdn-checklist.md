# P0 — AOF Hub CDN + stable media URLs

Operator checklist to unblock stable OG images, sitemap thumbs, and CDN-cached B2 delivery.

## Prerequisites

- Domain purchased (working title: **AOF Hub**; TLD operator choice — see `tbcc/docs/AOF_FORUM_DOMAIN.md`)
- Backblaze B2 bucket with private objects (`aof-media-dev` or prod bucket)
- Cloudflare account

## Steps

### 1. Cloudflare zone

1. Add domain in Cloudflare (orange-cloud proxy ON).
2. Point apex/`www` DNS to **Cloudflare Pages** project for `aof-forum/` (build: `npm run build`, output `.next` or Pages adapter per your setup).
3. Point `api.` CNAME to revenue island tunnel (`api.powercore.app` pattern) — already live for TBCC.

### 2. B2 → Cloudflare CDN (private bucket)

**Option A — Cloudflare R2 mirror (if migrating):** defer; forum already uses B2 via `lib/b2.ts`.

**Option B — B2 private + Cloudflare Worker/CDN pull (recommended for current stack):**

1. Create a Cloudflare Worker or Transform Rules origin that signs/proxies B2 GETs, **or** use a public CDN hostname with short-lived edge cache + origin auth.
2. Simplest v1: create a **public read** path prefix on B2 (`cdn/` copies) — only if acceptable for NSFW leakage risk; default doctrine is **private B2 + signed GET at origin**.

**Pragmatic v1 (matches existing code):**

1. Add subdomain `cdn.<domain>` as Cloudflare Worker that:
   - Accepts `GET /media/<b2_key>`
   - Validates path, fetches from B2 with server credentials, caches at edge (`Cache-Control: public, max-age=86400`)
2. Set in `aof-forum/.env.local` and Pages env:

```env
NEXT_PUBLIC_MEDIA_BASE_URL=https://cdn.<your-domain>
```

`lib/media-url.ts` already prefers this over 1-hour presigned URLs.

### 3. aof-forum env (Pages + local)

```env
NEXT_PUBLIC_SITE_URL=https://<your-domain>
NEXT_PUBLIC_MEDIA_BASE_URL=https://cdn.<your-domain>
NEXT_PUBLIC_TBCC_BEACON_BASE=https://api.powercore.app
NEXT_PUBLIC_BEACON_SLUG_VIP=web-vip
NEXT_PUBLIC_BEACON_SLUG_SPICY=web-spicy
```

### 4. Awempire live embeds (P5/P6)

After affiliate approval, edit `aof-forum/data/live-embeds.json`:

- Paste iframe `src` per category into `embeds[].iframeSrc`
- Set `outboundUrl` + keep `beaconSlug` (`web-live-girls`, etc.)
- Add `performerMappings` as extension intel maps performers → tag slugs

Re-seed TBCC beacons on island:

```powershell
cd tbcc/backend
py -3.13 scripts/seed_web_hub_beacons.py --execute
# optional: AWEMPIRE_OUTBOUND_URL_GIRLS=https://... py -3.13 scripts/seed_web_hub_beacons.py --execute --only web-live-girls
```

### 5. Verify

```bash
curl -I https://cdn.<domain>/media/<known-b2-key>
curl https://<domain>/sitemap.xml
curl https://<domain>/live
```

Share a media page on Telegram — OG image should not 403 after 1 hour.

## Rollback

Unset `NEXT_PUBLIC_MEDIA_BASE_URL` — app falls back to presigned URLs (dev behavior).
