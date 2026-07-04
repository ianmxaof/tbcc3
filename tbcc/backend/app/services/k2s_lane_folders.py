"""K2S folder mapping for AOF network lanes + packs/loot."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.data.aof_network import AOF_NETWORK_CHANNELS
from app.services.keep2share_client import (
    K2sNotConfiguredError,
    create_folder,
    get_folders_list,
    k2s_configured,
)

logger = logging.getLogger(__name__)

# Lanes covered: main group + AI/taboo/voyeur channels + unified pack/loot pools.
K2S_LANE_KEYS: tuple[str, ...] = (
    "main",
    "ai",
    "taboo",
    "voyeur",
    "packs",
    "loot",
)

_LANE_ENV: dict[str, str] = {
    "main": "TBCC_K2S_FOLDER_MAIN",
    "ai": "TBCC_K2S_FOLDER_AI",
    "taboo": "TBCC_K2S_FOLDER_TABOO",
    "voyeur": "TBCC_K2S_FOLDER_VOYEUR",
    "packs": "TBCC_K2S_FOLDER_PACKS",
    "loot": "TBCC_K2S_FOLDER_LOOT",
}

_LANE_FOLDER_NAMES: dict[str, str] = {
    "main": "AOF Main",
    "ai": "AOF AI",
    "taboo": "AOF Taboo",
    "voyeur": "AOF Voyeur",
    "packs": "AOF Packs",
    "loot": "AOF Loot",
}

_runtime_folder_cache: dict[str, str] = {}


def mirror_enabled() -> bool:
    if not k2s_configured():
        return False
    return (os.getenv("TBCC_K2S_MIRROR_ENABLED") or "0").strip().lower() in ("1", "true", "yes", "on")


def vip_direct_enabled() -> bool:
    if not k2s_configured():
        return False
    return (os.getenv("TBCC_K2S_VIP_DIRECT_ENABLED") or "1").strip().lower() not in ("0", "false", "no", "off")


def auto_create_folders() -> bool:
    return (os.getenv("TBCC_K2S_AUTO_CREATE_FOLDERS") or "1").strip().lower() not in ("0", "false", "no", "off")


def lane_env_key(lane: str) -> str | None:
    key = (lane or "").strip().lower()
    return _LANE_ENV.get(key)


def list_lane_status() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in K2S_LANE_KEYS:
        env_name = _LANE_ENV[key]
        configured = (os.getenv(env_name) or "").strip() or _runtime_folder_cache.get(key)
        ch = next((c for c in AOF_NETWORK_CHANNELS if c.key == key), None)
        out.append(
            {
                "lane": key,
                "folder_id": configured or None,
                "folder_name": _LANE_FOLDER_NAMES.get(key),
                "env_var": env_name,
                "network_channel": ch.display_name if ch else None,
            }
        )
    return out


def infer_lane_from_text(*parts: str | None) -> str:
    blob = " ".join(p for p in parts if p).lower()
    if "taboo" in blob:
        return "taboo"
    if "voyeur" in blob:
        return "voyeur"
    if _ai_lane_match(blob):
        return "ai"
    if "main group" in blob or blob.startswith("main") or "|main" in blob:
        return "main"
    if "pack" in blob or "aof packs" in blob:
        return "packs"
    if "loot" in blob or "modifier" in blob:
        return "loot"
    return "packs"


def _ai_lane_match(blob: str) -> bool:
    return bool(re.search(r"\bai\b|aof ai|deepfake", blob))


def get_lane_folder_id(lane: str, *, create: bool = False) -> str | None:
    key = (lane or "packs").strip().lower()
    if key not in _LANE_ENV:
        key = "packs"
    cached = _runtime_folder_cache.get(key)
    if cached:
        return cached
    env_val = (os.getenv(_LANE_ENV[key]) or "").strip()
    if env_val:
        _runtime_folder_cache[key] = env_val
        return env_val
    if not create or not auto_create_folders() or not k2s_configured():
        return None
    return ensure_lane_folder(key)


def ensure_lane_folder(lane: str) -> str | None:
    key = (lane or "packs").strip().lower()
    if key not in _LANE_ENV:
        key = "packs"
    existing = get_lane_folder_id(key, create=False)
    if existing:
        return existing
    if not k2s_configured():
        return None
    name = _LANE_FOLDER_NAMES.get(key, f"AOF {key.title()}")
    try:
        for row in get_folders_list():
            if (row.get("name") or "").strip().lower() == name.lower():
                fid = str(row.get("id") or "").strip()
                if fid:
                    _runtime_folder_cache[key] = fid
                    logger.info("k2s lane %s resolved existing folder %s", key, fid)
                    return fid
        fid = create_folder(name, parent="/")
        if fid:
            _runtime_folder_cache[key] = fid
            logger.info("k2s lane %s created folder %s (%s)", key, fid, name)
        return fid
    except K2sNotConfiguredError:
        return None
    except Exception as e:
        logger.warning("k2s ensure_lane_folder %s failed: %s", key, e)
        return None


def ensure_all_lane_folders() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for key in K2S_LANE_KEYS:
        out[key] = ensure_lane_folder(key)
    return out
