"""PC-local registry of arbitrary REST API "slots" (API Pocket, Phase 0).

Operator loads a key (+ optional base URL) via clipboard or CLI; suggest_slot()
classifies it, add_slot() persists it to tbcc/.tbcc-run/api_slot_registry.sqlite3
(gitignored, same posture as llm_model_index.py), and call_slot() forwards a
generic HTTP request using stored auth — no per-vendor SDK codegen needed to
make a freshly-loaded key immediately callable.

Reuses tbcc_env_secret_store.suggest_env_key/normalize_env_key so the same
key gets the same env var name whether it lands here or in the plain .env
capture path.

PC-local only, like llm_model_index.py: this file lives outside the island's
runtime and is never reachable in production. call_slot() resolves auth from
the process environment (tbcc/.env, loaded by load_tbcc_dotenv() at CLI/API
startup) — this module never writes .env itself; callers that also want a
plain env-file copy go through tbcc_env_secret_store.write_env_secret()
explicitly.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from app.services.tbcc_env_secret_store import normalize_env_key, suggest_env_key

AuthStyle = Literal["bearer", "x-api-key", "query", "form_api_dev_key", "none"]
Category = Literal["llm", "text-format", "media", "generic-rest"]

_VALID_AUTH_STYLES = ("bearer", "x-api-key", "query", "form_api_dev_key", "none")

_LLM_ENV_HINTS = (
    "OPENROUTER", "GEMINI", "CEREBRAS", "NVIDIA", "MISTRAL", "GROQ",
    "OPENAI", "ANTHROPIC", "DEEPINFRA", "FEATHERLESS", "VENICE", "HUGGINGFACE",
    "ORCAROUTER", "MOONSHOT", "KIMI",
)
_LLM_URL_HINTS = (
    "openrouter.ai", "openai.com", "anthropic.com", "cerebras.ai", "groq.com",
    "mistral.ai", "deepinfra.com", "huggingface.co", "venice.ai", "orcarouter.ai",
    "moonshot.ai", "kimi.ai",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    override = (os.getenv("TBCC_API_SLOT_DB") or "").strip()
    if override:
        return Path(override)
    # this file: tbcc/backend/app/services/api_slot_registry.py -> tbcc/.tbcc-run/
    tbcc_root = Path(__file__).resolve().parents[3]
    return tbcc_root / ".tbcc-run" / "api_slot_registry.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS slots (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            base_url TEXT,
            auth_env_key TEXT NOT NULL,
            auth_style TEXT NOT NULL DEFAULT 'bearer',
            openapi_url TEXT,
            method TEXT NOT NULL DEFAULT 'GET',
            path_template TEXT NOT NULL DEFAULT '',
            headers_json TEXT,
            added_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or "slot"


def split_endpoint(url: str) -> tuple[str, str]:
    """Split a full REST URL into (origin, path). Empty path when URL is origin-only.

    Pastebin operators often paste https://pastebin.com/api/api_post.php into
    the Endpoint field — storing that whole string as base_url then appending
    another path doubles the path. Origin + path_template is the pocket model.

    Do NOT strip OpenAI-style /v1 bases — those belong in base_url for LLM slots.
    """
    raw = (url or "").strip()
    if not raw:
        return "", ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    path = parsed.path or ""
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if path in ("", "/"):
        return origin, ""
    return origin, path


def _path_looks_like_rpc_file(path: str) -> bool:
    """True when the URL path is a concrete RPC file (Pastebin), not an API version root."""
    p = (path or "").lower()
    if p.endswith((".php", ".asp", ".aspx", ".jsp")):
        return True
    if "/api/api_" in p:
        return True
    return False


def _normalize_slot_base_and_path(base_url: str, path_template: str = "") -> tuple[str, str]:
    """Keep /v1 (and similar) on base_url; only peel file-style endpoints into path_template."""
    raw = (base_url or "").strip().rstrip("/")
    if path_template:
        return raw, path_template
    if not raw:
        return "", ""
    origin, split_path = split_endpoint(raw)
    if split_path and _path_looks_like_rpc_file(split_path):
        return origin, split_path
    return raw, ""


def _pastebin_preset(*, base_url: str, auth_env_key: str, slot_id: str) -> dict[str, Any] | None:
    blob = f"{base_url} {auth_env_key} {slot_id}".lower()
    if "pastebin" not in blob:
        return None
    origin, path = split_endpoint(base_url) if base_url else ("https://pastebin.com", "")
    if not origin or "pastebin.com" not in origin.lower():
        origin = "https://pastebin.com"
    if not path:
        path = "/api/api_post.php"
    return {
        "base_url": origin,
        "path_template": path,
        "method": "POST",
        "auth_style": "form_api_dev_key",
        "id": slot_id or "pastebin",
    }


def _shrinkme_preset(*, base_url: str, auth_env_key: str, slot_id: str) -> dict[str, Any] | None:
    blob = f"{base_url} {auth_env_key} {slot_id}".lower()
    if "shrinkme" not in blob and "shrinkmeio" not in blob.replace("_", ""):
        return None
    origin, path = split_endpoint(base_url) if base_url else ("https://shrinkme.io", "")
    if not origin:
        origin = "https://shrinkme.io"
    return {
        "base_url": origin,
        "path_template": path or "/api",
        "method": "GET",
        "auth_style": "query",
        "id": slot_id or "shrinkme",
    }


def _brand_label_from_host(url: str) -> str:
    """First DNS label that actually names the vendor — a bare "api" leading
    label (api.openrouter.ai) isn't a brand name, so it's dropped when a real
    second label is still left to use instead. Shared by both the slot-id and
    the fallback-env-key heuristics so they never diverge on the same host."""
    if not url:
        return ""
    host = urlparse(url).netloc or url
    host = re.sub(r"^www\.", "", host, flags=re.I)
    labels = host.split(".") if host else []
    if len(labels) > 2 and labels[0].lower() == "api":
        labels = labels[1:]
    return labels[0] if labels else ""


def _slot_id_from_hint(base_url: str, auth_env_key: str) -> str:
    label = _brand_label_from_host(base_url)
    if label:
        return _slugify(label)
    return _slugify(re.sub(r"_API(_KEY)?$", "", auth_env_key or ""))


def _unique_id(conn: sqlite3.Connection, base_id: str) -> str:
    candidate = base_id
    n = 2
    while conn.execute("SELECT 1 FROM slots WHERE id = ?", (candidate,)).fetchone():
        candidate = f"{base_id}-{n}"
        n += 1
    return candidate


def classify_category(*, auth_env_key: str = "", base_url: str = "") -> Category:
    key_u = (auth_env_key or "").upper()
    url_l = (base_url or "").lower()
    if any(h in key_u for h in _LLM_ENV_HINTS) or any(h in url_l for h in _LLM_URL_HINTS):
        return "llm"
    return "generic-rest"


def parse_slot_source(text: str) -> dict[str, str]:
    """Best-effort parse of pasted API onboarding material: a curl one-liner
    (-H 'Authorization: Bearer KEY' / '-H X-Api-Key: KEY' + a URL), multiline
    "{url}\\n{key}", or a bare key. Returns only the keys it actually found —
    callers fill gaps with suggest_env_key/classify_category."""
    raw = (text or "").strip()
    out: dict[str, str] = {}
    if not raw:
        return out

    curl_url = re.search(r"curl\s+.*?['\"]?(https?://[^\s'\"]+)", raw, re.I | re.S)
    curl_key = re.search(
        r"-H\s+['\"]?(?:Authorization:\s*Bearer\s+([^\s'\"]+)|X-Api-Key:\s*([^\s'\"]+))",
        raw,
        re.I,
    )
    if curl_key:
        out["key"] = curl_key.group(1) or curl_key.group(2)
        if curl_url:
            out["url"] = curl_url.group(1)
        return out

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    urls = [ln for ln in lines if re.match(r"^https?://", ln, re.I)]
    non_urls = [ln for ln in lines if ln not in urls]
    if urls:
        out["url"] = urls[0]
    if non_urls:
        out["key"] = non_urls[0]
    elif lines:
        out["key"] = lines[0]
    return out


def _fallback_env_key(url: str) -> str:
    label = _brand_label_from_host(url) or "GENERIC"
    return normalize_env_key(f"TBCC_{label}_API_KEY")


def suggest_slot(
    text: str, *, page_url: str = "", id_override: str = "", auth_env_key_override: str = ""
) -> dict[str, Any]:
    """Classify pasted text into a slot suggestion without persisting it.

    auth_env_key_override, when given, replaces auto-detection everywhere it
    matters — not just the returned auth_env_key, but also what category and
    id get derived FROM. Real bug this fixes: a caller could override
    auth_env_key (e.g. "TBCC_GITGIST_TOKEN") while leaving id blank, and the
    id would still be derived from the raw paste's OWN auto-detected key
    (e.g. a GitHub token prefix auto-suggesting "TBCC_GHCR_TOKEN") — landing
    a slot whose id and stored auth_env_key silently disagreed about what the
    key even was."""
    parsed = parse_slot_source(text)
    key = parsed.get("key") or (text or "").strip()
    url = parsed.get("url") or ""
    auth_env_key = (
        normalize_env_key(auth_env_key_override)
        if auth_env_key_override
        else (suggest_env_key(value=key, page_url=page_url or url) or _fallback_env_key(url))
    )
    category = classify_category(auth_env_key=auth_env_key, base_url=url or page_url)
    slot_id = _slugify(id_override) if id_override else _slot_id_from_hint(url, auth_env_key)
    return {
        "id": slot_id,
        "category": category,
        "auth_env_key": auth_env_key,
        "base_url": url or None,
        "auth_style": "bearer",
    }


def _first_post_path(openapi_url: str, *, timeout: float = 10.0) -> tuple[str, str]:
    r = httpx.get(openapi_url, timeout=timeout)
    r.raise_for_status()
    spec = r.json()
    paths = spec.get("paths") or {}
    for path, ops in paths.items():
        if isinstance(ops, dict) and "post" in ops:
            return path, "POST"
    for path, ops in paths.items():
        if isinstance(ops, dict) and "get" in ops:
            return path, "GET"
    raise ValueError("no usable path in OpenAPI spec")


def add_slot(
    *,
    auth_env_key: str,
    slot_id: str = "",
    category: str = "generic-rest",
    base_url: str = "",
    auth_style: AuthStyle = "bearer",
    openapi_url: str = "",
    method: str = "GET",
    path_template: str = "",
    headers: dict[str, str] | None = None,
    upsert: bool = True,
) -> dict[str, Any]:
    if auth_style not in _VALID_AUTH_STYLES:
        raise ValueError(f"auth_style must be one of {_VALID_AUTH_STYLES}")
    env_key = normalize_env_key(auth_env_key)
    if not env_key:
        raise ValueError("auth_env_key required")

    # Full Pastebin-style endpoints → origin + path; keep /v1 on LLM bases.
    base_url_n, split_path = _normalize_slot_base_and_path(base_url, path_template)
    method_final = (method or "GET").upper()
    path_final = split_path or ""
    warning = None
    if openapi_url and not path_final:
        try:
            path_final, method_final = _first_post_path(openapi_url)
        except Exception as e:  # noqa: BLE001 — OpenAPI hint is optional, register anyway
            warning = f"openapi fetch failed: {e}"[:300]

    with closing(_connect()) as conn:
        base_id = _slugify(slot_id) if slot_id else _slot_id_from_hint(base_url_n, env_key)
        existing = conn.execute("SELECT id FROM slots WHERE id = ?", (base_id,)).fetchone()
        if existing and upsert and slot_id:
            final_id = base_id
            conn.execute(
                "UPDATE slots SET category=?, base_url=?, auth_env_key=?, auth_style=?, openapi_url=?, "
                "method=?, path_template=?, headers_json=? WHERE id=?",
                (
                    category,
                    base_url_n or None,
                    env_key,
                    auth_style,
                    openapi_url or None,
                    method_final,
                    path_final,
                    json.dumps(headers or {}),
                    final_id,
                ),
            )
        else:
            final_id = _unique_id(conn, base_id) if existing else base_id
            conn.execute(
                "INSERT INTO slots (id, category, base_url, auth_env_key, auth_style, openapi_url, "
                "method, path_template, headers_json, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    final_id,
                    category,
                    base_url_n or None,
                    env_key,
                    auth_style,
                    openapi_url or None,
                    method_final,
                    path_final,
                    json.dumps(headers or {}),
                    _now_iso(),
                ),
            )
        conn.commit()

    result = get_slot(final_id)
    assert result is not None
    if warning:
        result["warning"] = warning
    return result


def get_slot(slot_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    return dict(row) if row else None


def list_slots() -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM slots ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def remove_slot(slot_id: str) -> bool:
    with closing(_connect()) as conn:
        cur = conn.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        conn.commit()
        return cur.rowcount > 0


def call_slot(
    slot_id: str,
    *,
    body: Any = None,
    method: str | None = None,
    path: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    slot = get_slot(slot_id)
    if slot is None:
        return {"ok": False, "error": f"slot {slot_id!r} not found"}
    base_url = slot.get("base_url") or ""
    if not base_url:
        return {
            "ok": False,
            "error": (
                f"slot {slot_id!r} has no base_url — Remove it, then Register again with "
                "Endpoint filled (e.g. https://pastebin.com/api/api_post.php)"
            ),
        }

    auth_env_key = slot["auth_env_key"]
    auth_style = slot.get("auth_style") or "bearer"
    api_key = os.getenv(auth_env_key, "")
    if not api_key and "PASTEBIN" in auth_env_key.upper():
        for alt in (
            "TBCC_PASTEBIN_API_DEV_KEY",
            "TBCC_PASTEBIN_API_KEY",
            "TBCC_PASTEBIN_API",
            "PASTEBIN_API_DEV_KEY",
        ):
            api_key = os.getenv(alt, "")
            if api_key:
                break
    if not api_key and "SHRINKME" in auth_env_key.upper():
        for alt in ("TBCC_SHRINKME_API_TOKEN", "TBCC_SHRINKMEIO_API", "SHRINKME_API_TOKEN"):
            api_key = os.getenv(alt, "")
            if api_key:
                break
    if auth_style != "none" and not api_key:
        return {"ok": False, "error": f"env var {auth_env_key} is not set"}

    method_final = (method or slot.get("method") or "GET").upper()
    path_final = path if path is not None else (slot.get("path_template") or "")
    if path_final and not path_final.startswith("/"):
        path_final = "/" + path_final
    url = base_url.rstrip("/") + path_final

    headers: dict[str, str] = json.loads(slot.get("headers_json") or "{}")
    params: dict[str, str] = {}
    form: dict[str, str] | None = None
    json_body = body

    if auth_style == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif auth_style == "x-api-key":
        headers["X-Api-Key"] = api_key
    elif auth_style == "query":
        # ShrinkMe family uses ?api=TOKEN&url=
        params["api"] = api_key
        if body is None and "shrinkme" in (base_url or "").lower():
            params.setdefault("url", "https://example.com/")
            params.setdefault("format", "text")
    elif auth_style == "form_api_dev_key":
        method_final = "POST"
        if not path_final:
            path_final = "/api/api_post.php"
            url = base_url.rstrip("/") + path_final
        form = {
            "api_dev_key": api_key,
            "api_option": "paste",
            "api_paste_code": "tbcc-api-pocket-smoke",
            "api_paste_private": "1",
            "api_paste_name": "tbcc-smoke",
            "api_paste_expire_date": "10M",
        }
        if isinstance(body, dict):
            form.update({str(k): str(v) for k, v in body.items()})
        json_body = None

    try:
        r = httpx.request(
            method_final,
            url,
            headers=headers,
            params=params or None,
            data=form,
            json=json_body if form is None and json_body is not None else None,
            timeout=timeout,
        )
        try:
            payload = r.json()
        except ValueError:
            payload = (r.text or "")[:800]
        ok = r.status_code < 400
        if auth_style == "form_api_dev_key" and isinstance(payload, str):
            low = payload.lower()
            if low.startswith("bad api"):
                ok = False
            elif not (payload.startswith("http") or "pastebin.com/" in low):
                ok = False
        return {"ok": ok, "status": r.status_code, "url": url, "body": payload}
    except httpx.HTTPError as e:
        return {"ok": False, "error": str(e)[:300], "url": url}
