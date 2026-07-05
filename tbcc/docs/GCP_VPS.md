# TBCC on Google Cloud Platform (GCP)

**One command (Windows, from repo root):**

```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\gcp\setup-tbcc-gcp.ps1
```

That script creates the VM, uploads your local `tbcc/` tree + `.env` + sessions, runs Docker install, migrations, and starts the lean stack. **Stop home TBCC first** (duplicate bots = Telegram 409).

---

Run the **lean TBCC stack** on a single Linux VM: Postgres, Redis, API, Celery (all queues), Beat, Payment/Loot/Secretary/Album Composer bots — same shape as your Windows tray **lean** profile, without Telethon session fights across machines.

For **scrape-only offload** (home PC + remote worker), use [REMOTE_WORKER.md](./REMOTE_WORKER.md) (Oracle/Hetzner/GCP) instead.

---

## 1. Install Google Cloud CLI (home PC)

**Windows:** [Install the gcloud CLI](https://cloud.google.com/sdk/docs/install-sdk#windows)

```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable compute.googleapis.com
```

Verify:

```powershell
gcloud config list
gcloud compute zones list --filter="name~us-west1"
```

---

## 2. Create the VM (CLI)

Generate an SSH key (once):

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\gcp_tbcc -N '""'
```

Bootstrap from repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\gcp\bootstrap-gcp-instance.ps1
```

Defaults:

| Setting | Default | Notes |
|---------|---------|--------|
| Machine | `e2-standard-2` | 2 vCPU / 8 GB — fits lean stack |
| Zone | `us-west1-b` | Change if quota/cost differs |
| Disk | 50 GB balanced | Sessions + Postgres |
| Firewall | IAP SSH only | **No** public 5432/6379/8000 |

Override:

```powershell
powershell ... -Zone us-central1-a -MachineType e2-medium -InstanceName my-tbcc
```

SSH in:

```powershell
gcloud compute ssh tbcc-lean --zone=us-west1-b
```

---

## 3. Clone TBCC on the VM

```bash
sudo mkdir -p /opt && sudo chown $USER:$USER /opt
cd /opt
git clone <your-repo-url> telegram_bot2
```

---

## 4. Sync secrets + sessions from home

On **Windows** (stop home Celery/bots first if migrating — one writer per bot token):

```powershell
cd tbcc
# IAP-friendly (RemoteHost = instance name):
.\scripts\gcp\sync-stack-to-gcp.ps1 -RemoteHost tbcc-lean -RemoteUser ubuntu -UseGcloudSsh -GcpZone us-west1-b

# Or direct IP + OpenSSH:
.\scripts\gcp\sync-stack-to-gcp.ps1 -RemoteHost 34.x.x.x -RemoteUser ubuntu
```

This uploads:

- `infra/.env.gcp-lean` (mapped from your local `tbcc/.env` + GCP template)
- Telethon `*.session` files into `infra/data/sessions/`

Set a strong `POSTGRES_PASSWORD` in local `.env` before sync, or edit `.env.gcp-lean` on the VM.

---

## 5. Install and start stack (on VM)

```bash
bash /opt/telegram_bot2/tbcc/scripts/gcp/install-gcp-lean-stack.sh
```

Health:

```bash
bash /opt/telegram_bot2/tbcc/scripts/gcp/health-gcp-stack.sh
curl -s http://127.0.0.1:8000/health
```

Logs:

```bash
cd /opt/telegram_bot2/tbcc/infra
docker compose -f docker-compose.gcp-lean.yml logs -f api celery celery_post beat
```

---

## 6. Expose API (required for Telegram webhooks)

API listens on **127.0.0.1:8000** only. Pick one:

1. **Cloudflare Tunnel** (recommended) — same pattern as home; point tunnel at `http://127.0.0.1:8000`
2. **Tailscale** on the VM — access API from your PC over tailnet
3. **Do not** open `0.0.0.0:8000` on GCP firewall without auth

Set in `.env.gcp-lean`:

```env
TBCC_PUBLIC_API_URL=https://api.yourdomain.com
```

---

## 7. Optional dashboard

Build + preview on the VM (profile `dashboard`):

```bash
cd /opt/telegram_bot2/tbcc/infra
docker compose -f docker-compose.gcp-lean.yml --profile dashboard up -d dashboard
```

Tunnel port **5173** or use dashboard only over Tailscale.

---

## Architecture

```
GCP VM (e2-standard-2)
├── postgres / redis     (Docker internal only)
├── api :8000            (127.0.0.1 — tunnel)
├── celery               (celery,scrape,subscription,telegram)
├── celery_post          (post queue)
├── celery_post_scheduler
├── beat
├── payment / secretary / loot / album_composer bots
└── data/sessions        (persistent volume — Telethon)
```

---

## Cost / sizing

| Shape | RAM | TBCC lean |
|-------|-----|-----------|
| `e2-medium` | 4 GB | Tight — set `TBCC_SKIP_ENRICHMENT=1` |
| `e2-standard-2` | 8 GB | **Recommended** |
| `e2-standard-4` | 16 GB | Headroom for enrichment sidecars later |

---

## Migrate from Windows home

1. Stop tray / all TBCC processes at home (`tbcc-stack-cli.ps1 -Action Stop` per service or tray Stop all).
2. `pg_dump` home Postgres if moving data (optional script path in sync `-IncludeDbDump` — manual restore).
3. Sync env + sessions (step 4).
4. Start GCP stack; verify bots with `GET /ops/stack-status` equivalent via health script.
5. Point Cloudflare tunnel DNS to GCP.
6. Keep home stack **off** to avoid duplicate Telegram bot 409 conflicts.

---

## Files

| Path | Purpose |
|------|---------|
| `scripts/gcp/bootstrap-gcp-instance.sh` | `gcloud` VM + IAP firewall |
| `scripts/gcp/bootstrap-gcp-instance.ps1` | Windows launcher |
| `scripts/gcp/install-gcp-lean-stack.sh` | Docker install + compose up |
| `scripts/gcp/sync-stack-to-gcp.ps1` | Home → VM env + sessions |
| `scripts/gcp/health-gcp-stack.sh` | Smoke test |
| `infra/docker-compose.gcp-lean.yml` | Lean stack compose |
| `infra/env.gcp-lean.example` | Env template |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gcloud` not found | Install SDK; restart terminal |
| SSH timeout | Use `gcloud compute ssh` (IAP), not raw IP:22 |
| `database is locked` | Only one host using each `.session`; stop home stack |
| Telegram 409 Conflict | Two payment/loot bots running — stop home bots |
| API 500 / missing tables | `docker compose ... run --rm api python -m alembic upgrade head` |
| OOM on e2-medium | Upsize VM or disable optional workers |
