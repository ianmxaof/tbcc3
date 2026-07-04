"""Keep2Share API v2 client — partner access_token or user login auth.

Docs: https://keep2share.github.io/api/
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

K2S_HOST_MARKERS: tuple[str, ...] = (
    "keep2share.cc",
    "k2s.cc",
    "tezfiles.com",
    "fboom.me",
)

_K2S_ID_RE = re.compile(r"/(?:file|folder)/([a-f0-9]{10,16})", re.I)

_cached_auth_token: str | None = None
_cached_auth_at: float = 0.0


@dataclass
class K2sFileStatus:
    ok: bool
    file_id: str
    is_available: bool
    is_folder: bool
    name: str | None
    size: int | None
    access: str | None
    error: str | None = None


@dataclass
class K2sRemoteUpload:
    ok: bool
    remote_id: str | None
    file_id: str | None
    public_url: str | None
    error: str | None = None


class K2sNotConfiguredError(RuntimeError):
    pass


def k2s_enabled() -> bool:
    return (os.getenv("TBCC_K2S_ENABLED") or "0").strip().lower() in ("1", "true", "yes", "on")


def k2s_configured() -> bool:
    if not k2s_enabled():
        return False
    if (os.getenv("TBCC_K2S_ACCESS_TOKEN") or "").strip():
        return True
    if (os.getenv("TBCC_K2S_EMAIL") or "").strip() and (os.getenv("TBCC_K2S_PASSWORD") or "").strip():
        return True
    return bool(_cached_auth_token)


def is_k2s_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(m in host for m in K2S_HOST_MARKERS)


def parse_k2s_file_id(url: str) -> str | None:
    m = _K2S_ID_RE.search(url or "")
    return m.group(1) if m else None


def k2s_partner_id() -> str | None:
    raw = (os.getenv("TBCC_K2S_PARTNER_ID") or os.getenv("TBCC_K2S_AFFILIATE_ID") or "").strip()
    return raw or None


def k2s_partner_referral_urls() -> dict[str, str]:
    """Partner /pr/ landing pages (k2s, fboom, tezfiles)."""
    pid = k2s_partner_id()
    if not pid:
        return {}
    return {
        "k2s.cc": f"https://k2s.cc/pr/{pid}",
        "fboom.me": f"https://fboom.me/pr/{pid}",
        "tezfiles.com": f"https://tezfiles.com/pr/{pid}",
    }


def public_file_url(file_id: str) -> str:
    domain = (os.getenv("TBCC_K2S_PUBLIC_DOMAIN") or "k2s.cc").strip().lstrip(".")
    fid = (file_id or "").strip()
    return f"https://{domain}/file/{fid}"


def _api_base() -> str:
    return (os.getenv("TBCC_K2S_API_BASE") or "https://keep2share.cc/api/v2").rstrip("/")


def _timeout_s() -> float:
    try:
        return max(5.0, float(os.getenv("TBCC_K2S_TIMEOUT_S", "45")))
    except ValueError:
        return 45.0


def _auth_cache_ttl_s() -> float:
    try:
        return max(300.0, float(os.getenv("TBCC_K2S_AUTH_CACHE_SEC", "3600")))
    except ValueError:
        return 3600.0


def _secured_payload(extra: dict[str, Any]) -> dict[str, Any]:
    access = (os.getenv("TBCC_K2S_ACCESS_TOKEN") or "").strip()
    if access:
        return {**extra, "access_token": access}
    global _cached_auth_token, _cached_auth_at
    if _cached_auth_token and (time.time() - _cached_auth_at) < _auth_cache_ttl_s():
        return {**extra, "auth_token": _cached_auth_token}
    email = (os.getenv("TBCC_K2S_EMAIL") or "").strip()
    password = (os.getenv("TBCC_K2S_PASSWORD") or "").strip()
    if not email or not password:
        raise K2sNotConfiguredError("Set TBCC_K2S_ACCESS_TOKEN or TBCC_K2S_EMAIL+TBCC_K2S_PASSWORD")
    recaptcha = (os.getenv("TBCC_K2S_RECAPTCHA") or "").strip() or None
    body: dict[str, Any] = {"username": email, "password": password}
    if recaptcha:
        body["reCaptcha"] = recaptcha
    data = _post("login", body, secured=False)
    token = str(data.get("auth_token") or "").strip()
    if not token:
        raise K2sNotConfiguredError(data.get("message") or "k2s_login_failed")
    _cached_auth_token = token
    _cached_auth_at = time.time()
    return {**extra, "auth_token": token}


def _post(method: str, payload: dict[str, Any], *, secured: bool = True) -> dict[str, Any]:
    url = f"{_api_base()}/{method.lstrip('/')}"
    body = _secured_payload(payload) if secured else payload
    try:
        with httpx.Client(timeout=_timeout_s()) as client:
            r = client.post(url, json=body)
        data = r.json() if r.content else {}
    except Exception as e:
        logger.warning("k2s %s request error: %s", method, e)
        return {"status": "error", "message": str(e)}
    if not isinstance(data, dict):
        return {"status": "error", "message": "invalid_json"}
    return data


def _success(data: dict[str, Any]) -> bool:
    return str(data.get("status") or "").lower() == "success"


def get_file_status(file_id: str) -> K2sFileStatus:
    """Public liveness probe — auth optional per API docs."""
    fid = (file_id or "").strip()
    if not fid:
        return K2sFileStatus(
            ok=False,
            file_id=fid,
            is_available=False,
            is_folder=False,
            name=None,
            size=None,
            access=None,
            error="missing_id",
        )
    data = _post("getFileStatus", {"id": fid}, secured=False)
    if not _success(data):
        return K2sFileStatus(
            ok=False,
            file_id=fid,
            is_available=False,
            is_folder=False,
            name=None,
            size=None,
            access=None,
            error=str(data.get("message") or "status_error"),
        )
    files = data.get("files")
    if isinstance(files, dict):
        row = files
    elif isinstance(files, list) and files:
        row = files[0] if isinstance(files[0], dict) else {}
    else:
        row = data
    is_available = bool(row.get("is_available", data.get("is_available", False)))
    is_folder = bool(row.get("is_folder", data.get("is_folder", False)))
    return K2sFileStatus(
        ok=is_available,
        file_id=str(row.get("id") or fid),
        is_available=is_available,
        is_folder=is_folder,
        name=(row.get("name") or data.get("name")),
        size=row.get("size") or data.get("size"),
        access=row.get("access") or data.get("access"),
    )


def check_url_alive(url: str) -> tuple[bool, str | None]:
    """Dead-link check for K2S public URLs via getFileStatus."""
    fid = parse_k2s_file_id(url)
    if not fid:
        return False, "invalid_k2s_url"
    st = get_file_status(fid)
    if not st.is_available:
        return False, st.error or "unavailable"
    return True, None


def get_direct_download_url(file_id: str) -> tuple[str | None, str | None]:
    """VIP direct temp URL via getUrl (requires auth)."""
    if not k2s_configured():
        return None, "not_configured"
    fid = (file_id or "").strip()
    if not fid:
        return None, "missing_id"
    data = _post("getUrl", {"file_id": fid})
    if not _success(data):
        return None, str(data.get("message") or "getUrl_failed")
    url = str(data.get("url") or "").strip()
    return (url, None) if url.startswith("http") else (None, "empty_url")


def remote_upload_add(urls: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    if not k2s_configured():
        raise K2sNotConfiguredError("k2s_not_configured")
    clean = [u.strip() for u in urls if (u or "").strip().startswith("http")]
    if not clean:
        return [], ["no_urls"]
    data = _post("remoteUploadAdd", {"urls": clean})
    if not _success(data):
        raise RuntimeError(str(data.get("message") or "remote_upload_add_failed"))
    accepted = []
    for row in data.get("acceptedUrls") or []:
        if isinstance(row, dict) and row.get("id"):
            accepted.append({"url": str(row.get("url") or ""), "id": str(row["id"])})
    rejected = [str(x) for x in (data.get("rejectedUrls") or [])]
    return accepted, rejected


def remote_upload_status(remote_ids: list[str]) -> list[dict[str, Any]]:
    if not remote_ids:
        return []
    data = _post("remoteUploadStatus", {"ids": remote_ids})
    if not _success(data):
        return []
    out: list[dict[str, Any]] = []
    for row in data.get("uploads") or []:
        if isinstance(row, dict):
            out.append(row)
    return out


def wait_remote_upload(
    remote_id: str,
    *,
    poll_sec: float | None = None,
    max_wait_sec: float | None = None,
) -> K2sRemoteUpload:
    rid = (remote_id or "").strip()
    if not rid:
        return K2sRemoteUpload(ok=False, remote_id=None, file_id=None, public_url=None, error="missing_remote_id")
    poll = poll_sec if poll_sec is not None else float(os.getenv("TBCC_K2S_MIRROR_POLL_SEC", "20"))
    max_wait = max_wait_sec if max_wait_sec is not None else float(os.getenv("TBCC_K2S_MIRROR_MAX_WAIT_SEC", "7200"))
    deadline = time.time() + max(30.0, max_wait)
    while time.time() < deadline:
        rows = remote_upload_status([rid])
        row = rows[0] if rows else {}
        status = int(row.get("status") or 0)
        file_id = str(row.get("file_id") or "").strip() or None
        if status == 3 and file_id:
            return K2sRemoteUpload(
                ok=True,
                remote_id=rid,
                file_id=file_id,
                public_url=public_file_url(file_id),
            )
        if status in (4, 5):
            return K2sRemoteUpload(
                ok=False,
                remote_id=rid,
                file_id=file_id,
                public_url=None,
                error=f"remote_status_{status}",
            )
        time.sleep(max(5.0, poll))
    return K2sRemoteUpload(ok=False, remote_id=rid, file_id=None, public_url=None, error="timeout")


def create_folder(name: str, *, parent: str = "/") -> str | None:
    data = _post(
        "createFolder",
        {
            "name": name[:120],
            "parent": parent or "/",
            "access": "public",
            "is_public": True,
        },
    )
    if not _success(data):
        logger.warning("k2s createFolder failed: %s", data.get("message"))
        return None
    fid = str(data.get("id") or "").strip()
    return fid or None


def get_folders_list(*, parent_id: str | None = None) -> list[dict[str, Any]]:
    body: dict[str, Any] = {}
    if parent_id:
        body["parent_id"] = parent_id
    data = _post("getFoldersList", body)
    if not _success(data):
        return []
    names = data.get("foldersList") or []
    ids = data.get("foldersIds") or []
    out: list[dict[str, Any]] = []
    for name, fid in zip(names, ids):
        out.append({"name": str(name), "id": str(fid)})
    return out


def get_files_list(
    *,
    parent: str = "/",
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    data = _post(
        "getFilesList",
        {
            "parent": parent,
            "limit": max(1, min(int(limit), 500)),
            "offset": max(0, int(offset)),
            "sort": {"date_created": -1},
        },
    )
    if not _success(data):
        return []
    files = data.get("files") or []
    return [f for f in files if isinstance(f, dict)]


def move_files_to_folder(file_ids: list[str], folder_id: str) -> bool:
    if not file_ids or not folder_id:
        return False
    data = _post(
        "updateFiles",
        {
            "ids": file_ids,
            "new_parent": folder_id,
            "new_access": "public",
            "new_is_public": True,
        },
    )
    return _success(data)
