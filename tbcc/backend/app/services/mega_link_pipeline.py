"""
Mega / file-host pipeline: bypass obfuscated links → unwrap paste pages → verify → LV rewrap → loot modifier.

Integrates:
  - bypass.vip via app.services.bypass_vip_client (TBCC_BYPASS_API_KEY)
  - master archive tags/descriptions via CaptureArchiveEntry
  - loot_modifiers (kind=mega_pack) with volume-based min_rarity_tier
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.pack_gate_wrap import legacy_wrap_destination, wrap_pack_gates_on_ingest
from app.services.link_gate_unwrap import resolve_obfuscated_url
from app.services.mega_link_extract import (
    ExtractedUrl,
    classify_url_host,
    extract_mega_urls_from_html,
    extract_urls_from_text,
    parse_mega_folder_page_meta,
    parse_size_gb_hint,
    pick_best_file_url,
    volume_to_rarity_tier,
)

logger = logging.getLogger(__name__)

_MAX_RESOLVE_HOPS = 8
_FETCH_TIMEOUT = 25.0
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class MegaLinkPipelineResult:
    ok: bool
    input_url: str
    destination_url: str | None = None
    lv_wrapped_url: str | None = None
    min_rarity_tier: int = 3
    size_gb_hint: float | None = None
    label: str | None = None
    hops: list[str] = field(default_factory=list)
    error: str | None = None


def _is_mega_folder(url: str) -> bool:
    low = url.lower()
    if "mega.nz" not in low and "mega.co.nz" not in low:
        return False
    return "/folder/" in low or "#f!" in low


def _fetch_html(url: str) -> tuple[str | None, str | None]:
    try:
        with httpx.Client(
            timeout=_FETCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*"},
        ) as client:
            r = client.get(url)
        if r.status_code >= 400:
            return None, f"http_{r.status_code}"
        return r.text or "", None
    except Exception as e:
        return None, str(e)[:300]


def _dead_body_markers() -> tuple[str, ...]:
    return (
        "not found",
        "no longer available",
        "no longer exists",
        "removed",
        "file/folder is not accessible",
        "folder link has been cancelled",
        "link you are trying to access is not valid",
        "invalid url",
        "dead link",
        "this folder is empty",
        "folder is empty",
        "0 files",
        "the folder you are trying to view is not accessible",
    )


def _mega_folder_has_files(html: str) -> bool:
    low = (html or "").lower()
    if any(m in low for m in _dead_body_markers()):
        return False
    # MEGA web client embeds file metadata when folder has content
    positive = (
        '"type":"file"',
        '"type": "file"',
        "data-filecount",
        "file-block",
        "grid-table",
    )
    if any(p in low for p in positive):
        return True
    _size_gb, file_count = parse_mega_folder_page_meta(html)
    if file_count is not None and file_count > 0:
        return True
    if _size_gb is not None and _size_gb > 0:
        return True
    return False


def _mega_fetch_url(url: str) -> str:
    """HTTP fetch URL for MEGA folder probes (fragment is client-side only)."""
    return url.split("#")[0]


def _mega_folder_probe(url: str) -> tuple[bool, float | None, str | None]:
    """Validate MEGA folder liveness and parse og: size hint."""
    html, err = _fetch_html(_mega_fetch_url(url))
    if err or not html:
        return False, None, err or "fetch_failed"
    ok, reason = validate_file_host_has_content(url, html)
    size_gb, _file_count = parse_mega_folder_page_meta(html)
    return ok, size_gb, reason


def _pixeldrain_list_has_files(html: str, url: str) -> bool:
    low = (html or "").lower()
    if "no files" in low or "not found" in low:
        return False
    if "/l/" in url.lower():
        return "filesize" in low or "download" in low or "list_item" in low
    return True


def validate_file_host_has_content(url: str, html: str | None = None) -> tuple[bool, str | None]:
    """Returns (ok, reason). Rejects empty/dead mega folders and dead paste targets."""
    from app.services.keep2share_client import check_url_alive, is_k2s_host

    if is_k2s_host(url):
        ok, reason = check_url_alive(url)
        return ok, reason

    host = (urlparse(url).hostname or "").lower()
    body = html
    if body is None:
        body, err = _fetch_html(url)
        if err or not body:
            return False, err or "fetch_failed"
    low = body.lower()
    if any(m in low for m in _dead_body_markers()):
        return False, "dead_or_empty"
    if "mega.nz" in host or "mega.co.nz" in host:
        if "/folder/" in url.lower() and not _mega_folder_has_files(body):
            return False, "mega_folder_empty"
    if "pixeldrain.com" in host and not _pixeldrain_list_has_files(body, url):
        return False, "pixeldrain_empty"
    return True, None


def _soft_check_live(url: str) -> bool:
    """Liveness + non-empty check where HTML allows."""
    host = (urlparse(url).hostname or "").lower()
    try:
        with httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            r = client.get(url)
        if r.status_code >= 400:
            return False
        body = r.text or ""
        ok, _reason = validate_file_host_has_content(url, body)
        return ok
    except Exception:
        return False


def _resolve_obfuscated(url: str) -> tuple[str | None, str | None]:
    return resolve_obfuscated_url(url)


def _unwrap_paste(url: str, html: str | None = None) -> list[ExtractedUrl]:
    text = html
    if text is None:
        text, err = _fetch_html(url)
        if err or not text:
            return []
    found = extract_urls_from_text(text)
    for mega in extract_mega_urls_from_html(text):
        if not any(mega == f.url for f in found):
            found.append(
                ExtractedUrl(
                    url=mega,
                    host_kind="file_host",
                    size_gb_hint=parse_size_gb_hint(text),
                )
            )
    return found


def resolve_to_file_host(
    input_url: str,
    *,
    max_hops: int = _MAX_RESOLVE_HOPS,
) -> MegaLinkPipelineResult:
    """
    Walk obfuscated → paste → file-host chain.
    Does not write DB — caller creates loot_modifier / archive rows.
    """
    res = MegaLinkPipelineResult(ok=False, input_url=input_url.strip())
    current = res.input_url
    if not current.startswith(("http://", "https://")):
        res.error = "invalid_url"
        return res

    for _ in range(max_hops):
        res.hops.append(current)
        kind = classify_url_host(current)

        if kind == "file_host":
            from app.services.keep2share_client import is_k2s_host

            size_hint = parse_size_gb_hint(current)
            if is_k2s_host(current):
                ok, reason = validate_file_host_has_content(current)
                if not ok:
                    res.error = reason or "k2s_dead"
                    return res
            elif _is_mega_folder(current):
                live, og_gb, err_reason = _mega_folder_probe(current)
                if not live:
                    res.error = err_reason or "destination_dead"
                    return res
                if og_gb is not None:
                    size_hint = og_gb
            elif not _soft_check_live(current):
                res.error = "destination_dead"
                return res
            res.destination_url = current
            res.size_gb_hint = size_hint
            res.min_rarity_tier = volume_to_rarity_tier(
                size_gb=res.size_gb_hint,
                host_kind=kind,
                is_folder=_is_mega_folder(current),
            )
            res.ok = True
            return res

        if kind == "gallery_bunkr":
            res.destination_url = current.split("#")[0]
            res.size_gb_hint = parse_size_gb_hint(current)
            res.min_rarity_tier = volume_to_rarity_tier(
                size_gb=res.size_gb_hint,
                host_kind="file_host",
                is_folder="/a/" in current.lower(),
            )
            res.ok = True
            return res

        if kind == "obfuscated":
            nxt, err = _resolve_obfuscated(current)
            if err or not nxt:
                res.error = err or "bypass_failed"
                return res
            current = nxt
            continue

        if kind in ("paste", "sophon", "other"):
            inner = _unwrap_paste(current)
            best = pick_best_file_url(inner)
            if best and best.host_kind == "file_host":
                current = best.url
                res.size_gb_hint = best.size_gb_hint
                continue
            if best and best.host_kind in ("paste", "obfuscated", "sophon"):
                current = best.url
                continue
            # Follow redirect for sophon short links
            html, _ = _fetch_html(current)
            if html:
                inner2 = _unwrap_paste(current, html)
                best2 = pick_best_file_url(inner2)
                if best2:
                    current = best2.url
                    res.size_gb_hint = best2.size_gb_hint
                    continue
            res.error = "no_file_host_in_paste"
            return res

        res.error = f"unsupported_host:{kind}"
        return res

    res.error = "max_hops_exceeded"
    return res


def lv_wrap_destination(destination_url: str) -> str:
    import os

    if (os.getenv("TBCC_PACK_USE_LEGACY_GATE_WRAP") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return legacy_wrap_destination(destination_url)
    gates = wrap_pack_gates_on_ingest(destination_url)
    return gates.primary_url


def build_modifier_payload(
    pipeline: MegaLinkPipelineResult,
    *,
    label: str | None = None,
    archive_tags: str | None = None,
    source_note: str = "mega_pipeline",
) -> dict[str, Any]:
    if not pipeline.ok or not pipeline.destination_url:
        raise ValueError(pipeline.error or "pipeline_not_ok")
    gates = wrap_pack_gates_on_ingest(pipeline.destination_url)
    pipeline.lv_wrapped_url = gates.primary_url
    host = urlparse(pipeline.destination_url).hostname or "pack"
    tier = pipeline.min_rarity_tier
    note = f"{source_note}|dest={pipeline.destination_url[:200]}"
    if gates.gate_adm_url:
        note = f"{note}|gate_adm={gates.gate_adm_url[:200]}"
    return {
        "kind": "mega_pack",
        "label": (label or host)[:256],
        "target_url": gates.primary_url,
        "min_rarity_tier": tier,
        "rarity_focus": float(max(tier, 5)),
        "weight_base": 1.0,
        "bypass_vip": False,
        "active": True,
        "source_note": note,
        "tags": archive_tags,
        "size_gb_hint": pipeline.size_gb_hint,
        "hops": pipeline.hops,
        "gate_adm_url": gates.gate_adm_url,
        "gate_lv_url": gates.gate_lv_url,
    }


def process_archive_entry_value(
    url: str,
    *,
    label: str | None = None,
    tags: str | None = None,
    description: str | None = None,
) -> MegaLinkPipelineResult:
    """Resolve a master-archive URL through the full pipeline."""
    res = resolve_to_file_host(url)
    if not res.ok:
        return res
    if description and not label:
        label = description[:256]
    elif tags and not label:
        label = tags.split(",")[0].strip()[:256]
    try:
        build_modifier_payload(res, label=label, archive_tags=tags, source_note="master_archive")
    except ValueError:
        pass
    return res
