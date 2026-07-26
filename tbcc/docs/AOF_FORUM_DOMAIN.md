# aof-forum domain + API harden

Split public SEO from the TBCC control-plane API. Do **not** put marketing SEO on raw uvicorn.

## Hostnames

| Host | Purpose |
|------|---------|
| `aof-forum.com` / `www` | SEO landing, CTAs, affiliates, future forum |
| `api.aof-forum.com` | TBCC API for extension / bots (TLS + Access or internal key) |

Exact TLD is operator choice; keep the `api.` split.

## Cloudflare steps

1. Add the zone in Cloudflare (proxy orange-cloud ON).
2. **SEO surface:** Cloudflare Pages (or Worker) on apex/`www` — loot CTA → `https://telegram.me/aof_lootgod_bot`, affiliate links, later forum.
3. **API:** CNAME/A `api` → island origin (or Cloudflare Tunnel to `http://127.0.0.1:8000` on the VPS).
4. Prefer **Cloudflare Access** on `api.` for browser humans; extension uses `X-TBCC-Internal-Key`.
5. After proxy works, **close raw** `0.0.0.0:8000` to the world (firewall allow Cloudflare only, or bind compose to `127.0.0.1:8000` and tunnel).

## Island env

```env
TBCC_API_PUBLIC_URL=https://api.aof-forum.com
TBCC_API_REQUIRE_INTERNAL=1
TBCC_INTERNAL_API_KEY=<same as home>
TBCC_LINK_GATE_PROVIDERS=linkvertise,admaven,workink
TBCC_LINK_GATE_ROTATION=first
```

Compose helper: [`infra/docker-compose.revenue-island.bind-localhost.yml`](../infra/docker-compose.revenue-island.bind-localhost.yml) — use after tunnel is up.

## Extension

Options → Local stack → **API base URL** = `https://api.aof-forum.com` (or Tailscale MagicDNS until DNS is live). Paste internal key. Reload extension.

## Until domain is purchased

Use Tailscale to island `:8000`. Do not default the extension to the bare public VPS IP.
