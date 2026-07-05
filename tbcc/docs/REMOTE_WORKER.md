# TBCC Remote Worker — offload Celery `scrape` queue to a cloud VM

Run **heavy Telethon scrapes** on Oracle Cloud / Hetzner while keeping API, bots, Beat, Postgres, and Redis at home.

```
HOME (Windows, lean 24/7)              REMOTE VM (Linux, $0 Oracle or ~€4 Hetzner)
────────────────────────────         ───────────────────────────────────────────
API + Cloudflare Tunnel              Celery worker — queue `scrape` only
Postgres + Redis  ◄── Tailscale ──►  scraper.session on persistent volume
Beat, Payment, Loot bots             No API, no bots, no Beat
TBCC_CELERY_HOME_QUEUES=             docker compose remote-worker
  celery,subscription,telegram
```

Scrape jobs queued from home (dashboard, batch script, Beat cron) travel over **shared Redis**; only the remote worker consumes `scrape`.

---

## 1. Home — stop consuming scrape queue locally

In `tbcc/.env`:

```env
# Home Celery must NOT listen on scrape when remote worker is active
TBCC_CELERY_HOME_QUEUES=celery,subscription,telegram
```

Restart **TBCC-Celery** (tray or `start.ps1`).

---

## 2. Tailscale mesh (recommended)

1. Install [Tailscale](https://tailscale.com) on home PC and the VM; same tailnet.
2. Note home Tailscale IP (e.g. `100.64.0.1`) and VM IP (e.g. `100.64.0.2`).

**Never expose Postgres/Redis to the public internet.** Tailscale only.

### Bind Docker Postgres + Redis to Tailscale IP

If infra runs via Docker on home, create `tbcc/infra/docker-compose.tailscale-bind.yml`:

```yaml
services:
  postgres:
    ports:
      - "100.64.0.1:5432:5432"   # replace with YOUR home Tailscale IP
  redis:
    ports:
      - "100.64.0.1:6379:6379"
```

Apply:

```powershell
cd tbcc\infra
docker compose -f docker-compose.infra.yml -f docker-compose.tailscale-bind.yml up -d
```

Allow Windows Firewall inbound on 5432/6379 **Private** profile for Tailscale adapter only.

---

## 3. Oracle Cloud free VM (or Hetzner / GCP)

**Full lean stack on GCP:** see [GCP_VPS.md](./GCP_VPS.md) (`scripts/gcp/`).

**Oracle (always-free ARM) — scrape worker only:**

1. Create Ubuntu 22.04/24.04 VM (Ampere A1, 1 OCPU / 6 GB is enough).
2. Open outbound HTTPS (Telegram API); **no** inbound ports required (Tailscale handles mesh).
3. `ssh ubuntu@100.64.0.2`

**Clone TBCC:**

```bash
sudo mkdir -p /opt/tbcc && sudo chown $USER:$USER /opt/tbcc
git clone <your-repo> /opt/tbcc
# or: rsync from home — see sync script below
```

---

## 4. Copy scraper.session (once)

On **home PC** (PowerShell, from `tbcc/`):

```powershell
.\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost 100.64.0.2 -RemoteUser ubuntu
```

This copies `backend/scraper.session` (+ WAL/SHM) to the VM.

> **Important:** Do not run scrape on home **and** remote at the same time with the same session file — SQLite lock conflicts. Home Celery must exclude `scrape` (step 1).

---

## 5. Remote — configure and start

On the **VM**:

```bash
cd /opt/tbcc/infra
cp env.remote-worker.example .env.remote-worker
nano .env.remote-worker   # DATABASE_URL, REDIS_URL, API_ID, API_HASH
```

Example `.env.remote-worker`:

```env
DATABASE_URL=postgresql://postgres:postgres@100.64.0.1:5432/tbcc
REDIS_URL=redis://100.64.0.1:6379/0
API_ID=...
API_HASH=...
TBCC_SCRAPER_TELEGRAM_SESSION=/data/sessions/scraper
TBCC_SCRAPER_FORWARD_ONLY=1
TBCC_SCRAPER_SKIP_NOFORWARD=1
```

Start:

```bash
bash /opt/tbcc/scripts/remote-worker/install-remote-worker.sh
```

Logs:

```bash
cd /opt/tbcc/infra
docker compose -f docker-compose.remote-worker.yml logs -f worker_scrape
```

Health:

```bash
bash /opt/tbcc/scripts/remote-worker/health-remote-worker.sh
```

---

## 6. Test from home

With stack up at home (API + Beat + Celery **without** scrape queue):

```powershell
cd tbcc\backend
py -3.13 scripts/run_aof_batch_scrapes.py --batch third --execute --limit 10
```

Watch remote logs — runs should execute on the VM. Dashboard scrape banner + channel intel update as usual.

---

## Optional: offload post worker too

Copy poster session from home:

```powershell
.\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost 100.64.0.2 -RemoteUser ubuntu -IncludePoster
```

On VM `.env.remote-worker`:

```env
TBCC_POSTER_TELEGRAM_SESSION=/data/sessions/admin_poster
```

Start post worker profile:

```bash
cd /opt/tbcc/infra
docker compose -f docker-compose.remote-worker.yml --profile post up -d
```

On home: stop **TBCC-Celery-Post** tab so only remote consumes `post` queue.

---

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| Jobs stay `queued` | Remote worker down, or home Celery still has `scrape` in queues |
| `database is locked` | Two hosts using same `scraper.session` — stop home scrape consumer |
| Redis/Postgres timeout | Tailscale down, wrong IP in `.env.remote-worker`, firewall |
| `scraper_session` auth error | Re-copy session; ensure API_ID/HASH match home |
| Forward-disabled skips | Expected — channel intel marks them; not a remote-worker bug |

---

## Files

| Path | Purpose |
|------|---------|
| `infra/docker-compose.remote-worker.yml` | Remote scrape (+ optional post) worker |
| `infra/env.remote-worker.example` | Remote env template |
| `scripts/remote-worker/sync-scraper-session.ps1` | Home → VM session copy |
| `scripts/remote-worker/install-remote-worker.sh` | VM bootstrap |
| `scripts/remote-worker/health-remote-worker.sh` | Connectivity check |
