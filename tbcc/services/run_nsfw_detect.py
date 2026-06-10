"""
Launch NSFW_Detection_API on the port TBCC expects (default 8001, not upstream 8000).

Usage (from tbcc/services):
  py -3.13 run_nsfw_detect.py
"""
from __future__ import annotations

import logging
import os
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "NSFW_Detection_API"
if not ROOT.is_dir():
    raise SystemExit(f"Missing clone: {ROOT}\nSee services/README.md")

sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# nsfw_model.h5 was trained with Keras 2 / tf.keras; TF 2.16+ default Keras 3 breaks hub.KerasLayer load.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
# Quiet TensorFlow C++/Python startup noise (oneDNN, cpu_feature_guard, deprecation spam).
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

# tensorflow-hub imports pkg_resources (setuptools); setuptools 81+ drops it on Py3.13
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        import pkg_resources  # noqa: F401
except ModuleNotFoundError:
    raise SystemExit(
        "Missing pkg_resources (setuptools). Fix:\n"
        "  py -3.13 -m pip install \"setuptools>=70,<81\"\n"
        "Or re-run: cd tbcc\\services ; .\\setup-enrichment.ps1"
    ) from None

logging.getLogger("tensorflow").setLevel(logging.ERROR)
logging.getLogger("tensorflow_hub").setLevel(logging.ERROR)

import config  # noqa: E402

port_raw = (
    os.getenv("TBCC_NSFW_DETECT_PORT")
    or os.getenv("NSFW_DETECT_PORT")
    or "8001"
)
config.PORT = int(port_raw)

# Registers route + loads model (side effect of importing __main__)
import api.__main__  # noqa: E402, F401

import uvicorn  # noqa: E402

if __name__ == "__main__":
    print(f"NSFW Detection API on http://127.0.0.1:{config.PORT}/  (TBCC_NSFW_DETECT_URL)")
    uvicorn.run("api:app", host="127.0.0.1", port=config.PORT, log_level="info")
