"""Wire Erome album URLs into pack pool modifiers + promo copy."""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.loot import LootModifier
from app.services.aof_packs_post_copy import (
    display_pack_name,
    merge_pack_source_note,
    parse_pack_source_note,
    resolve_pack_gate_urls,
)
from app.services.loot_pack_pool import refresh_aof_packs_scheduler

EROME_PROMO_MARKER = "erome_promo"


@dataclass
class EromeWireResult:
    ok: bool
    modifier_id: int | None = None
    album_url: str | None = None
    promo_caption: str | None = None
    promo_note_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "modifier_id": self.modifier_id,
            "album_url": self.album_url,
            "promo_caption": self.promo_caption,
            "promo_note_path": self.promo_note_path,
            "error": self.error,
        }


def erome_watermark_required() -> bool:
    raw = (os.getenv("TBCC_EROME_WATERMARK") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def build_erome_promo_caption(
    album_url: str,
    label: str,
    *,
    mega_dest_url: str | None = None,
    gate_url: str | None = None,
) -> str:
    """Telegram HTML promo block for an Erome teaser album."""
    name = display_pack_name(label)
    lines = [
        f"<b>{html.escape(name)}</b> — AOF Network teaser",
        (
            f"🎬 <b>Erome gallery</b> ↘️\n"
            f'<a href="{html.escape(album_url, quote=True)}">View watermarked preview</a>'
        ),
    ]
    if mega_dest_url:
        lines.append(
            f"📦 <b>Full pack</b> ↘️\n"
            f'<a href="{html.escape(mega_dest_url, quote=True)}">MEGA unlock</a>'
        )
    from app.services.utm_links import allmylinks_tracked_url, slug_utm_value

    hub = allmylinks_tracked_url(
        source="erome",
        medium="album",
        campaign=slug_utm_value(label, fallback="pack_teaser"),
        content=slug_utm_value(album_url.rsplit("/", 1)[-1], fallback="gallery"),
    )
    if hub:
        lines.append(
            f"🌐 <b>AOF Network</b> ↘️\n" f'<a href="{html.escape(hub, quote=True)}">All links</a>'
        )
    if gate_url:
        lines.append(
            f"🔗 <b>Unlock</b> ↘️\n" f'<a href="{html.escape(gate_url, quote=True)}">Gated download</a>'
        )
    return "\n\n".join(lines)


def _write_promo_note(modifier_id: int, caption: str) -> str:
    from app.services.import_pipeline import tbcc_run_dir

    d = tbcc_run_dir() / "erome-promo"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"mod_{modifier_id}_promo.html"
    path.write_text(caption.strip() + "\n", encoding="utf-8")
    return str(path)


def wire_erome_album_to_modifier(
    db: Session,
    *,
    album_url: str,
    label: str,
    modifier_id: int | None = None,
    mega_folder: str | None = None,
    mega_dest_url: str | None = None,
    size_gb: float | None = None,
    refresh_scheduler: bool = True,
) -> EromeWireResult:
    """Attach Erome album URL to pack pool modifier + save promo caption template."""
    url = (album_url or "").strip()
    if not url.startswith("https://") or "erome.com/a/" not in url:
        return EromeWireResult(ok=False, error="invalid_erome_album_url")

    lbl = (label or mega_folder or "AOF Pack").strip()[:256]
    mod: LootModifier | None = None
    if modifier_id is not None:
        mod = db.query(LootModifier).filter(LootModifier.id == int(modifier_id)).first()
        if not mod:
            return EromeWireResult(ok=False, error=f"modifier_not_found:{modifier_id}")

    if mod is None:
        note = f"{EROME_PROMO_MARKER}|erome={url[:200]}"
        if mega_folder:
            note = f"{note}|theme={re.sub(r'[|]', '', mega_folder)[:120]}"
        mod = LootModifier(
            kind="mega_pack",
            label=lbl,
            target_url=url[:512],
            weight_base=1.0,
            rarity_focus=5.0,
            min_rarity_tier=3,
            active=True,
            source_note=note[:2000],
        )
        db.add(mod)
        db.flush()
    else:
        meta = parse_pack_source_note(mod.source_note)
        mod.source_note = merge_pack_source_note(
            mod.source_note or "",
            erome_url=url,
            theme=meta.theme or lbl,
            size_gb=size_gb if size_gb is not None else meta.size_gb,
            destination_url=meta.destination_url or mega_dest_url,
            gate_lv_url=meta.gate_lv_url,
            gate_adm_url=meta.gate_adm_url,
        )
        if not mod.target_url or "erome.com" in (mod.target_url or ""):
            mod.target_url = url[:512]

    gate = resolve_pack_gate_urls(mod)
    promo = build_erome_promo_caption(
        url,
        lbl,
        mega_dest_url=mega_dest_url or gate.destination_url,
        gate_url=gate.gate_lv_url or gate.gate_adm_url or mod.target_url,
    )
    promo_path = _write_promo_note(int(mod.id), promo)
    base_note = (mod.source_note or "").split("|promo_note_path=")[0]
    mod.source_note = f"{base_note}|promo_note_path={promo_path}"[:2000]

    try:
        from app.services.growth_attribution import EVENT_EROME_ALBUM_PUBLISHED, record_growth_attribution

        record_growth_attribution(
            db,
            event_type=EVENT_EROME_ALBUM_PUBLISHED,
            attach_latest_delivery=False,
            extra={
                "album_url": url,
                "label": lbl,
                "modifier_id": int(mod.id),
                "mega_folder": mega_folder,
            },
        )
    except Exception:
        pass

    db.commit()
    db.refresh(mod)

    if refresh_scheduler:
        try:
            refresh_aof_packs_scheduler(db)
        except Exception:
            pass

    return EromeWireResult(
        ok=True,
        modifier_id=int(mod.id),
        album_url=url,
        promo_caption=promo,
        promo_note_path=promo_path,
    )


def wire_batch_results(
    db: Session,
    results: list[dict[str, Any]],
    *,
    refresh_scheduler: bool = True,
) -> list[EromeWireResult]:
    wired: list[EromeWireResult] = []
    for row in results:
        if not row.get("ok") or not row.get("album_url"):
            wired.append(EromeWireResult(ok=False, error=row.get("error") or "upload_failed"))
            continue
        wired.append(
            wire_erome_album_to_modifier(
                db,
                album_url=str(row["album_url"]),
                label=str(row.get("title") or row.get("label") or row.get("mega_folder") or "AOF Pack"),
                modifier_id=row.get("modifier_id"),
                mega_folder=row.get("mega_folder"),
                mega_dest_url=row.get("mega_dest_url"),
                size_gb=row.get("size_gb"),
                refresh_scheduler=False,
            )
        )
    if refresh_scheduler:
        try:
            refresh_aof_packs_scheduler(db)
        except Exception:
            pass
    return wired
