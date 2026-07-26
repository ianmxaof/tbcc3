"""Upload media to Cloudflare R2 (aof-media bucket) or ImgBB.

Canonical layout under ``TBCC_R2_BUCKET`` (default ``aof-media``):

- ``library/`` — general AOF library media
- ``sfw-x-promo/`` — SFW X promo pool images (legacy ``x-promo/`` maps here)
"""

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

# destination id → object-key prefix
DEST_PREFIXES: dict[str, str] = {
    "library": "library",
    "sfw_x_promo": "sfw-x-promo",
    "sfw-x-promo": "sfw-x-promo",
    "x-promo": "sfw-x-promo",  # legacy alias
    "x_promo": "sfw-x-promo",
}

DEFAULT_DESTINATION = "sfw_x_promo"
DEFAULT_PREFIX = "sfw-x-promo"


def r2_config() -> dict[str, str] | None:
    token = (os.getenv("TBCC_CF_API_TOKEN") or os.getenv("TBCC_CLOUDFLARE_API_TOKEN") or "").strip()
    account_id = (os.getenv("TBCC_R2_ACCOUNT_ID") or "").strip()
    bucket = (os.getenv("TBCC_R2_BUCKET") or "aof-media").strip()
    public_base = (os.getenv("TBCC_R2_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    access_key = (os.getenv("TBCC_R2_ACCESS_KEY_ID") or "").strip()
    secret_key = (os.getenv("TBCC_R2_SECRET_ACCESS_KEY") or "").strip()
    s3_endpoint = (os.getenv("TBCC_R2_S3_ENDPOINT") or "").strip().rstrip("/")
    if not account_id or not public_base:
        return None
    if not token and not (access_key and secret_key):
        return None
    if not s3_endpoint and account_id:
        s3_endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    return {
        "token": token,
        "account_id": account_id,
        "bucket": bucket,
        "public_base": public_base,
        "access_key": access_key,
        "secret_key": secret_key,
        "s3_endpoint": s3_endpoint,
    }


def imgbb_api_key() -> str:
    return (os.getenv("TBCC_IMGBB_API_KEY") or "").strip()


def pool_json_path() -> Path:
    override = (os.getenv("TBCC_X_PROMO_IMAGE_POOL_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "data" / "aof_x_promo_image_pool.json"


def resolve_prefix(destination: str | None = None, *, prefix: str | None = None) -> str:
    """Normalize destination id or raw prefix to a folder segment (no trailing slash)."""
    if prefix is not None and str(prefix).strip():
        raw = str(prefix).strip().strip("/")
        return DEST_PREFIXES.get(raw, DEST_PREFIXES.get(raw.replace("-", "_"), raw)) or DEFAULT_PREFIX
    dest = (destination or DEFAULT_DESTINATION).strip().lower().replace("-", "_")
    if dest not in DEST_PREFIXES and dest.replace("_", "-") in DEST_PREFIXES:
        dest = dest.replace("_", "-")
    mapped = DEST_PREFIXES.get(dest) or DEST_PREFIXES.get((destination or "").strip().lower())
    if mapped:
        return mapped
    raise ValueError(
        f"Unknown R2 destination {destination!r}; expected one of: "
        + ", ".join(sorted({k for k in ("library", "sfw_x_promo")}))
    )


def sanitize_object_filename(filename: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", (filename or "").strip()).strip("-")
    return safe or "image.jpg"


def _object_key(filename: str, *, prefix: str = DEFAULT_PREFIX) -> str:
    safe = sanitize_object_filename(filename)
    return f"{prefix.strip('/')}/{safe}"


def object_key_for_destination(
    filename: str,
    *,
    destination: str | None = None,
    prefix: str | None = None,
) -> str:
    return _object_key(filename, prefix=resolve_prefix(destination, prefix=prefix))


def public_url_for_key(public_base: str, object_key: str) -> str:
    base = public_base.rstrip("/")
    return f"{base}/{quote(object_key, safe='/')}"


def _upload_bytes_to_r2_s3(
    data: bytes,
    *,
    object_key: str,
    content_type: str,
    cfg: dict[str, str],
    timeout: float,
) -> None:
    """S3-compatible PutObject (R2 access key) — preferred when CF API token lacks R2 edit."""
    import datetime as _dt
    import hashlib
    import hmac

    access = cfg["access_key"]
    secret = cfg["secret_key"]
    endpoint = cfg["s3_endpoint"].rstrip("/")
    bucket = cfg["bucket"]
    region = "auto"
    host = endpoint.replace("https://", "").replace("http://", "")
    amz_date = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    datestamp = amz_date[:8]
    payload_hash = hashlib.sha256(data).hexdigest()
    canonical_uri = f"/{bucket}/{quote(object_key, safe='/')}"
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        ["PUT", canonical_uri, "", canonical_headers, signed_headers, payload_hash]
    )
    credential_scope = f"{datestamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k_date = _sign(("AWS4" + secret).encode("utf-8"), datestamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, "s3")
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    auth = (
        f"AWS4-HMAC-SHA256 Credential={access}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    url = f"{endpoint}{canonical_uri}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.put(
            url,
            content=data,
            headers={
                "Content-Type": content_type,
                "Host": host,
                "x-amz-content-sha256": payload_hash,
                "x-amz-date": amz_date,
                "Authorization": auth,
            },
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"R2 S3 upload failed {resp.status_code}: {(resp.text or '')[:400]}")


def upload_bytes_to_r2(
    data: bytes,
    *,
    filename: str,
    destination: str | None = None,
    prefix: str | None = None,
    object_key: str | None = None,
    content_type: str | None = None,
    timeout: float = 120.0,
) -> dict[str, str]:
    cfg = r2_config()
    if not cfg:
        raise ValueError(
            "R2 not configured — set TBCC_R2_ACCOUNT_ID + TBCC_R2_PUBLIC_BASE_URL and either "
            "TBCC_R2_ACCESS_KEY_ID/SECRET or TBCC_CF_API_TOKEN (and optionally TBCC_R2_BUCKET=aof-media)"
        )
    if not data or len(data) < 200:
        raise ValueError("File too small or empty")
    key = object_key or object_key_for_destination(filename, destination=destination, prefix=prefix)
    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # Prefer S3 access keys (reliable for object PUT). CF API token often lacks R2 write.
    if cfg.get("access_key") and cfg.get("secret_key") and cfg.get("s3_endpoint"):
        _upload_bytes_to_r2_s3(data, object_key=key, content_type=mime, cfg=cfg, timeout=timeout)
        return {
            "direct_url": public_url_for_key(cfg["public_base"], key),
            "object_key": key,
            "provider": "r2_s3",
            "bucket": cfg["bucket"],
        }

    if not cfg.get("token"):
        raise ValueError("R2 S3 keys missing and TBCC_CF_API_TOKEN unset")

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
    return {
        "direct_url": direct,
        "object_key": key,
        "provider": "r2",
        "bucket": cfg["bucket"],
    }


def upload_to_r2(
    path: Path,
    *,
    object_key: str | None = None,
    destination: str | None = None,
    prefix: str | None = None,
    timeout: float = 120.0,
) -> dict[str, str]:
    data = path.read_bytes()
    return upload_bytes_to_r2(
        data,
        filename=path.name,
        destination=destination,
        prefix=prefix,
        object_key=object_key,
        timeout=timeout,
    )


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
        return upload_to_r2(path, destination=DEFAULT_DESTINATION)
    if prov == "imgbb":
        return upload_to_imgbb(path)
    if r2_config():
        return upload_to_r2(path, destination=DEFAULT_DESTINATION)
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
