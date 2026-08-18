"""Write TBCC secrets to tbcc/.env (shared by API + scripts)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_KEY_RE = re.compile(
    r"^\s*(TBCC_[A-Z0-9_]+|BUFFER_[A-Z0-9_]+|OPENROUTER_[A-Z0-9_]+|REPLICATE_[A-Z0-9_]+)\s*="
)
_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "tbcc_env_secret_registry.json"
_AFFILIATE_RE = re.compile(
    r"nodress|nudify\.now|musebox|playbun|fapify|drawai|botynude|/ref/|bot\?username=",
    re.I,
)
_TELEGRAM_RE = re.compile(r"t\.me/", re.I)
_ALLMYLINKS_RE = re.compile(r"allmylinks\.com", re.I)
_EROME_RE = re.compile(r"erome\.com", re.I)


def tbcc_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def env_file_path() -> Path:
    override = (os.getenv("TBCC_ENV_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return tbcc_root() / ".env"


def list_env_secret_keys() -> list[str]:
    path = env_file_path()
    if not path.is_file():
        return []
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ENV_KEY_RE.match(line)
        if m:
            keys.append(m.group(1))
    return sorted(set(keys))


def _load_hints() -> list[dict[str, str]]:
    if not _REGISTRY_PATH.is_file():
        return []
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        rows = data.get("hints") if isinstance(data, dict) else []
        return [r for r in rows if isinstance(r, dict)]
    except Exception as e:
        logger.warning("secret registry read failed: %s", e)
        return []


def suggest_env_key(*, value: str, page_url: str = "") -> str | None:
    text = (value or "").strip()
    url = (page_url or "").strip().lower()
    for h in _load_hints():
        pat = str(h.get("pattern") or "").strip()
        if pat and re.search(pat, text, re.I):
            key = str(h.get("suggest_key") or "").strip()
            if key:
                return key
    for h in _load_hints():
        mu = str(h.get("match_url") or "").strip().lower()
        if mu and mu in url:
            key = str(h.get("suggest_key") or "").strip()
            if key:
                return key
        mt = str(h.get("match_title") or "").strip().lower()
        if mt and mt in url:
            key = str(h.get("suggest_key") or "").strip()
            if key:
                return key
    # High-confidence fallbacks when registry URL context is missing (notepad / desktop).
    if re.match(r"^https://pub-[a-z0-9]+\.r2\.dev(/.*)?$", text, re.I):
        return "TBCC_R2_PUBLIC_BASE_URL"
    if re.match(r"^https://[a-z0-9.-]+\.r2\.cloudflarestorage\.com(/.*)?$", text, re.I):
        return "TBCC_R2_S3_ENDPOINT"
    if re.match(r"^AIza", text):
        return "TBCC_GEMINI_API_KEY"
    if re.match(r"^tskey-", text, re.I):
        return "TBCC_TAILSCALE_AUTHKEY"
    if re.match(r"^sk-or-", text, re.I):
        return "OPENROUTER_API_KEY"
    if re.match(r"^csk-", text, re.I):
        return "TBCC_CEREBRAS_API"
    if re.match(r"^nvapi-", text, re.I):
        return "TBCC_NVIDIA_API"
    if re.match(r"^r8_", text, re.I):
        return "REPLICATE_API_TOKEN"
    if re.match(r"^(ghp_|gho_|github_pat_)", text, re.I):
        return "TBCC_GHCR_TOKEN"
    if "pixeldrain" in url:
        return "TBCC_PIXELDRAIN_API_KEY"
    if re.match(r"^[a-f0-9]{32}$", text, re.I):
        return "TBCC_R2_ACCOUNT_ID"
    return None


def looks_like_api_key(value: str) -> bool:
    t = (value or "").strip()
    if len(t) < 12 or len(t) > 600:
        return False
    if re.search(r"\s", t):
        return False
    if re.search(
        r"^(sk-|pk_|r8_|ghp_|gho_|github_pat_|xox[baprs]-|AIza|tskey-|tskey-auth-|csk-|nvapi-|gsk_)",
        t,
        re.I,
    ):
        return True
    if re.match(r"^https://pub-[a-z0-9]+\.r2\.dev(/.*)?$", t, re.I):
        return True
    if re.match(r"^https://[a-z0-9.-]+\.r2\.cloudflarestorage\.com(/[A-Za-z0-9._-]*)?/?$", t, re.I):
        return True
    if re.match(r"^[A-Za-z0-9._\-+/=]{16,}$", t):
        return True
    return False


def normalize_secret_value(key: str, value: str) -> str:
    """Strip optional /bucket from R2 S3 dashboard copies; trim trailing slash on public base."""
    k = normalize_env_key(key)
    t = (value or "").strip()
    if not t:
        return t
    if k == "TBCC_R2_S3_ENDPOINT" or re.search(r"\.r2\.cloudflarestorage\.com/", t, re.I):
        m = re.match(r"^(https://[a-z0-9.-]+\.r2\.cloudflarestorage\.com)(/.*)?$", t, re.I)
        if m:
            return m.group(1)
    if k == "TBCC_R2_PUBLIC_BASE_URL" or re.match(r"^https://pub-[a-z0-9]+\.r2\.dev/", t, re.I):
        m = re.match(r"^(https://pub-[a-z0-9]+\.r2\.dev)(/.*)?$", t, re.I)
        if m:
            return m.group(1)
    return t.rstrip("/")


_KEY_ALIASES = {
    "TBCC_GEMINI_KEY": "TBCC_GEMINI_API_KEY",
    "GEMINI_KEY": "TBCC_GEMINI_API_KEY",
    "GEMINI_API_KEY": "TBCC_GEMINI_API_KEY",
    "TBCC_CLOUDFLARE_TOKEN": "TBCC_CF_API_TOKEN",
    "CLOUDFLARE_TOKEN": "TBCC_CF_API_TOKEN",
    "TBCC_CLOUDFLARE_API_TOKEN": "TBCC_CF_API_TOKEN",
    "ACCOUNT_ID": "TBCC_R2_ACCOUNT_ID",
    "R2_ACCOUNT_ID": "TBCC_R2_ACCOUNT_ID",
    "PUBLIC_DEVELOPMENT_URL": "TBCC_R2_PUBLIC_BASE_URL",
    "PUBLIC_DEV_URL": "TBCC_R2_PUBLIC_BASE_URL",
    "R2_PUBLIC_URL": "TBCC_R2_PUBLIC_BASE_URL",
    "S3_API": "TBCC_R2_S3_ENDPOINT",
    "S3_ENDPOINT": "TBCC_R2_S3_ENDPOINT",
    "R2_S3_API": "TBCC_R2_S3_ENDPOINT",
    "TBCC_PD": "TBCC_PIXELDRAIN_API_KEY",
    "PD_KEY": "TBCC_PIXELDRAIN_API_KEY",
    "PIXELDRAIN_API_KEY": "TBCC_PIXELDRAIN_API_KEY",
    "PIXELDRAIN_KEY": "TBCC_PIXELDRAIN_API_KEY",
    "PIXELDRAIN_API_KEY_071726": "TBCC_PIXELDRAIN_API_KEY",
    "CEREBRAS_API_KEY": "TBCC_CEREBRAS_API",
    "TBCC_CEREBRAS_API_KEY": "TBCC_CEREBRAS_API",
    "NVIDIA_API_KEY": "TBCC_NVIDIA_API",
    "TBCC_NVIDIA_API_KEY": "TBCC_NVIDIA_API",
    "NIM_API_KEY": "TBCC_NVIDIA_API",
    "MISTRAL_API_KEY": "TBCC_MISTRAL_API",
    "TBCC_MISTRAL_API_KEY": "TBCC_MISTRAL_API",
}


def normalize_env_key(key: str) -> str:
    """Normalize human labels ('TBCC GEMINI KEY') to env var names."""
    k = re.sub(r"[^A-Za-z0-9]+", "_", (key or "").strip())
    k = re.sub(r"_+", "_", k).strip("_").upper()
    return _KEY_ALIASES.get(k, k)


def write_env_secret(key: str, value: str) -> None:
    k = normalize_env_key(key)
    v = normalize_secret_value(k, value)
    if not k:
        raise ValueError("key required")
    if not v:
        raise ValueError("value required")
    path = env_file_path()
    if not path.is_file():
        raise FileNotFoundError(f".env not found at {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    out: list[str] = []
    pattern = re.compile(rf"^\s*{re.escape(k)}\s*=")
    for line in lines:
        if pattern.match(line):
            out.append(f"{k}={v}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{k}={v}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def backup_credential_manager(key: str, value: str) -> bool:
    """Best-effort Windows Credential Manager backup via cmdkey."""
    if os.name != "nt":
        return False
    import subprocess

    target = f"TBCC/{key}"
    try:
        proc = subprocess.run(
            ["cmdkey", f"/generic:{target}", "/user:tbcc", f"/pass:{value}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.returncode == 0
    except Exception as e:
        logger.warning("cmdkey backup failed: %s", e)
        return False
