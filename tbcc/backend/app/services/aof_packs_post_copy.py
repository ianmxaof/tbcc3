"""AOF PACKS channel post copy: model/theme, size, download CTA, preview media pairing."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.loot import LootModifier
from app.models.media import Media

PACK_MOD_TAG_PREFIX = "pack_mod:"
PACK_LABEL_TAG_PREFIX = "pack_label:"
MAX_PACK_PREVIEW_IMAGES = 5
MAX_PACK_CAPTION_SLOTS = 8

_SIZE_GB_RE = re.compile(r"\|size_gb=([\d.]+)")
_PREVIEW_IDS_RE = re.compile(r"\|preview_ids=([\d,]+)")
_THEME_RE = re.compile(r"\|theme=([^|]+)")
_CONTENTS_RE = re.compile(r"\|contents=([^|]+)")
_DEST_RE = re.compile(r"\|dest=([^|]+)")
_GATE_LV_RE = re.compile(r"\|gate_lv=([^|]+)")
_GATE_ADM_RE = re.compile(r"\|gate_adm=([^|]+)")
_EROME_RE = re.compile(r"\|erome=([^|]+)")
_LABEL_GB_RE = re.compile(r"(\d+(?:\.\d+)?)\s*gb\b", re.I)


@dataclass
class PackPostMeta:
    size_gb: float | None = None
    preview_media_ids: tuple[int, ...] = ()
    theme: str | None = None
    contents: tuple[str, ...] = ()
    destination_url: str | None = None
    gate_lv_url: str | None = None
    gate_adm_url: str | None = None
    erome_url: str | None = None


def _a_tag(lv_url: str, anchor: str) -> str:
    return f'<a href="{html.escape(lv_url, quote=True)}">{html.escape(anchor)}</a>'


def parse_pack_source_note(note: str | None) -> PackPostMeta:
    raw = (note or "").strip()
    meta = PackPostMeta()
    m = _SIZE_GB_RE.search(raw)
    if m:
        try:
            meta.size_gb = float(m.group(1))
        except ValueError:
            pass
    m = _PREVIEW_IDS_RE.search(raw)
    if m:
        ids: list[int] = []
        for part in m.group(1).split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        meta.preview_media_ids = tuple(ids)
    m = _THEME_RE.search(raw)
    if m:
        meta.theme = m.group(1).strip()[:120] or None
    m = _CONTENTS_RE.search(raw)
    if m:
        parts = [p.strip() for p in m.group(1).split(";") if p.strip()]
        meta.contents = tuple(parts[:20])
    m = _DEST_RE.search(raw)
    if m:
        meta.destination_url = m.group(1).strip() or None
    m = _GATE_LV_RE.search(raw)
    if m:
        meta.gate_lv_url = m.group(1).strip() or None
    m = _GATE_ADM_RE.search(raw)
    if m:
        meta.gate_adm_url = m.group(1).strip() or None
    m = _EROME_RE.search(raw)
    if m:
        meta.erome_url = m.group(1).strip() or None
    return meta


def merge_pack_source_note(
    note: str,
    *,
    size_gb: float | None = None,
    preview_ids: list[int] | None = None,
    theme: str | None = None,
    contents: list[str] | None = None,
    destination_url: str | None = None,
    gate_lv_url: str | None = None,
    gate_adm_url: str | None = None,
    erome_url: str | None = None,
) -> str:
    """Append or replace pack metadata tokens on loot_modifiers.source_note."""
    base = (note or "").strip()
    for pattern in (_SIZE_GB_RE, _PREVIEW_IDS_RE, _THEME_RE, _CONTENTS_RE, _GATE_LV_RE, _GATE_ADM_RE, _EROME_RE):
        base = pattern.sub("", base)

    if size_gb is not None and size_gb > 0:
        base = f"{base}|size_gb={size_gb:.2f}".rstrip("|")
    if preview_ids:
        uniq = []
        seen: set[int] = set()
        for mid in preview_ids:
            i = int(mid)
            if i not in seen:
                seen.add(i)
                uniq.append(str(i))
        if uniq:
            base = f"{base}|preview_ids={','.join(uniq)}"
    if theme:
        safe = re.sub(r"[|]", "", theme.strip())[:120]
        if safe:
            base = f"{base}|theme={safe}"
    if contents:
        safe_items = []
        for item in contents:
            s = re.sub(r"[|;]", "", (item or "").strip())[:80]
            if s:
                safe_items.append(s)
        if safe_items:
            base = f"{base}|contents={';'.join(safe_items[:20])}"
    if destination_url and "|dest=" not in base:
        base = f"{base}|dest={destination_url[:200]}"
    if gate_lv_url:
        base = f"{base}|gate_lv={gate_lv_url.strip()[:200]}"
    if gate_adm_url:
        base = f"{base}|gate_adm={gate_adm_url.strip()[:200]}"
    if erome_url:
        base = f"{base}|erome={erome_url.strip()[:200]}"
    return base[:2000]


def pack_meta_from_modifier(mod: LootModifier) -> PackPostMeta:
    meta = parse_pack_source_note(mod.source_note)
    if meta.size_gb is None:
        m = _LABEL_GB_RE.search(mod.label or "")
        if m:
            try:
                meta.size_gb = float(m.group(1))
            except ValueError:
                pass
    if not meta.theme:
        lbl = display_pack_name(mod.label)
        if lbl and lbl.lower() not in ("aof pack", "pack"):
            meta.theme = lbl
    return meta


def display_pack_name(label: str | None) -> str:
    """Human pack / model name from loot_modifiers.label (strip URL tails)."""
    raw = (label or "").strip()
    if not raw:
        return "AOF Pack"
    for sep in (" — ", " - ", " – ", " | ", " —", " -"):
        if sep in raw:
            left, _, right = raw.partition(sep)
            right = right.strip()
            if right.startswith("http") or "://" in right or right.lower().startswith("www."):
                raw = left.strip()
                break
    if raw.startswith("http") or "://" in raw:
        return "AOF Pack"
    cleaned = re.sub(r"\s+", " ", raw).strip()
    if cleaned.lower() in ("aof pack", "pack", "aof pack drop"):
        return "AOF Pack"
    return cleaned[:120] or "AOF Pack"


def format_pack_size_line(size_gb: float | None) -> str:
    if size_gb is None or size_gb <= 0:
        return "💾 <b>Size:</b> see folder after unlock"
    if size_gb >= 100:
        text = f"{size_gb:.0f} GB"
    elif size_gb >= 10:
        text = f"{size_gb:.0f} GB"
    else:
        text = f"{size_gb:.1f} GB"
    return f"💾 <b>{html.escape(text)}</b> curated mega parcel"


def resolve_pack_gate_urls(mod: LootModifier, fallback_gate: str | None = None) -> PackPostMeta:
    """Resolve dual gates from source_note with legacy target_url fallbacks."""
    from app.services.pack_gate_wrap import _is_admaven_gate, _is_dynamic_linkvertise
    from app.services.link_gate_provider import is_linkvertise_host

    meta = pack_meta_from_modifier(mod)
    target_parts = (mod.target_url or "").strip().split()
    target = target_parts[0] if target_parts else ""

    if not meta.gate_adm_url and target and _is_admaven_gate(target):
        meta.gate_adm_url = target
    if not meta.gate_lv_url and target and is_linkvertise_host(target) and not _is_dynamic_linkvertise(target):
        meta.gate_lv_url = target

    fb_parts = (fallback_gate or "").strip().split()
    fb = fb_parts[0] if fb_parts else ""
    if not meta.gate_adm_url and fb and _is_admaven_gate(fb):
        meta.gate_adm_url = fb
    if not meta.gate_lv_url and fb and is_linkvertise_host(fb) and not _is_dynamic_linkvertise(fb):
        meta.gate_lv_url = fb

    return meta


def format_pack_contents_block(meta: PackPostMeta, mod: LootModifier) -> str:
    """Competitor-style bullet list of what's inside the pack."""
    lines: list[str] = list(meta.contents)
    if not lines:
        name = display_pack_name(mod.label)
        if name and name.lower() not in ("aof pack", "pack"):
            lines = [name]
        elif meta.theme:
            lines = [meta.theme]
    if not lines:
        return ""
    bullets = "\n".join(f"• {html.escape(line)}" for line in lines[:12])
    return f"👇 <b>NEW PACK CONTENTS</b> 👇\n{bullets}"


def build_pack_drop_caption(
    mod: LootModifier,
    gate_url: str,
    footer: str,
    meta: PackPostMeta | None = None,
) -> str:
    """Competitor-style PACKS post: model/theme, size, Linkvertise + AdMaven download CTAs."""
    meta = meta or resolve_pack_gate_urls(mod, gate_url)
    name = display_pack_name(mod.label)
    if meta.theme and meta.theme.lower() not in (name.lower(), "aof pack"):
        name = meta.theme

    size_line = format_pack_size_line(meta.size_gb)
    contents_block = format_pack_contents_block(meta, mod)
    host_hint = ""
    if meta.destination_url:
        try:
            from urllib.parse import urlparse

            host = urlparse(meta.destination_url).hostname or ""
            if host:
                host_hint = f" · {html.escape(host.replace('www.', ''))}"
        except Exception:
            pass

    gate_lines: list[str] = []
    if meta.erome_url:
        gate_lines.append(f"🎬 <b>Erome teaser</b> ↘️\n{_a_tag(meta.erome_url, 'Preview gallery')}")
    if meta.gate_lv_url:
        gate_lines.append(f"🔗 <b>Linkvertise</b> ↘️\n{_a_tag(meta.gate_lv_url, 'Unlock via Linkvertise')}")
    else:
        gate_lines.append("🔗 <b>Linkvertise</b> — <i>provisioning soon · use AdMaven below</i>")

    if meta.gate_adm_url:
        gate_lines.append(f"🔗 <b>AdMaven</b> ↘️\n{_a_tag(meta.gate_adm_url, 'Unlock via AdMaven')}")
    elif meta.gate_lv_url:
        gate_lines.append("🔗 <b>AdMaven</b> — <i>not configured</i>")
    else:
        fb = (gate_url or mod.target_url or "").strip().split()[0]
        if fb:
            gate_lines = [f"🎯 <b>MAIN LINK</b> ↘️\n{_a_tag(fb, 'Download pack')}"]

    body = (
        f"📦 <b>{html.escape(name)}</b>\n"
        f"{size_line}{host_hint}"
    )
    if contents_block:
        body = f"{body}\n\n{contents_block}"
    body = (
        f"{body}\n\n"
        + "\n\n".join(gate_lines)
        + "\n\n<i>One ad step per gate · VIP skips ads</i>"
    )
    foot = (footer or "").strip()
    return f"{body}{foot}" if foot else body


def _slug_label(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return s[:80]


def resolve_pack_preview_media_ids(
    db: Session,
    mod: LootModifier,
    pool_id: int,
    *,
    limit: int = MAX_PACK_PREVIEW_IMAGES,
) -> list[int]:
    """Preview stills for this pack: explicit preview_ids, then tag match in promo pool."""
    meta = parse_pack_source_note(mod.source_note)
    out: list[int] = []
    seen: set[int] = set()

    def _add(mid: int) -> None:
        if mid in seen or len(out) >= limit:
            return
        row = (
            db.query(Media.id)
            .filter(Media.id == mid, Media.pool_id == pool_id, Media.status == "approved")
            .first()
        )
        if row:
            seen.add(mid)
            out.append(mid)

    for mid in meta.preview_media_ids:
        _add(int(mid))

    tag_mod = f"{PACK_MOD_TAG_PREFIX}{mod.id}"
    tag_rows = (
        db.query(Media.id)
        .filter(
            Media.pool_id == pool_id,
            Media.status == "approved",
            Media.tags.isnot(None),
            Media.tags.contains(tag_mod),
        )
        .order_by(Media.id.asc())
        .limit(limit)
        .all()
    )
    for (mid,) in tag_rows:
        _add(int(mid))

    slug = _slug_label(display_pack_name(mod.label))
    if slug and slug not in ("aof-pack", "pack"):
        label_tag = f"{PACK_LABEL_TAG_PREFIX}{slug}"
        label_rows = (
            db.query(Media.id)
            .filter(
                Media.pool_id == pool_id,
                Media.status == "approved",
                Media.tags.isnot(None),
                Media.tags.contains(label_tag),
            )
            .order_by(Media.id.asc())
            .limit(limit)
            .all()
        )
        for (mid,) in label_rows:
            _add(int(mid))

    return out


def build_pack_post_album_variant(
    db: Session,
    mod: LootModifier,
    pool_id: int,
    promo_media_id: int | None,
    *,
    max_previews: int = MAX_PACK_PREVIEW_IMAGES,
    previews_only_when_available: bool = False,
) -> dict[str, Any]:
    """Album slot: brand promo first, then pack preview grid (up to max_previews)."""
    previews = resolve_pack_preview_media_ids(db, mod, pool_id, limit=max_previews)
    mids: list[int] = []
    if previews_only_when_available and previews:
        mids = list(previews[:max_previews])
        return {"media_ids": mids, "attachment_urls": []}
    if promo_media_id:
        mids.append(int(promo_media_id))
    for pid in previews:
        if pid not in mids:
            mids.append(pid)
    if not mids and promo_media_id:
        mids = [int(promo_media_id)]
    return {"media_ids": mids[: max_previews + 1], "attachment_urls": []}


def attach_preview_media_to_modifier(
    db: Session,
    mod: LootModifier,
    media_ids: list[int],
    *,
    pool_id: int | None = None,
) -> dict[str, Any]:
    """Persist preview_ids on modifier + tag media rows for discovery."""
    ids = [int(x) for x in media_ids if int(x) > 0]
    if not ids:
        return {"ok": False, "error": "no_media_ids"}

    existing = list(parse_pack_source_note(mod.source_note).preview_media_ids)
    merged = list(existing)
    seen = set(existing)
    for mid in ids:
        if mid not in seen:
            seen.add(mid)
            merged.append(mid)

    mod.source_note = merge_pack_source_note(
        mod.source_note or "",
        preview_ids=merged,
    )

    tag = f"{PACK_MOD_TAG_PREFIX}{mod.id}"
    q = db.query(Media).filter(Media.id.in_(ids))
    if pool_id is not None:
        q = q.filter(Media.pool_id == pool_id)
    rows = q.all()
    tagged = 0
    for row in rows:
        tags = [t.strip() for t in (row.tags or "").split(",") if t.strip()]
        if tag not in tags:
            tags.append(tag)
            row.tags = ",".join(tags)[:512]
            tagged += 1

    db.commit()
    return {"ok": True, "modifier_id": mod.id, "preview_ids": merged, "media_tagged": tagged}
