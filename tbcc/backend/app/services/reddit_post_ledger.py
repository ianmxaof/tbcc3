"""Append-only ledger for Reddit submit attempts (ops + attribution)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.import_pipeline import tbcc_run_dir

logger = logging.getLogger(__name__)


def reddit_promo_dir() -> Path:
    d = tbcc_run_dir() / "reddit-promo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def reddit_post_ledger_path() -> Path:
    return reddit_promo_dir() / "post-ledger.jsonl"


def append_reddit_post_ledger(entry: dict[str, Any]) -> Path:
    path = reddit_post_ledger_path()
    row = dict(entry)
    row.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def read_reddit_post_ledger(limit: int = 50) -> list[dict[str, Any]]:
    path = reddit_post_ledger_path()
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, limit) :]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
