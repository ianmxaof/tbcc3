"""
Local CLIP zero-shot categorizer for TBCC (OpenCLIP ViT-B/32).

Loads a fixed category catalog (JSON / txt / slugs) and scores images by cosine
similarity between image embedding and precomputed text embeddings.

Env:
  TBCC_CLIP_CATEGORIES_FILE — path to category catalog (required for /classify)
  TBCC_CLIP_PROMPT_TEMPLATE — default: "a photo of {label}"
  TBCC_CLIP_TEXT_BATCH — batch size when encoding catalog (default 64)
  TBCC_CLIP_EMBED_CACHE — optional path to npz cache (auto beside categories file)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

logger = logging.getLogger(__name__)

app = FastAPI(title="TBCC CLIP Categorizer", version="1.0")

_model = None
_preprocess = None
_tokenizer = None
_device = "cpu"
_categories: list[dict[str, Any]] = []
_text_features: Any = None  # torch.Tensor [N, D]
_catalog_hash = ""
_loaded_at = 0.0


def _prompt_template() -> str:
    return (os.getenv("TBCC_CLIP_PROMPT_TEMPLATE") or "a photo of {label}").strip()


def _slugify(raw: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", (raw or "").strip().lower()).strip("-")
    return (s[:64] or "other") if s else "other"


def _label_for_entry(entry: dict[str, Any]) -> str:
    prompts = entry.get("prompts")
    if isinstance(prompts, list) and prompts:
        return str(prompts[0]).strip()
    name = str(entry.get("name") or entry.get("slug") or "").strip()
    return name or "other"


def load_categories_from_path(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    raw = path.read_text(encoding="utf-8-sig").strip()
    out: list[dict[str, Any]] = []
    if raw.startswith("[") or raw.startswith("{"):
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("categories"), list):
            data = data["categories"]
        if not isinstance(data, list):
            raise ValueError("JSON catalog must be an array or {categories: [...]}")
        for item in data:
            if isinstance(item, str):
                slug = _slugify(item)
                out.append({"slug": slug, "name": item.strip(), "prompts": [item.strip()]})
            elif isinstance(item, dict):
                slug = _slugify(str(item.get("slug") or item.get("name") or ""))
                name = str(item.get("name") or slug).strip()
                prompts = item.get("prompts")
                if not isinstance(prompts, list) or not prompts:
                    prompts = [name]
                group = str(item.get("group") or item.get("category") or "").strip() or None
                out.append({"slug": slug, "name": name, "prompts": [str(p).strip() for p in prompts if str(p).strip()], "group": group})
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            slug = _slugify(line.split(",")[0].split("|")[0])
            out.append({"slug": slug, "name": line, "prompts": [line]})
    # dedupe by slug (first wins)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for e in out:
        if e["slug"] in seen:
            continue
        seen.add(e["slug"])
        deduped.append(e)
    return deduped


def _catalog_file() -> Path | None:
    raw = (os.getenv("TBCC_CLIP_CATEGORIES_FILE") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _cache_path(catalog_path: Path) -> Path:
    env = (os.getenv("TBCC_CLIP_EMBED_CACHE") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return catalog_path.with_suffix(catalog_path.suffix + ".clip_embeddings.npz")


def _ensure_model():
    global _model, _preprocess, _tokenizer, _device
    if _model is not None:
        return
    import torch
    import open_clip

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    _model, _, _preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="openai", force_quick_gelu=True
    )
    _tokenizer = open_clip.get_tokenizer("ViT-B-32")
    _model = _model.to(_device)
    _model.eval()
    logger.info("CLIP ViT-B-32 loaded on %s", _device)


def _encode_text_batch(texts: list[str]):
    import torch

    tokens = _tokenizer(texts).to(_device)
    with torch.no_grad():
        feats = _model.encode_text(tokens)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats.cpu().numpy()


def _build_text_features(categories: list[dict[str, Any]]) -> np.ndarray:
    tmpl = _prompt_template()
    texts = [tmpl.format(label=_label_for_entry(c)) for c in categories]
    batch = max(8, min(int(os.getenv("TBCC_CLIP_TEXT_BATCH") or "64"), 256))
    chunks: list[np.ndarray] = []
    for i in range(0, len(texts), batch):
        chunks.append(_encode_text_batch(texts[i : i + batch]))
    return np.vstack(chunks) if chunks else np.zeros((0, 512), dtype=np.float32)


def reload_catalog(force: bool = False) -> dict[str, Any]:
    global _categories, _text_features, _catalog_hash, _loaded_at
    path = _catalog_file()
    if not path:
        _categories = []
        _text_features = None
        _catalog_hash = ""
        return {"ok": False, "error": "TBCC_CLIP_CATEGORIES_FILE not set", "count": 0}
    _ensure_model()
    categories = load_categories_from_path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    cache = _cache_path(path)
    feats: np.ndarray | None = None
    if cache.is_file() and not force:
        try:
            npz = np.load(cache, allow_pickle=False)
            if str(npz.get("catalog_hash", "")) == digest and int(npz.get("count", 0)) == len(categories):
                feats = np.array(npz["text_features"], dtype=np.float32)
                logger.info("Loaded CLIP text embeddings cache (%s categories)", len(categories))
        except Exception as e:
            logger.warning("CLIP embed cache read failed: %s", e)
    if feats is None:
        t0 = time.time()
        feats = _build_text_features(categories)
        logger.info("Encoded %s CLIP text prompts in %.1fs", len(categories), time.time() - t0)
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(cache, text_features=feats, catalog_hash=digest, count=len(categories))
        except Exception as e:
            logger.warning("CLIP embed cache write failed: %s", e)
    _categories = categories
    _text_features = feats
    _catalog_hash = digest
    _loaded_at = time.time()
    return {"ok": True, "count": len(categories), "catalog_hash": digest, "path": str(path)}


def classify_pil(image: Image.Image, *, top_k: int = 5) -> dict[str, Any]:
    import torch

    if not _categories or _text_features is None or len(_categories) == 0:
        return {"ok": False, "error": "catalog_empty", "labels": []}
    _ensure_model()
    if image.mode != "RGB":
        image = image.convert("RGB")
    tensor = _preprocess(image).unsqueeze(0).to(_device)
    with torch.no_grad():
        img_feat = _model.encode_image(tensor)
        img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
        img_np = img_feat.cpu().numpy()[0]
    scores = np.dot(_text_features, img_np)
    # softmax for readable probabilities
    exp = np.exp(scores - scores.max())
    probs = exp / exp.sum()
    k = min(max(1, top_k), len(_categories))
    idx = np.argpartition(-probs, k - 1)[:k]
    idx = idx[np.argsort(-probs[idx])]
    labels = []
    for i in idx:
        c = _categories[int(i)]
        labels.append(
            {
                "slug": c["slug"],
                "name": c.get("name") or c["slug"],
                "group": c.get("group"),
                "score": float(probs[int(i)]),
                "raw_score": float(scores[int(i)]),
            }
        )
    top = labels[0] if labels else None
    gap = 0.0
    if len(labels) >= 2:
        gap = float(labels[0]["score"] - labels[1]["score"])
    return {
        "ok": True,
        "top_slug": top["slug"] if top else None,
        "top_score": top["score"] if top else 0.0,
        "margin": gap,
        "labels": labels,
        "catalog_count": len(_categories),
    }


def embed_pil(image: Image.Image) -> list[float]:
    """L2-normalized CLIP image embedding — same encode_image path as classify_pil,
    no catalog required (gatekeeper prototype bank consumes this, not the 1260-slug
    catalog scores)."""
    import torch

    _ensure_model()
    if image.mode != "RGB":
        image = image.convert("RGB")
    tensor = _preprocess(image).unsqueeze(0).to(_device)
    with torch.no_grad():
        img_feat = _model.encode_image(tensor)
        img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
        img_np = img_feat.cpu().numpy()[0]
    return [float(v) for v in img_np]


@app.on_event("startup")
def _startup():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    reload_catalog(force=False)


@app.get("/health")
def health():
    return {
        "ok": bool(_categories),
        "categories": len(_categories),
        "catalog_hash": _catalog_hash,
        "device": _device,
        "loaded_at": _loaded_at,
    }


@app.post("/reload")
def reload_endpoint():
    return reload_catalog(force=True)


@app.post("/classify")
async def classify_upload(file: UploadFile = File(...), top_k: int = 5):
    try:
        raw = await file.read()
        if not raw or len(raw) < 32:
            raise HTTPException(status_code=400, detail="empty file")
        image = Image.open(BytesIO(raw))
        return classify_pil(image, top_k=min(top_k, 20))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("classify failed")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.post("/classify-path")
def classify_path(body: dict):
    """Classify image at local path (same machine as sidecar)."""
    p = str(body.get("path") or "").strip()
    if not p:
        raise HTTPException(status_code=400, detail="path required")
    path = Path(p)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    try:
        image = Image.open(path)
        top_k = int(body.get("top_k") or 5)
        return classify_pil(image, top_k=min(top_k, 20))
    except Exception as e:
        logger.exception("classify-path failed")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.post("/embed")
async def embed_upload(file: UploadFile = File(...)):
    """Raw CLIP image embedding for the gatekeeper prototype bank — no catalog needed."""
    try:
        raw = await file.read()
        if not raw or len(raw) < 32:
            raise HTTPException(status_code=400, detail="empty file")
        image = Image.open(BytesIO(raw))
        vec = embed_pil(image)
        return {"ok": True, "dim": len(vec), "embedding": vec}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("embed failed")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.post("/embed-path")
def embed_path(body: dict):
    """Embed image at local path (same machine as sidecar)."""
    p = str(body.get("path") or "").strip()
    if not p:
        raise HTTPException(status_code=400, detail="path required")
    path = Path(p)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    try:
        image = Image.open(path)
        vec = embed_pil(image)
        return {"ok": True, "dim": len(vec), "embedding": vec}
    except Exception as e:
        logger.exception("embed-path failed")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
