"""
Launch TBCC CLIP categorizer on port 8002 (default).

Usage (from tbcc/services):
  py -3.13 run_clip_categorize.py

Requires TBCC_CLIP_CATEGORIES_FILE in tbcc/.env or environment.
"""
from __future__ import annotations

import logging
import os
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
tbcc_dir = ROOT.parent
env_file = tbcc_dir / ".env"

if env_file.is_file():
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
    except ImportError:
        pass

# Hugging Face Hub accepts HF_TOKEN; dotenv may use the longer alias.
if not (os.getenv("HF_TOKEN") or "").strip():
    hub_token = (os.getenv("HUGGINGFACE_HUB_TOKEN") or "").strip()
    if hub_token:
        os.environ["HF_TOKEN"] = hub_token

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*", category=UserWarning)

port_raw = os.getenv("TBCC_CLIP_CATEGORIZE_PORT") or os.getenv("TBCC_CLIP_PORT") or "8002"
port = int(port_raw)

if __name__ == "__main__":
    import uvicorn

    print(f"TBCC CLIP categorizer on http://127.0.0.1:{port}/  (TBCC_CLIP_CATEGORIZE_URL)")
    uvicorn.run("clip_categorize_app:app", host="127.0.0.1", port=port, log_level="info")
