"""Upload SFW X promo images to Cloudflare R2 (public bucket) or ImgBB."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def r2_config() -> dict[str, str] | None:
    token = (os.getenv("TBCC_CF_API_TOKEN") or os.getenv("TBCC_CLOUDFLARE_API_TOKEN") or "").strip()
    account_id = (os.getenv("TBCC_R2_ACCOUNT_ID") or "").strip()
    bucket = (os.getenv("TBCC_R2_BUCKET") or "aof-x-promo").strip()
    public_base = (os.getenv("TBCC_R2_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not token or not account_id or not public_base:
        return None
    return {
        "token": token,
        "account_id": account_id,
        "bucket": bucket,
        "public_base": public_base,
    }


def imgbb_api_key() -> str:
    return (os.getenv("TBCC_IMGBB_API_KEY") or "").strip()


def pool_json_path() -> Path:
    override = (os.getenv("TBCC_X_PROMO_IMAGE_POOL_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "data" / "aof_x_promo_image_pool.json"


def _object_key(filename: str, *, prefix: str = "x-promo") -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", filename).strip("-") or "image.jpg"
    return f"{prefix.strip('/')}/{safe}"


def public_url_for_key(public_base: str, object_key: str) -> str:
    base = public_base.rstrip("/")
    return f"{base}/{quote(object_key, safe='/')}"


def upload_to_r2(path: Path, *, object_key: str | None = None, timeout: float = 120.0) -> dict[str, str]:
    cfg = r2_config()
    if not cfg:
        raise ValueError(
            "R2 not configured — set TBCC_CF_API_TOKEN, TBCC_R2_ACCOUNT_ID, TBCC_R2_PUBLIC_BASE_URL "
            "(and optionally TBCC_R2_BUCKET)"
        )
    data = path.read_bytes()
    if len(data) < 200:
        raise ValueError(f"File too small or empty: {path}")
    key = object_key or _object_key(path.name)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{cfg['account_id']}"
        f"/r2/buckets/{cfg['bucket']}/objects/{quote(key, safe='')}"
    )
    with httpx.Client(timeout=timeout) as client:
        resp = client.put(
            url,
            content=data,
            headers={
                "Authorization": f"Bearer {cfg['token']}",
                "Content-Type": mime,
            },
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"R2 upload failed {resp.status_code}: {(resp.text or '')[:400]}")
    direct = public_url_for_key(cfg["public_base"], key)
    return {"direct_url": direct, "object_key": key, "provider": "r2"}


def upload_to_imgbb(path: Path, *, timeout: float = 120.0) -> dict[str, str]:
    key = imgbb_api_key()
    if not key:
        raise ValueError("TBCC_IMGBB_API_KEY not set")
    data = path.read_bytes()
    if len(data) < 200:
        raise ValueError(f"File too small or empty: {path}")
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            "https://api.imgbb.com/1/upload",
            data={"key": key},
            files={"image": (path.name, data, mimetypes.guess_type(path.name)[0] or "image/jpeg")},
        )
    body = resp.json() if resp.content else {}
    if not body.get("success"):
        raise RuntimeError(f"ImgBB upload failed: {body}")
    row = body.get("data") or {}
    direct = str(row.get("url") or (row.get("image") or {}).get("url") or "").strip()
    if not direct.startswith("https://"):
        raise RuntimeError(f"ImgBB response missing direct url: {body}")
    viewer = str(row.get("url_viewer") or "").strip() or None
    out: dict[str, str] = {"direct_url": direct, "provider": "imgbb"}
    if viewer:
        out["viewer_url"] = viewer
    return out


def upload_promo_image(path: Path, *, provider: str = "auto") -> dict[str, str]:
    prov = (provider or "auto").strip().lower()
    if prov == "r2":
        return upload_to_r2(path)
    if prov == "imgbb":
        return upload_to_imgbb(path)
    if r2_config():
        return upload_to_r2(path)
    if imgbb_api_key():
        return upload_to_imgbb(path)
    raise ValueError("No upload provider — configure R2 or TBCC_IMGBB_API_KEY")


def load_pool_entries() -> list[dict[str, str]]:
    path = pool_json_path()
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("images") or data.get("entries") or []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        direct = str(row.get("direct_url") or row.get("url") or "").strip()
        if not direct.startswith("https://") or "example.com" in direct:
            continue
        entry: dict[str, str] = {"direct_url": direct}
        label = str(row.get("label") or "").strip()
        if label:
            entry["label"] = label
        viewer = str(row.get("viewer_url") or "").strip()
        if viewer.startswith("https://"):
            entry["viewer_url"] = viewer
        out.append(entry)
    return out


def append_pool_entries(new_entries: list[dict[str, str]], *, dry_run: bool = False) -> Path:
    path = pool_json_path()
    existing = load_pool_entries()
    seen = {e["direct_url"] for e in existing}
    merged = list(existing)
    for entry in new_entries:
        direct = str(entry.get("direct_url") or "").strip()
        if not direct.startswith("https://") or direct in seen:
            continue
        seen.add(direct)
        merged.append(entry)
    if dry_run:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return path


def iter_image_paths(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")
    paths = [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in _IMAGE_EXT]
    return paths
