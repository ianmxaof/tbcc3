# Island UI surfaces — dashboard + AOF Forum always-on

**Goal:** Keep the TBCC dashboard and AOF Forum up **simultaneously on the revenue VPS**, with no home npm/Vite dependency. Bidirectional admin deep-links connect the two.

## Why the dashboard looked “down”

The island compose stack historically ran **API + workers + bots only**. The Vite dashboard lived on the home PC (`npm run dev` / `dev:island`). When home slept or the tray lean profile left dashboard Off, there was no control-plane UI — even though `api.powercore.app` was healthy.

## Architecture

| Surface | Container | Bind | Public hostname (tunnel) |
|---------|-----------|------|---------------------------|
| TBCC API | `api` | `:8000` | `api.powercore.app` (existing) |
| Dashboard | `dashboard` (profile `ui`) | `127.0.0.1:5173` → nginx:80 | `dash.powercore.app` |
| AOF Forum | `forum` (profile `ui`) | `127.0.0.1:3001` | `forum.powercore.app` |

- Dashboard nginx proxies `/api` → `http://api:8000` and injects `X-TBCC-Internal-Key`.
- Nginx uses Docker DNS (`resolver 127.0.0.11`) + host variable so API container recreates do not leave a stale upstream IP (502 until dashboard restart).
- **Put Cloudflare Access on `dash.*`** — anyone who can reach the dashboard gets full API power via that proxy.
- Forum uses Supabase auth; `profiles.is_admin` gates `/admin`.

## Bring-up (VPS)

```bash
# Once: sync sources (dashboard under /opt/tbcc, forum under /opt/aof-forum)
# From home: .\scripts\revenue-island\sync-island-ui.ps1 -HostName root@<ip>

cd /opt/tbcc/infra
# Fill .env.revenue-island: TBCC_*_PUBLIC_URL, bridge secret, Supabase keys, ADMIN_BRIDGE_EMAIL

docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island \
  --profile ui up -d --build dashboard forum
```

Helper: `bash /opt/tbcc/scripts/revenue-island/up-island-ui.sh`

RAM tip: Next.js build on a 4 GB box needs **~2 GB swap** the first time. Prefer shipping images from a workstation (`docker save | ssh docker load`) or GHCR (`TBCC_DASHBOARD_IMAGE` / `AOF_FORUM_IMAGE`). Workflow: `.github/workflows/tbcc-ui-ghcr.yml` — needs a PAT/`packages:write` to push; CI `GITHUB_TOKEN` works on `workflow_dispatch` from GitHub Actions.

## Cloudflare Tunnel routes

Add ingress (same tunnel as API or a sibling):

```yaml
- hostname: dash.powercore.app
  service: http://127.0.0.1:5173
- hostname: forum.powercore.app
  service: http://127.0.0.1:3001
```

DNS CNAMEs → tunnel (already created for `dash` / `forum` on `powercore.app`).

### Access (required for dash)

Zero Trust org **AOF Powercore** (`aof-powercore.cloudflareaccess.com`) is enabled.

- App: **TBCC Dashboard** → `dash.powercore.app`
- IdP: One-time PIN (email)
- Allow: `Aof.ianmx@gmail.com` (add more emails in Zero Trust → Access → Applications if needed)

Unauthenticated browser hits get the Cloudflare Access login wall, then reach nginx (which still injects `TBCC_INTERNAL_API_KEY`).

### Tailscale (private path — already on island)

Island is on the tailnet as `tbcc-revenue-island` (`100.71.125.100`). UI ports are published for Tailscale CGNAT only (`lock-island-ui-ports.sh` — localhost + `100.64.0.0/10`).

From a Tailscale-connected PC (your `kaiulew` machine already is):

- Dashboard: `http://tbcc-revenue-island:5173` or `http://100.71.125.100:5173`
- Forum: `http://tbcc-revenue-island:3001`
- API: `http://tbcc-revenue-island:8000/health`

Optional HTTPS Serve (prettier URLs) — one-time enable, then:

```bash
bash /opt/tbcc/scripts/revenue-island/enable-island-tailscale-serve.sh
# Enable prompt: https://login.tailscale.com/f/serve?node=nJARcTxvJM11CNTRL
```

Use Tailscale for day-to-day admin (no Access OTP). Use Access-gated `https://dash.powercore.app` when you're off Tailscale.

## Admin bridge

Shared HMAC secret: `TBCC_ADMIN_BRIDGE_SECRET` (falls back to `TBCC_INTERNAL_API_KEY`).

| Direction | How |
|-----------|-----|
| Dashboard → Forum | Header **Forum** button → `POST /ops/admin-bridge/mint` `{destination:forum}` → opens `/auth/bridge?t=…` → Supabase session as `ADMIN_BRIDGE_EMAIL` + `is_admin` |
| Forum → Dashboard | `/admin` → **Open TBCC dashboard** → mint dashboard token → `https://dash…/?bridge=…` → SPA `AdminBridgeConsumer` |

Tokens expire in ~2 minutes.

Env (island `.env.revenue-island`):

```env
TBCC_DASHBOARD_PUBLIC_URL=https://dash.powercore.app
TBCC_FORUM_PUBLIC_URL=https://forum.powercore.app
TBCC_ADMIN_BRIDGE_SECRET=<long random>
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
ADMIN_BRIDGE_EMAIL=you@example.com
```

## Local still works

Home `npm run dev` / `dev:island` is unchanged for development. Production truth is the island `ui` profile.

## Related

- [`REVENUE_ISLAND.md`](./REVENUE_ISLAND.md)
- [`AOF_FORUM_DOMAIN.md`](./AOF_FORUM_DOMAIN.md)
- Compose: `infra/docker-compose.revenue-island.yml` profile `ui`
