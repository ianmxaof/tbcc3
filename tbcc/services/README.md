# TBCC enrichment sidecars

Used by the auto-tag pipeline (Lustpress metadata + NSFW classifier + LLM fallback).

## Quick setup (recommended)

```powershell
cd c:\Powercore-repo-main\telegram_bot2\tbcc\services

git clone https://github.com/TheHamkerCat/NSFW_Detection_API
git clone https://github.com/sinkaroid/lustpress

.\setup-enrichment.ps1
```

`setup-enrichment.ps1` runs `pip install` for NSFW API and installs **Bun** + `bun install` for Lustpress if needed.

## Manual setup

### NSFW Detection API (port **8001** — not upstream default 8000)

TBCC backend runs on **8000**. Use our launcher so the classifier does not collide:

```powershell
cd c:\Powercore-repo-main\telegram_bot2\tbcc\services\NSFW_Detection_API
py -3.13 -m pip install -U -r requirements.txt
py -3.13 -m pip install "setuptools>=70,<81"
cd ..
py -3.13 run_nsfw_detect.py
```

**Notes:**

- `tensorflow-hub` needs `pkg_resources` from setuptools. Setuptools **81+** removed it — pin **&lt;81** (handled by `setup-enrichment.ps1` and `nsfw-detect-tbcc.txt`).
- On Python 3.13, install **`tf-keras`** and run via `run_nsfw_detect.py` (sets `TF_USE_LEGACY_KERAS=1`) so `nsfw_model.h5` loads. Without this you may see `Only instances of keras.Layer can be added to a Sequential model`.

### Lustpress (port **3000**) — requires [Bun](https://bun.sh)

```powershell
powershell -c "irm bun.sh/install.ps1 | iex"
# Close and reopen PowerShell, then:
cd c:\Powercore-repo-main\telegram_bot2\tbcc\services\lustpress
bun install
bun run start:dev
```

## Start with TBCC

```powershell
cd c:\Powercore-repo-main\telegram_bot2\tbcc
.\start.ps1 -Full -WtTabs
```

Adds tabs **TBCC-NSFW-Detect**, **TBCC-Lustpress**, and **TBCC-CLIP-Categorize** when `.env` has:

```env
TBCC_NSFW_DETECT_URL=http://127.0.0.1:8001
TBCC_LUSTPRESS_URL=http://127.0.0.1:3000
TBCC_CLIP_CATEGORIZE_URL=http://127.0.0.1:8002
TBCC_CLIP_CATEGORIES_FILE=C:/path/to/clip-categories.json
```

Requires **TBCC-Celery** (`-Full`) for import enrichment tasks.

### CLIP niche categorizer (port **8002**)

Local zero-shot sorting against your fixed category list (OpenCLIP ViT-B/32). No LLM vision required for the primary pass.

```powershell
cd c:\Powercore-repo-main\telegram_bot2\tbcc\services
.\setup-enrichment.ps1   # installs torch + open-clip-torch
cd ..
python tools/import_clip_categories.py --in C:/path/your-1400-categories.txt --out data/clip-categories.json
# Set TBCC_CLIP_CATEGORIES_FILE in .env to that output path, then:
.\start.ps1 -Full -WtTabs
```

First CLIP startup encodes all category prompts (~few minutes on CPU for 1400 labels; cached as `.clip_embeddings.npz` beside the catalog).

**How it works:** each category becomes a text prompt (`a photo of {label}`). At startup CLIP encodes all prompts once. Per image, CLIP encodes the image and picks the highest cosine-similarity category. If score/margin is below `TBCC_CLIP_MIN_CONF` / `TBCC_CLIP_MIN_MARGIN`, an optional vision LLM (`TBCC_VISION_LLM_PROVIDER=openrouter|openai|ollama`) fills the gap.

Same pipeline feeds: watch-folder subfolders, dashboard import tags, extension Saved Messages hashtags.

Optional custom clone paths:

```env
TBCC_NSFW_DETECT_DIR=C:\path\to\NSFW_Detection_API
TBCC_LUSTPRESS_DIR=C:\path\to\lustpress
```
