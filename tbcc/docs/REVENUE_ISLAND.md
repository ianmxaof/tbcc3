# TBCC Revenue Island — dedicated VPS (not scrape micro)

**Lock:** Money runs on a small paid Linux VPS (~$5–15/mo). The existing **GCP scrape e2-micro stays scrape-only** (leave it running; do not put island on it). Home becomes an optional workstation (sleep OK after cutover).

**One-liner:** Home = light lean cold-start; island = Postgres + Redis + API + payment + loot + Beat + slim Celery + **optional always-on dashboard/forum** (`--profile ui`); scrape = separate; agents never Start bots.

**CLI-first:** After you have a Hetzner account + one API token, provision and operate the island with `hcloud` / `ssh` / `scp` / Docker Compose. Browser only for account signup (if needed) and creating the API token.

**Grok / extra agents:** Not required for cutover. Plan is locked; scripts + this runbook are enough. Use Desktop Auto only if a script fails; **Tray/operator** for bot Start/Stop and overnight smoke.

---

## Google scrape micro — what happens to it?

| Keep | Do not |
|------|--------|
| Leave the GCP e2-micro running as **Celery `scrape` only** | Recreate it as the revenue island |
| Keep Tailscale + GHCR worker as today (`REMOTE_WORKER.md`) | Co-locate Postgres/API/payment/loot on it (too small; OOM risk) |
| Accept scrape may stall if it still uses **home** Redis while home sleeps | Fail cutover because scrape paused |

**Follow-up (not v1):** point scrape worker at **island** Redis/Postgres so ingest survives home sleep too. Until then: overnight success = **bots answer**, not “scrapes keep finishing.”

---

## Host pick

| Option | Notes |
|--------|--------|
| **Hetzner CPX21 (US ash/hil default)** | 4 GB shared x86 — fits island; CLI via `hcloud`. EU: `cx23` / `cpx22` also OK. Not `cx22` (gone / not in ash). |
| Lightsail / DO basic 2GB | Fine if you bump past 1GB |
| Oracle Ampere free | Only if you accept free-tier quirks |

**Do not** co-locate this stack on the scrape e2-micro.

---

## Browser only if needed (account + token)

If you **already** have Hetzner Cloud access, skip to [CLI from home](#cli-from-home-windows).

If not:

1. **Sign up / log in** — [https://accounts.hetzner.com/signUp](https://accounts.hetzner.com/signUp) · [https://accounts.hetzner.com/login](https://accounts.hetzner.com/login)
2. **Open Cloud Console** — [https://console.hetzner.cloud/](https://console.hetzner.cloud/)
3. **Create or open a project** (one click in console if empty).
4. **API token (once)** — Project → **Security** → **API Tokens** → **Generate API Token** (Read & Write). Copy once; paste into `hcloud context create` below.  
   Console shortcuts after login usually land on the project; Security is in the left nav.
5. **Billing** — add a payment method in [https://console.hetzner.cloud/](https://console.hetzner.cloud/) if prompted (required before create). Still browser.

Optional later (also browser-or-CLI once): Cloudflare account for Tunnel; Tailscale auth key at [https://login.tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys) (reusable/ephemeral **auth** key).

Docs: [hcloud CLI](https://github.com/hetznercloud/cli) · [Community howto](https://community.hetzner.com/tutorials/howto-hcloud-cli/)

---

## CLI from home (Windows)

### 0. Install CLI + context (one-time)

```powershell
winget install HetznerCloud.cli
# reopen shell, then:
hcloud context create tbcc
# paste API token when prompted
```

Upload your SSH public key if the project has none:

```powershell
hcloud ssh-key create --name laptop --public-key-from-file $env:USERPROFILE\.ssh\id_ed25519.pub
```

### 1. Create the server (Docker via cloud-init; **no bots**)

```powershell
cd tbcc
# Optional: -TailscaleAuthKey "tskey-auth-..." from Tailscale admin
.\scripts\revenue-island\create-hetzner-island.ps1 -Location ash -SshKeyName laptop
# US ash: default -Type cpx21. EU example:
# .\scripts\revenue-island\create-hetzner-island.ps1 -Location nbg1 -Type cx23 -SshKeyName laptop
# -WhatIf to dry-run the hcloud line
```

Defaults: name `tbcc-revenue-island`, type **`cpx21`**, location `ash`, image `ubuntu-24.04`. Wait ~60–90s for cloud-init. Check types: `hcloud server-type list`.

### 2. Sync files + bootstrap API plane

```powershell
$ip = hcloud server ip tbcc-revenue-island
.\scripts\revenue-island\sync-island-files.ps1 -HostName "root@$ip"
# After filling secrets locally into infra\.env.revenue-island:
.\scripts\revenue-island\sync-island-files.ps1 -HostName "root@$ip" -IncludeFilledEnv

ssh root@$ip "bash /opt/tbcc/scripts/revenue-island/bootstrap-island.sh"
# starts: postgres redis api worker worker_post beat — NOT payment/loot
```

Fill `.env.revenue-island` from [`infra/env.revenue-island.example`](../infra/env.revenue-island.example) (tokens, R2, `TBCC_API_PUBLIC_URL`, strong `POSTGRES_PASSWORD`). **Never commit** the filled file.

### 3. DB migrate + health (CLI)

On home (Docker postgres):

```powershell
# example — adjust container name / auth to match your home stack
docker exec -i <home-postgres> pg_dump -U postgres tbcc > $env:TEMP\tbcc-home.dump
scp $env:TEMP\tbcc-home.dump root@${ip}:/tmp/tbcc-home.dump
```

On island:

```bash
# restore into compose postgres (names from compose)
docker compose -f /opt/tbcc/infra/docker-compose.revenue-island.yml --env-file /opt/tbcc/infra/.env.revenue-island \
  exec -T postgres psql -U postgres -d tbcc < /tmp/tbcc-home.dump
# or drop/recreate then restore — see postgres docs for large DBs

docker compose -f /opt/tbcc/infra/docker-compose.revenue-island.yml --env-file /opt/tbcc/infra/.env.revenue-island \
  exec api alembic upgrade head

curl -fsS http://127.0.0.1:8000/health
```

### 3b. Always-on dashboard + AOF Forum (optional profile `ui`)

Keeps the control-plane UI and forum up on the VPS without home Vite. Full runbook: [`ISLAND_UI_SURFACES.md`](./ISLAND_UI_SURFACES.md).

```powershell
.\scripts\revenue-island\sync-island-ui.ps1 -HostName "root@$ip"
# On VPS: fill Supabase + TBCC_DASHBOARD_PUBLIC_URL / TBCC_FORUM_PUBLIC_URL / bridge secret, then:
# bash /opt/tbcc/scripts/revenue-island/up-island-ui.sh
# Tunnel dash.powercore.app → :5173 and forum.powercore.app → :3001 (Access on dash).
```

### Database uptime (Postgres + Redis)

Island money stack depends on **postgres** + **redis** containers. Compose uses `restart: always`; a **systemd timer** re-checks every 5 minutes and after boot:

```bash
# One-time install (also runs from bootstrap-island.sh and deploy-island-live.ps1):
bash /opt/tbcc/scripts/revenue-island/install-island-database-watchdog.sh

# Manual check:
bash /opt/tbcc/scripts/revenue-island/ensure-island-databases.sh
systemctl status tbcc-island-databases.timer
journalctl -u tbcc-island-databases.service -n 20
```

`ensure-island-api-reachable.sh` runs database ensure before API/tunnel checks.

### 4. Public webhooks (CLI-friendly)

Point Cloudflare Tunnel / Gumroad Ping at island `TBCC_API_PUBLIC_URL` (not home). Tunnel setup is mostly `cloudflared` once the zone exists.

### 5. Bot cutover (operator — no dual tokens)

```powershell
# Home: stop tray payment + loot, then:
.\scripts\revenue-island\assert-home-bots-down.ps1
```

```bash
# Island (or from home with SSH):
bash /opt/tbcc/scripts/revenue-island/up-island-bots.sh
# optional: HOME_STATUS_CMD='ssh home-pc ...' to refuse if home bots still up
```

Telegram smoke → then on home:

```powershell
.\scripts\revenue-island\mark-home-bots-off.ps1
# set in tbcc/.env (manual): TBCC_REVENUE_ISLAND_ACTIVE=1
```

Overnight: home asleep → bots still answer. Scrape stall on home Redis = **known / deferred**.

### Abort

Any Telegram **409** → on island: `docker compose ... --profile bots stop` → restore home payment/loot → fix → retry.

---

## Queue audit (slim Celery)

From `backend/app/workers/celery_app.py` `task_routes`:

| Queue | Revenue-relevant tasks | On island? |
|-------|------------------------|------------|
| `celery` | `sale_announce_worker`, `loot_promo_worker`, `scheduler_worker`, … | **Yes** (`worker`) |
| `subscription` | `grant_access_worker`, `subscription_worker`, milestones, drop_countdown | **Yes** (`worker`) |
| `telegram` | import/mirror helpers used by fulfill paths | **Yes** (`worker`) |
| `post_scheduler` / `post` | sale FOMO + scheduled channel posts (`drain_scheduled_post_queue`, `post_scheduled_text`) | **Yes** (`worker_post`) |
| `scrape` | Telethon scrapers | **No** — GCP micro |
| `ops_*` | growth/relay/erome | Home/dev |

Compose:
- `worker`: `-Q celery,subscription,telegram`
- `worker_post`: `-Q post_scheduler,post` (separate solo pool so Telethon poster never blocks fulfill)

Without `worker_post`, sale announces upsert into `scheduled_text_posts` but never send — dashboard shows overdue backlog.

---

## Artifacts

| Path | Role |
|------|------|
| [`infra/docker-compose.revenue-island.yml`](../infra/docker-compose.revenue-island.yml) | postgres, redis, api, worker, worker_post, beat, bots under `--profile bots` |
| [`infra/env.revenue-island.example`](../infra/env.revenue-island.example) | secrets template |
| [`scripts/revenue-island/create-hetzner-island.ps1`](../scripts/revenue-island/create-hetzner-island.ps1) | `hcloud server create` + cloud-init |
| [`scripts/revenue-island/cloud-init-island.yaml`](../scripts/revenue-island/cloud-init-island.yaml) | Docker (+ optional Tailscale) first boot |
| [`scripts/revenue-island/sync-island-files.ps1`](../scripts/revenue-island/sync-island-files.ps1) | scp compose/scripts to `/opt/tbcc` |
| [`scripts/revenue-island/dashboard-tunnel.ps1`](../scripts/revenue-island/dashboard-tunnel.ps1) | SSH `-L` local :8000 → island API (dashboard = VM DB) |
| [`scripts/revenue-island/install-island-tailscale.ps1`](../scripts/revenue-island/install-island-tailscale.ps1) | Install Tailscale on VPS + join tailnet |
| [`scripts/revenue-island/sync-admin-session.ps1`](../scripts/revenue-island/sync-admin-session.ps1) | Copy `admin.session` for loot media (one host only) |
| [`scripts/revenue-island/bootstrap-island.sh`](../scripts/revenue-island/bootstrap-island.sh) | API plane up; **no bots** |
| [`scripts/revenue-island/up-island-bots.sh`](../scripts/revenue-island/up-island-bots.sh) | bots after home assert |
| [`scripts/revenue-island/mark-home-bots-off.ps1`](../scripts/revenue-island/mark-home-bots-off.ps1) / [`assert-home-bots-down.ps1`](../scripts/revenue-island/assert-home-bots-down.ps1) | post-cutover lock |
| [`scripts/revenue-island/wire-r2-rclone.ps1`](../scripts/revenue-island/wire-r2-rclone.ps1) | Push Mega+R2 rclone remotes to island from `tbcc/.env` S3 keys |
| [`scripts/revenue-island/setup-rclone-r2-from-env.sh`](../scripts/revenue-island/setup-rclone-r2-from-env.sh) | Configure `r2:` remote on island |
| [`scripts/revenue-island/mega-export-to-r2.sh`](../scripts/revenue-island/mega-export-to-r2.sh) | Background `mega:` → `r2:aof-media/mega-export` (no home bandwidth) |

Prefer `TBCC_WORKER_IMAGE=ghcr.io/ianmxaof/tbcc-worker:latest` (pull, no build-on-VPS).

---

## Mega → R2 vault (server-side) — **PAUSED**

**2026-07-16:** Full Mega→R2 export is **stopped**. Do not resume until there is a clear media strategy (what belongs in R2, for which product surfaces) and a Cloudflare cost/profit case. Partial `mega-export/` objects may already exist; treat as inconclusive experiment, not the vault.

Do **not** enable R2 Data Catalog for this. Needs S3 Access Key ID + Secret (`TBCC_R2_ACCESS_KEY_ID` / `TBCC_R2_SECRET_ACCESS_KEY`) — not the Bearer `TBCC_CF_API_TOKEN`.

```powershell
# status / kill only until strategy decision:
ssh root@5.161.53.91 'bash /opt/tbcc/scripts/revenue-island/mega-export-to-r2.sh --status'
# start again only after explicit operator go-ahead:
# .\scripts\revenue-island\wire-r2-rclone.ps1 -StartExport
```

Destination prefix (if resumed): `r2:aof-media/mega-export/`.

---

## Loot media on the island (Telethon session)

Loot rolls load media from Telegram Saved Messages via **`admin.session`**. Without that file on the island, you get banner text but:

`skip media … Telegram admin session is not logged in (admin.session)`

**Tonight fix (done via `sync-admin-session.ps1`):**

1. Stop home processes that use `admin.session` (backend / Celery telegram lanes).
2. `.\scripts\revenue-island\sync-admin-session.ps1 -HostName root@…`
3. Compose mounts `/opt/tbcc/sessions` → `/sessions` with `TELEGRAM_SESSION_PATH=/sessions/admin` on **api** + **worker** + **worker_post**.
4. `worker_post` also sets `TBCC_POSTER_TELEGRAM_SESSION=/sessions/admin_poster` + `TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1` so sale FOMO / scheduled posts can Telethon-send without sharing the admin SQLite file.
5. Recreate `api` / `worker` / `worker_post`.

**Hard rule:** only **one** host may run that session. After cutover, home must not open `admin.session` again until you intentionally move it back.

Without `worker_post` (or without a logged-in poster session), sale FOMO rows sit in the dashboard as overdue / unsent.

**R2 / Cloudflare later:** R2 is where paid packs and promo files live for delivery when home disk is off. Monetization is still Stars / Gumroad / loot keys — R2 is storage + CDN, not the checkout. Long-term loot should prefer R2/local pool bytes so the island does not need Telethon for every roll.

---

## Dashboard + scheduler: home vs island (read this)

You **still use the dashboard**. It must talk to the **island** API to see live scheduler / media / loot DB after cutover.

| How you open `:8000` | What you see |
|----------------------|--------------|
| Home tray backend only | **Home** Postgres — optional workstation. Not what payment/loot on the VM use. A media id can be “dead” here and fine on the island. |
| SSH tunnel → island | **Island** Postgres — scheduler behind?, rolls, revenue truth |
| Tailscale → island `:8000` | Same as tunnel, no open SSH window |

Telegram bot profile “DC1, Miami” is Telegram’s data center — **not** where TBCC runs.

### 1) SSH tunnel (works today — no Tailscale required)

```powershell
cd tbcc
.\scripts\revenue-island\dashboard-tunnel.ps1
# default: root@5.161.53.91 → local :8000
# If home Docker already bound :8000:  -LocalPort 8001
```

Leave that window open. Then `curl http://127.0.0.1:8000/health` or run the dashboard against that port. **Ctrl+C** closes the tunnel.

### 2) Tailscale on the island (best daily driver)

Create an auth key: [https://login.tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys)  
(Optional: save as `TBCC_TAILSCALE_AUTHKEY` in home `tbcc/.env` — never commit.)

```powershell
cd tbcc
.\scripts\revenue-island\install-island-tailscale.ps1 -HostName root@5.161.53.91 -AuthKey "tskey-auth-..."
# then from home (Tailscale up):
curl http://tbcc-revenue-island:8000/health
# or: tailscale status  → use 100.x IP
```

Point dashboard / extension API base at that Tailscale host when you want island truth.

### 3) Do not expect parity without (1) or (2)

Home `:8000` without a tunnel is a **different** API + DB. Extension “API offline” on home is normal when the tray backend is stopped; money still runs on the island.

CLI always-on check (no dashboard):

```powershell
ssh root@5.161.53.91 "curl -fsS http://127.0.0.1:8000/health; docker compose -f /opt/tbcc/infra/docker-compose.revenue-island.yml --env-file /opt/tbcc/infra/.env.revenue-island ps"
```

**Security note:** island compose currently publishes `:8000` on the public IP. Prefer Tailscale/SSH access long-term and firewall public 8000/5432/6379 when you can.

---

## Data model after cutover

- **Island Postgres = revenue primary** (one-time `pg_dump` home → restore on island before bots poll).
- **Home Docker Postgres = local/dev only.** No “home API → island DB over Tailscale” in v1.
- **R2** = media source of truth when home disk is off.

---

## Home lean + post-cutover bots Off

Pre-cutover lean (`TBCC_STACK_PROFILE=lean`): `backend`, `celery`, `beat`, `payment`, `loot` (+ Docker PG/Redis).

**Toggle override:** `.tbcc-run/service-toggles.json` wins over lean defaults. Clear leftover `dashboard`/`celery_post` trues for a true lean first boot.

**After cutover success:**

1. Set `TBCC_REVENUE_ISLAND_ACTIVE=1` in home `tbcc/.env`.
2. Run `scripts/revenue-island/mark-home-bots-off.ps1`.
3. Casual tray Start stack must **not** bring home payment/loot up (409 risk).

---

## Phase B tray smoke (operator)

Meltdown / `THROTTLE` / `STALE` are already in the panel — not greenfield.

1. Exit TBCC Supervisor tray fully; relaunch.
2. Open Panel + Mini; sparks update; drag after idle (no freeze).
3. Stop backend / kill `:8000` → `THROTTLE` or `STALE`; Services LEDs still refresh.
4. Toggle a non-bot optional service; match `tbcc-stack-cli.ps1 -Action Status`.

Status truth: CLI/panel when API down; `/ops/stack-status` only when API up.

---

## Cutover checklist (short)

1. Account + API token (browser if needed) → `hcloud context create`
2. `create-hetzner-island.ps1` → `sync-island-files.ps1` → fill `.env` → `bootstrap-island.sh`
3. `pg_dump` / restore / `alembic` / `/health`
4. Retarget public webhooks → island
5. Stop home payment+loot → `assert-home-bots-down.ps1` → `up-island-bots.sh`
6. Telegram smoke → `mark-home-bots-off` + `TBCC_REVENUE_ISLAND_ACTIVE=1`
7. Overnight home sleep → bots still answer

Agents: never Start bots. GCP scrape micro: leave as scrapes.
