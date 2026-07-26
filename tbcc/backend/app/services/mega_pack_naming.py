"""MEGA pack folder branding: @AOFMAINHUB · size · files · theme · tail (skips already on new format)."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.mega_account_client import MegaFolderEntry

logger = logging.getLogger(__name__)

AOFMAINHUB_MARKER = "AOFMAINHUB"
LEGACY_SUFFIX = "-TME AOFMAINHUB"
_MAX_FOLDER_NAME = 256


def pack_brand_handle() -> str:
    return (os.getenv("TBCC_MEGA_PACK_BRAND_HANDLE") or "telegram.me/aofmainhub").strip() or "telegram.me/aofmainhub"


def pack_name_tail() -> str:
    """Trailing brand slot — MEGA PACK, VIP, addlist slug, etc."""
    raw = (os.getenv("TBCC_MEGA_PACK_NAME_TAIL") or "MEGA PACK · VIP").strip()
    return raw or "MEGA PACK · VIP"


def pack_brand_rename_enabled() -> bool:
    return (os.getenv("TBCC_MEGA_PACK_BRAND_RENAME") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def rebrand_legacy_packs_enabled() -> bool:
    return (os.getenv("TBCC_MEGA_PACK_REBRAND_LEGACY") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def pack_name_separator() -> str:
    sep = (os.getenv("TBCC_MEGA_PACK_NAME_SEP") or " · ").strip()
    return sep or " · "


def is_new_brand_format(folder_name: str) -> bool:
    """True when folder already uses @AOFMAINHUB · … convention."""
    name = (folder_name or "").strip()
    if not name:
        return False
    handle = pack_brand_handle().lstrip("@").upper()
    up = name.upper()
    if up.startswith(f"@{handle} "):
        return True
    if up.startswith(f"@{handle}{pack_name_separator().strip()}".upper()):
        return True
    # Tolerate missing @ if handle token leads the name
    if up.startswith(f"{handle}{pack_name_separator().strip()}".upper()):
        return True
    return False


def is_pack_already_branded(folder_name: str) -> bool:
    """True when folder should not be touched (clean new format, or legacy when rebrand off)."""
    name = (folder_name or "").strip()
    if not name:
        return False
    # Partial renames still carrying -TME AOFMAINHUB in the theme slot → rebuild.
    if LEGACY_SUFFIX.upper() in name.upper():
        return not rebrand_legacy_packs_enabled()
    if is_new_brand_format(name):
        return True
    if AOFMAINHUB_MARKER in name.upper():
        return not rebrand_legacy_packs_enabled()
    return False


def slug_pack_label(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return s[:80]


def _sanitize_theme(text: str) -> str:
    from app.services.aof_packs_vocabulary import sanitize_pack_copy

    s = re.sub(r'[\\/:*?"<>|]+', " ", (text or "").strip())
    s = re.sub(r"\s+", " ", s).strip()
    if s.startswith("@"):
        s = s.lstrip("@").strip()
    cleaned = sanitize_pack_copy(s, seed=s)
    return cleaned[:100] or "AOF Pack"


def extract_pack_theme(folder_name: str) -> str:
    """Base model/theme from raw or partially branded folder name."""
    name = (folder_name or "").strip()
    if not name:
        return "AOF Pack"

    if not is_new_brand_format(name):
        legacy = name
        legacy = re.sub(
            r"\s*[·•|]\s*\d+(?:\.\d+)?\s*GB\s*[·•|]\s*AOFMAINHUB\s*$",
            "",
            legacy,
            flags=re.IGNORECASE,
        )
        for tail in (
            LEGACY_SUFFIX,
            " - TME AOFMAINHUB",
            f" · {AOFMAINHUB_MARKER}",
            f" - {AOFMAINHUB_MARKER}",
            f" | {AOFMAINHUB_MARKER}",
        ):
            if legacy.endswith(tail):
                legacy = legacy[: -len(tail)].strip()
                break
        if legacy.upper().startswith("AOF — "):
            legacy = legacy[6:].strip()
        if legacy.upper().startswith("AOF - "):
            legacy = legacy[6:].strip()
        return _sanitize_theme(legacy)

    sep = pack_name_separator()
    parts = [p.strip() for p in name.split(sep) if p.strip()]
    if not parts:
        return "AOF Pack"

    handle_up = pack_brand_handle().lstrip("@").upper()
    tail_tokens = {t.strip().upper() for t in pack_name_tail().split("·") if t.strip()}
    tail_tokens |= {"MEGA PACK", "VIP", AOFMAINHUB_MARKER, handle_up}

    cleaned: list[str] = []
    for part in parts:
        up = part.upper()
        if up.lstrip("@") == handle_up or up == f"@{handle_up}":
            continue
        if re.match(r"^\d+(?:\.\d+)?\s*GB$", part, re.IGNORECASE):
            continue
        if re.match(r"^\d+\s*Files?$", part, re.IGNORECASE):
            continue
        if up in tail_tokens:
            continue
        if "ALLMYLINKS.COM" in up or up.startswith("T.ME/") or up.startswith("TELEGRAM.ME/"):
            continue
        cleaned.append(part)

    if cleaned:
        theme = cleaned[0]
        for tail in (LEGACY_SUFFIX, " - TME AOFMAINHUB"):
            if theme.endswith(tail):
                theme = theme[: -len(tail)].strip()
                break
        return _sanitize_theme(theme)
    return "AOF Pack"


def format_size_gb_for_name(size_gb: float | None) -> str | None:
    if size_gb is None or size_gb <= 0:
        return None
    if size_gb >= 100:
        return f"{size_gb:.0f}GB"
    if size_gb >= 10:
        val = f"{size_gb:.1f}".rstrip("0").rstrip(".")
        return f"{val}GB"
    return f"{size_gb:.1f}GB"


def format_file_count_for_name(file_count: int | None) -> str | None:
    if file_count is None or file_count <= 0:
        return None
    return f"{file_count} Files"


def build_branded_pack_folder_name(
    theme: str,
    size_gb: float | None,
    *,
    file_count: int | None = None,
) -> str:
    """
    Single-line MEGA folder name — brand handle, size, file count, theme, tail.
    Example: @AOFMAINHUB · 13.7GB · 698 Files · Mihanika · MEGA PACK · VIP
    """
    sep = pack_name_separator()
    parts: list[str] = [pack_brand_handle()]
    size_part = format_size_gb_for_name(size_gb)
    if size_part:
        parts.append(size_part)
    count_part = format_file_count_for_name(file_count)
    if count_part:
        parts.append(count_part)
    parts.append(_sanitize_theme(theme))
    tail = pack_name_tail()
    if tail:
        parts.append(tail)
    name = sep.join(parts)
    return name[:_MAX_FOLDER_NAME]


def target_branded_pack_rename(
    current: str,
    size_gb: float | None,
    *,
    file_count: int | None = None,
) -> str | None:
    """New folder name for unbranded or legacy packs; None = leave unchanged."""
    name = (current or "").strip()
    if not name or is_pack_already_branded(name):
        return None
    theme = extract_pack_theme(name)
    new_name = build_branded_pack_folder_name(theme, size_gb, file_count=file_count)
    if new_name == name:
        return None
    return new_name


def apply_pack_brand_rename_rclone(
    entries: list[MegaFolderEntry],
    *,
    execute: bool,
    limit: int = 0,
) -> list[dict[str, str]]:
    from app.services.mega_rclone_client import (
        folder_size_stats_rclone,
        rename_mega_folder_rclone,
        should_skip_folder,
    )

    changes: list[dict[str, str]] = []
    renamed = 0
    for entry in entries:
        if limit > 0 and renamed >= limit:
            break
        if should_skip_folder(entry.name):
            continue
        if is_pack_already_branded(entry.name):
            continue
        print(f"STATS {entry.name}…", flush=True)
        size_gb = None
        file_count = None
        try:
            stats = folder_size_stats_rclone(entry.name)
            size_gb = stats.get("size_gb")
            file_count = stats.get("file_count")
        except Exception as exc:
            logger.warning("folder stats failed %s: %s", entry.name, exc)
        new_name = target_branded_pack_rename(
            entry.name,
            size_gb,
            file_count=file_count,
        )
        if not new_name:
            continue
        row = {
            "path": entry.path,
            "from": entry.name,
            "to": new_name,
            "size_gb": str(size_gb) if size_gb else "",
            "file_count": str(file_count) if file_count else "",
        }
        if execute:
            try:
                rename_mega_folder_rclone(entry, new_name)
                row["renamed"] = "true"
                entry.name = new_name
                entry.path = new_name
                renamed += 1
            except Exception as exc:
                row["renamed"] = "false"
                row["error"] = str(exc)[:300]
                logger.warning("brand rename failed %s → %s: %s", entry.name, new_name, exc)
        changes.append(row)
    return changes
