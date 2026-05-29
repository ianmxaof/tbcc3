"""ASCII art library for listening relay copy panels (mobile-safe widths)."""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import Any

from app.models.listening_relay_settings import ListeningRelaySettings

RELAY_ASCII_MAX_WIDTH = 42
RELAY_ASCII_MAX_LINES = 40
RELAY_ASCII_MAX_CHARS = 3800

_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "data" / "relay_ascii"


def _line_width(line: str) -> int:
    return len(line.rstrip("\n\r"))


def validate_ascii_content(text: str) -> tuple[bool, str]:
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not s.strip():
        return False, "Empty content"
    lines = s.split("\n")
    if len(lines) > RELAY_ASCII_MAX_LINES:
        return False, f"Max {RELAY_ASCII_MAX_LINES} lines"
    if len(s) > RELAY_ASCII_MAX_CHARS:
        return False, f"Max {RELAY_ASCII_MAX_CHARS} characters"
    for i, line in enumerate(lines, 1):
        w = _line_width(line)
        if w > RELAY_ASCII_MAX_WIDTH:
            return False, f"Line {i} is {w} chars (max {RELAY_ASCII_MAX_WIDTH})"
    return True, ""


def _load_builtin_entries() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not _BUILTIN_DIR.is_dir():
        return out
    for p in sorted(_BUILTIN_DIR.glob("*.txt")):
        try:
            body = p.read_text(encoding="utf-8")
        except OSError:
            continue
        ok, _ = validate_ascii_content(body)
        if not ok:
            continue
        out.append(
            {
                "id": f"builtin:{p.stem}",
                "name": p.stem.replace("_", " "),
                "content": body.strip("\n"),
                "builtin": True,
                "tryptych_group": (p.stem.rsplit("_panel_", 1)[0] if "_panel_" in p.stem else None),
                "tryptych_part": (
                    int(p.stem.rsplit("_panel_", 1)[1])
                    if "_panel_" in p.stem and p.stem.rsplit("_panel_", 1)[1].isdigit()
                    else None
                ),
            }
        )
    return out


def user_library_entries(row: ListeningRelaySettings) -> list[dict[str, Any]]:
    raw = getattr(row, "ascii_art_library_json", None)
    if not raw:
        return []
    try:
        arr = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(arr, list):
        return []
    out: list[dict[str, Any]] = []
    for x in arr:
        if not isinstance(x, dict):
            continue
        content = str(x.get("content") or "").strip("\n")
        ok, _ = validate_ascii_content(content)
        if not ok:
            continue
        out.append(
            {
                "id": str(x.get("id") or ""),
                "name": str(x.get("name") or "Custom")[:80],
                "content": content,
                "builtin": False,
                "tryptych_group": x.get("tryptych_group"),
                "tryptych_part": x.get("tryptych_part"),
            }
        )
    return out


def list_all_ascii_entries(row: ListeningRelaySettings) -> list[dict[str, Any]]:
    return _load_builtin_entries() + user_library_entries(row)


def add_user_ascii_entry(row: ListeningRelaySettings, *, name: str, content: str) -> dict[str, Any]:
    ok, err = validate_ascii_content(content)
    if not ok:
        raise ValueError(err)
    entry = {
        "id": str(uuid.uuid4()),
        "name": (name or "Custom").strip()[:80] or "Custom",
        "content": content.replace("\r\n", "\n").replace("\r", "\n").strip("\n"),
    }
    lib = user_library_entries(row)
    lib.append(entry)
    row.ascii_art_library_json = json.dumps(
        [{"id": e["id"], "name": e["name"], "content": e["content"]} for e in lib]
    )
    return entry


def remove_user_ascii_entry(row: ListeningRelaySettings, entry_id: str) -> bool:
    eid = (entry_id or "").strip()
    if not eid or eid.startswith("builtin:"):
        return False
    lib = [e for e in user_library_entries(row) if e.get("id") != eid]
    if len(lib) == len(user_library_entries(row)):
        return False
    row.ascii_art_library_json = json.dumps(
        [{"id": e["id"], "name": e["name"], "content": e["content"]} for e in lib]
    ) if lib else None
    return True


def pick_random_ascii(row: ListeningRelaySettings) -> str | None:
    pool = list_all_ascii_entries(row)
    if not pool:
        return None
    standalone = [e for e in pool if not e.get("tryptych_group")]
    pick_from = standalone or pool
    return str(random.choice(pick_from).get("content") or "")


def pick_tryptych_ascii_panels(row: ListeningRelaySettings) -> list[str] | None:
    """Return 3 panel strings if a built-in/user tryptych group exists."""
    pool = list_all_ascii_entries(row)
    groups: dict[str, list[tuple[int, str]]] = {}
    for e in pool:
        grp = e.get("tryptych_group")
        part = e.get("tryptych_part")
        content = e.get("content")
        if grp and isinstance(part, int) and content:
            groups.setdefault(str(grp), []).append((part, str(content)))
    if not groups:
        return None
    grp_key = random.choice(list(groups.keys()))
    parts = sorted(groups[grp_key], key=lambda x: x[0])
    if len(parts) < 3:
        return None
    return [p[1] for p in parts[:3]]


def split_ascii_into_panels(content: str, panels: int = 3) -> list[str]:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").strip("\n").split("\n")
    if not lines:
        return [""] * panels
    chunk = max(1, (len(lines) + panels - 1) // panels)
    chunks: list[str] = []
    for i in range(panels):
        seg = lines[i * chunk : (i + 1) * chunk]
        chunks.append("\n".join(seg) if seg else "·")
    return chunks


def roll_ascii_threshold(row: ListeningRelaySettings) -> int:
    lo = max(1, int(getattr(row, "ascii_art_min_interval", None) or 3))
    hi = max(lo, int(getattr(row, "ascii_art_max_interval", None) or 6))
    return random.randint(lo, hi)


def note_scrobble_for_ascii(row: ListeningRelaySettings) -> bool:
    """
    Increment scrobble counter; return True when an ASCII beat should fire on this post.
    """
    if not bool(getattr(row, "ascii_art_enabled", False)):
        return False
    row.ascii_art_scrobble_counter = int(getattr(row, "ascii_art_scrobble_counter", None) or 0) + 1
    thr = getattr(row, "ascii_art_next_threshold", None)
    if thr is None:
        row.ascii_art_next_threshold = roll_ascii_threshold(row)
        thr = row.ascii_art_next_threshold
    if row.ascii_art_scrobble_counter >= int(thr):
        row.ascii_art_scrobble_counter = 0
        row.ascii_art_next_threshold = roll_ascii_threshold(row)
        return True
    return False
