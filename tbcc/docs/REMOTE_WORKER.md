# TBCC Remote Worker — offload Celery `scrape` queue to a cloud VM

> **Not the revenue plane.** Payment + loot + API for money live on a **dedicated VPS** — see [`REVENUE_ISLAND.md`](REVENUE_ISLAND.md). Do not stack bots on this scrape micro.

## Setup vs routine launch

| | **One-time setup** | **Routine launch** (every `start.ps1`) |
|--|-------------------|----------------------------------------|
| **When** | First VM / new tailnet / new session | Daily stack start |
| **Script** | `setup-remote-worker.ps1` | `launch-remote-worker.ps1` (auto `[0c]`) |
| **Does** | Create GCP VM, Tailscale bind, `.env` queues, sync session, GHCR bootstrap | Tailscale up, sync scripts, `docker pull`, ensure worker running |
| **You run** | Once manually | Automatic with `.\start.ps1 -Full -WtTabs` |

WT tab **TBCC-RemoteWorker** polls VM scrape logs every `TBCC_REMOTE_WORKER_LOG_TICK_S` (default 5s).

---

Run **heavy Telethon scrapes** on a free/cheap Linux VM (GCP e2-micro, Oracle Always Free, or Hetzner) while keeping API, bots, Beat, Postgres, and Redis at home.



```

HOME (Windows, lean 24/7)              REMOTE VM (Linux, $0–cheap)

────────────────────────────         ───────────────────────────────────────────

API + Cloudflare Tunnel              Celery worker — queue `scrape` only

Postgres + Redis  ◄── Tailscale ──►  scraper.session on persistent volume

Beat, Payment, Loot bots             Image from GHCR (pull, no local build)

TBCC_CELERY_HOME_QUEUES=             docker compose remote-worker(.ghcr)

  celery,subscription,telegram

```



Scrape jobs queued from home travel over **shared Redis**; only the remote worker consumes `scrape`.



## GHCR upgrade (recommended)

**Before:** VM runs `docker compose build` — compiles Python image on e2-micro (slow, RAM-heavy, can OOM).

**After:** Home PC or GitHub Actions **builds once** → pushes to `ghcr.io/ianmxaof/tbcc-worker:latest` → VM only **`docker pull` + up** (~30s, near-zero CPU).

Enable in `tbcc/.env`:

```env
TBCC_USE_GHCR=1
TBCC_GHCR_USER=ianmxaof
TBCC_GHCR_TOKEN=ghp_...   # write:packages for push; read:packages on VM
```

One-time GHCR switch (you are here):

```powershell
cd tbcc
.\scripts\remote-worker\sync-remote-worker-scripts.ps1 -ViaGcloud   # done
.\scripts\remote-worker\push-ghcr-worker.ps1                          # build+push from home
.\scripts\remote-worker\update-remote-worker.ps1 -ViaGcloud         # pull on VM
```

After that, every `start.ps1` step `[0c]` keeps the VM on the latest image.

---



## Secrets: TBCC .env vs Windows Credential Manager vs GCP Secret Manager



| Store | What it is | Use for |

|-------|------------|---------|

| **`tbcc/.env`** | Primary local config | All API keys TBCC reads at runtime |

| **Windows Credential Manager** (`TBCC/<KEY>`) | Local backup via `cmdkey` | Recovery / audit; not the app’s source of truth |

| **GCP Secret Manager** | Google Cloud vault | Optional: Tailscale auth keys / GHCR tokens injected into VM metadata at create time |



They are **related but not the same**. Yesterday’s clipboard / context-menu tool writes **`.env` + Credential Manager**. GCP Secret Manager is the cloud equivalent for VM bootstrap secrets — optional; today we pass keys via instance metadata from `tbcc/.env` (`TBCC_TAILSCALE_AUTHKEY`, `TBCC_GHCR_TOKEN`).



**Clipboard capture (fixed):**



```powershell

cd tbcc\tools

.\register-tbcc-capture-secret-context-menu.ps1

# Copy API key → right-click desktop → "TBCC: Save clipboard API key to .env"

# If the key name cannot be guessed, a small picker dialog appears (no silent fail).

# Log: tbcc\.tbcc-run\capture-secret.log

```



Browser (best): select key text → **TBCC: Save selection as API key to .env**.



---



## Fast path (recommended)



### A. Push worker image (home or CI)



```powershell

cd tbcc

.\scripts\remote-worker\push-ghcr-worker.ps1

# or wait for GitHub Action: .github/workflows/tbcc-remote-worker-ghcr.yml

```



Needs `TBCC_GHCR_TOKEN` (PAT `write:packages`) or `gh auth login`.



### B. Create GCP VM with startup script



```powershell

# Ephemeral Tailscale key → .env first (clipboard capture works for tskey-*)

.\scripts\tbcc-secret.ps1 -Key TBCC_TAILSCALE_AUTHKEY -FromClipboard



.\scripts\remote-worker\create-gcp-vm.ps1 `

  -ProjectId "tbcc-cloud-instance" `

  -UseGhcr `

  -WithStartupScript

```



Startup installs Tailscale + Docker, clones the repo, prefers GHCR pull.



### C. Enable home offload + sync session



```powershell

# After Tailscale shows the VM IP:

.\scripts\remote-worker\enable-home-offload.ps1 -RemoteHost 100.x.y.z

.\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost 100.x.y.z -RemoteUser <linux-user>

.\scripts\remote-worker\update-remote-worker.ps1 -RemoteHost 100.x.y.z   # pull + up

.\scripts\remote-worker\status-remote-worker.ps1

```



Restart **TBCC-Celery** from the tray so home no longer consumes `scrape`.



---



## 1. Home — stop consuming scrape queue locally



In `tbcc/.env` (or via `enable-home-offload.ps1`):



```env

TBCC_CELERY_HOME_QUEUES=celery,subscription,telegram

TBCC_REMOTE_STACK_HOST=100.x.y.z

```



Restart **TBCC-Celery** (tray or `start.ps1`).



---



## 2. Tailscale mesh (required)



1. Install Tailscale on home PC and the VM; same tailnet.

2. Note home Tailscale IP and VM IP.

3. **`start.ps1` auto-starts Tailscale** when `TBCC_REMOTE_STACK_HOST` is set (step `[0b]`).



**Never expose Postgres/Redis to the public internet.** Tailscale only.



### Bind Docker Postgres + Redis to Tailscale IP



`docker-compose.tailscale-bind.yml` exposes **localhost** and your **Tailscale IP**. `start.ps1` applies it when `TBCC_REMOTE_STACK_HOST` is set.



```powershell

cd tbcc\infra

docker compose -f docker-compose.infra.yml -f docker-compose.tailscale-bind.yml up -d

```



Allow Windows Firewall inbound on 5432/6379 **Private** profile for Tailscale adapter only.



---



## 3. VM options



| Provider | Notes |

|---------|--------|

| **GCP e2-micro** | Scripts: `create-gcp-vm.ps1`, IAP SSH, startup-script |

| **Oracle Always Free ARM** | Manual create + `install-remote-worker.sh` |

| **Hetzner CX** | Same as Oracle |



### GCP create (with GHCR)



```powershell

.\scripts\remote-worker\create-gcp-vm.ps1 -ProjectId "YOUR_PROJECT" -UseGhcr

.\scripts\remote-worker\connect-gcp-vm.ps1 -StartupLog   # watch cloud-init

.\scripts\remote-worker\connect-gcp-vm.ps1 -Logs

```



---



## 4. Copy scraper.session (once)



```powershell

.\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost 100.64.0.2 -RemoteUser ubuntu

```



> Do not run scrape on home **and** remote with the same session — SQLite lock conflicts.



---



## 5. Remote — start (GHCR preferred)



```bash

cd /opt/tbcc

export TBCC_USE_GHCR=1

export TBCC_WORKER_IMAGE=ghcr.io/ianmxaof/tbcc-worker:latest

# optional: TBCC_GHCR_USER / TBCC_GHCR_TOKEN for private packages

bash scripts/remote-worker/install-remote-worker.sh

```



Update later (no rebuild):



```bash

bash /opt/tbcc/scripts/remote-worker/pull-remote-worker.sh

# or from home:

# .\scripts\remote-worker\update-remote-worker.ps1 -RemoteHost 100.x.y.z

```



Health:



```bash

bash /opt/tbcc/scripts/remote-worker/health-remote-worker.sh

```



---



## 6. Test from home



```powershell

cd tbcc\backend

py -3.13 scripts/run_aof_batch_scrapes.py --batch third --execute --limit 10

.\scripts\remote-worker\status-remote-worker.ps1

```



Watch remote logs — runs should execute on the VM.



---



## Optional: offload post worker too



```powershell

.\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost 100.x.y.z -RemoteUser ubuntu -IncludePoster

```



On VM:



```bash

docker compose -f infra/docker-compose.remote-worker.ghcr.yml --profile post up -d

```



Stop **TBCC-Celery-Post** on home.



---



## Script index



| Path | Purpose |

|------|---------|

| `scripts/remote-worker/create-gcp-vm.ps1` | Create GCP VM + startup-script + metadata |

| `scripts/remote-worker/startup-script.sh` | First-boot: Tailscale, Docker, clone, worker |

| `scripts/remote-worker/connect-gcp-vm.ps1` | IAP SSH / logs / serial |

| `scripts/remote-worker/push-ghcr-worker.ps1` | Build+push image from home |

| `scripts/remote-worker/pull-remote-worker.sh` | On VM: pull + recreate |

| `scripts/remote-worker/update-remote-worker.ps1` | From home: SSH pull |

| `scripts/remote-worker/enable-home-offload.ps1` | Set `.env` queues + remote host |

| `scripts/remote-worker/status-remote-worker.ps1` | Mesh + docker status |

| `scripts/remote-worker/sync-scraper-session.ps1` | Copy Telethon session |

| `scripts/remote-worker/install-remote-worker.sh` | Bootstrap compose (GHCR or build) |

| `scripts/remote-worker/health-remote-worker.sh` | Redis/Postgres/Celery ping |

| `infra/docker-compose.remote-worker.yml` | Build-on-VM compose |

| `infra/docker-compose.remote-worker.ghcr.yml` | Pull-from-GHCR compose |

| `.github/workflows/tbcc-remote-worker-ghcr.yml` | CI push to GHCR |



---



## Troubleshooting



| Symptom | Fix |

|--------|-----|

| Jobs stay `queued` | Remote worker down, or home Celery still has `scrape` |

| `database is locked` | Two hosts using same `scraper.session` |

| Redis/Postgres timeout | Tailscale down, wrong IP, firewall |

| Context menu does nothing | Re-register menu; check `.tbcc-run\capture-secret.log`; picker should appear |

| GHCR pull denied | Public package or set `TBCC_GHCR_TOKEN` with `read:packages` |

| e2-micro OOM on build | Use `-UseGhcr` / `TBCC_USE_GHCR=1` — never build on the VM |


