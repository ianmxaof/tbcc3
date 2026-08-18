"""Load FE-LLMv4 / secretary prompts from app/config/system_prompts.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PROMPTS_PATH = Path(__file__).resolve().parents[1] / "config" / "system_prompts.json"


@lru_cache(maxsize=1)
def load_system_prompts() -> dict:
    if not _PROMPTS_PATH.is_file():
        return {"prompts": {}}
    data = json.loads(_PROMPTS_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"prompts": {}}


def prompt_text(prompt_id: str) -> str:
    block = (load_system_prompts().get("prompts") or {}).get(prompt_id) or {}
    return str(block.get("text") or "").strip()
