"""MEGA account inventory via mega.py (list folders, rename, export public links)."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FOLDER_TYPE = 1
_ROOT_TYPE = 2


@dataclass
class MegaFolderEntry:
    handle: str
    name: str
    path: str
    parent_handle: str | None
    public_link: str | None = None


def mega_credentials_from_env() -> tuple[str, str]:
    email = (os.getenv("TBCC_MEGA_EMAIL") or "").strip()
    password = (os.getenv("TBCC_MEGA_PASSWORD") or "").strip()
    if not email or not password:
        raise ValueError("Set TBCC_MEGA_EMAIL and TBCC_MEGA_PASSWORD in tbcc/.env")
    return email, password


def mega_rename_prefix_from_env() -> str:
    return (os.getenv("TBCC_MEGA_RENAME_PREFIX") or "AOF — ").strip()


def login_mega_api():
    """Return logged-in mega.py Mega instance."""
    try:
        from mega import Mega
    except ImportError as e:
        raise RuntimeError(
            "mega.py is not installed — pip install mega.py tenacity>=8 (see backend/requirements.txt)"
        ) from e
    email, password = mega_credentials_from_env()
    api = Mega()
    return api.login(email, password)


def _node_name(node: dict[str, Any]) -> str:
    attrs = node.get("a") or {}
    name = attrs.get("n")
    return str(name) if name else ""


def _build_folder_path(nodes: dict[str, Any], handle: str) -> str:
    parts: list[str] = []
    current: str | None = handle
    seen: set[str] = set()
    while current and current in nodes and current not in seen:
        seen.add(current)
        node = nodes[current]
        if int(node.get("t", -1)) == _ROOT_TYPE:
            break
        name = _node_name(node)
        if name:
            parts.append(name)
        current = node.get("p")
    return "/".join(reversed(parts))


def list_mega_folders(
    api: Any,
    *,
    root_prefix: str | None = None,
    include_trash: bool = False,
) -> list[MegaFolderEntry]:
    """List folder nodes in the MEGA cloud drive."""
    nodes: dict[str, Any] = api.get_files()
    trash_id = getattr(api, "_trash_folder_node_id", None)
    root_prefix_norm = (root_prefix or "").strip().strip("/").lower()
    out: list[MegaFolderEntry] = []

    for handle, node in nodes.items():
        if int(node.get("t", -1)) != _FOLDER_TYPE:
            continue
        parent = node.get("p")
        if not include_trash and trash_id and parent == trash_id:
            continue
        path = _build_folder_path(nodes, handle)
        if root_prefix_norm and not path.lower().startswith(root_prefix_norm):
            continue
        out.append(
            MegaFolderEntry(
                handle=str(handle),
                name=_node_name(node),
                path=path,
                parent_handle=str(parent) if parent else None,
            )
        )
    out.sort(key=lambda e: e.path.lower())
    return out


def export_folder_link(api: Any, entry: MegaFolderEntry) -> str:
    """Create or fetch a public folder link (#F! or /folder/ format)."""
    link = api.export(node_id=entry.handle)
    if not isinstance(link, str) or not link.startswith("http"):
        raise RuntimeError(f"MEGA export failed for {entry.path!r}: {link!r}")
    return link.strip()


def rename_mega_folder(api: Any, entry: MegaFolderEntry, new_name: str) -> None:
    nodes = api.get_files()
    node = nodes.get(entry.handle)
    if not node:
        raise RuntimeError(f"MEGA folder not found: {entry.path}")
    api.rename((entry.handle, node), new_name.strip()[:256])


def apply_rename_prefix(
    api: Any,
    entries: list[MegaFolderEntry],
    *,
    prefix: str,
    execute: bool,
) -> list[dict[str, str]]:
    """Rename folders missing the prefix. Returns change log rows."""
    changes: list[dict[str, str]] = []
    if not prefix:
        return changes
    for entry in entries:
        if entry.name.startswith(prefix):
            continue
        new_name = f"{prefix}{entry.name}"[:256]
        row = {"path": entry.path, "from": entry.name, "to": new_name}
        if execute:
            rename_mega_folder(api, entry, new_name)
            row["renamed"] = "true"
        changes.append(row)
    return changes


def mega_readme_filename_from_env() -> str:
    name = (os.getenv("TBCC_MEGA_README_FILENAME") or "AOF_NETWORK.txt").strip()
    if not name or "/" in name or "\\" in name:
        return "AOF_NETWORK.txt"
    return name[:128]


def upload_text_to_folder(
    api: Any,
    entry: MegaFolderEntry,
    text: str,
    *,
    dest_filename: str | None = None,
) -> str:
    """Upload a text file into a MEGA folder. Returns uploaded filename."""
    fname = (dest_filename or mega_readme_filename_from_env()).strip()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tmp:
        tmp.write(text)
        tmp_path = tmp.name
    try:
        api.upload(tmp_path, dest=entry.handle, dest_filename=fname)
        return fname
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass
