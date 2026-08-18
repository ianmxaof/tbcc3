"""Pick one affiliate from a sequenced sponsor pack (overlay on rotation)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.data.affiliate_sponsor_packs import (
    META_CURSOR_KEYS,
    PLACEMENT_PACK_ROTATION,
    pack_by_id,
    slots_for_pack,
)
from app.models.promo_affiliate_link import PromoAffiliateLink

if TYPE_CHECKING:
    from app.services.promo_affiliate_rotation import AffiliatePick

logger = logging.getLogger(__name__)


def _row_by_label(db: Session, label: str) -> PromoAffiliateLink | None:
    lab = (label or "").strip()
    if not lab:
        return None
    return (
        db.query(PromoAffiliateLink)
        .filter(PromoAffiliateLink.active.is_(True), PromoAffiliateLink.label == lab)
        .order_by(PromoAffiliateLink.id.asc())
        .first()
    )


def packs_enabled() -> bool:
    """Overlay sponsor packs on rotation. Default on; tests may set 0 for legacy."""
    import os

    raw = (os.getenv("TBCC_SPONSOR_PACKS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def select_pack_id_for_placement(
    db: Session,
    placement: str,
    *,
    advance_meta: bool = False,
) -> str | None:
    """Resolve which pack owns this send for a contested placement."""
    from app.services.promo_affiliate_rotation import _get_cursor

    placement_norm = (placement or "").strip().lower()
    rotation = PLACEMENT_PACK_ROTATION.get(placement_norm)
    if not rotation:
        return None
    if len(rotation) == 1:
        return rotation[0]
    meta_nk = META_CURSOR_KEYS.get(placement_norm)
    if not meta_nk:
        return rotation[0]
    cur = _get_cursor(db, placement_norm, meta_nk)
    idx = int(cur.cursor_index or 0) % len(rotation)
    pack_id = rotation[idx]
    if advance_meta:
        from datetime import datetime

        cur.cursor_index = (idx + 1) % len(rotation)
        cur.updated_at = datetime.utcnow()
    return pack_id


def pick_from_sponsor_pack(
    db: Session,
    placement: str,
    *,
    network_key: str | None = None,
    advance: bool = True,
) -> "AffiliatePick | None":
    """
    Return the next pack slot row for this placement, or None to fall back to legacy rotation.

    Advances meta + pack slot cursors only when a pack row is actually served.
    """
    from app.services.promo_affiliate_rotation import (
        AffiliatePick,
        _get_cursor,
        _row_active,
        row_placements,
    )

    placement_norm = (placement or "").strip().lower()
    if placement_norm not in PLACEMENT_PACK_ROTATION:
        return None
    if not packs_enabled():
        return None

    pack_id = select_pack_id_for_placement(db, placement_norm, advance_meta=False)
    if not pack_id:
        return None
    pack = pack_by_id(pack_id)
    if not pack:
        return None
    if placement_norm not in pack.surfaces:
        return None

    slots = slots_for_pack(pack, network_key=network_key)
    if not slots:
        return None

    available: list[tuple[int, PromoAffiliateLink]] = []
    for slot in slots:
        row = _row_by_label(db, slot.label)
        if row is None or not _row_active(row):
            continue
        if placement_norm not in row_placements(row):
            continue
        available.append((slot.index, row))

    if not available:
        return None

    pack_cursor_nk = f"pack:{pack.id}"
    cur = _get_cursor(db, placement_norm, pack_cursor_nk)
    start = int(cur.cursor_index or 0) % len(available)
    slot_i, row = available[start]

    if advance:
        from datetime import datetime

        cur.cursor_index = (start + 1) % len(available)
        cur.updated_at = datetime.utcnow()
        select_pack_id_for_placement(db, placement_norm, advance_meta=True)

    return AffiliatePick(
        row=row,
        placement=placement_norm,
        network_key=network_key,
        slot_index=slot_i,
    )


def finance_sort_key(label: str) -> tuple[int, str]:
    """Lower sort key = earlier in Checkout FINANCE (Pack A order)."""
    from app.data.affiliate_sponsor_packs import pack_a_finance_label_order

    order = pack_a_finance_label_order()
    lab = (label or "").strip()
    try:
        return (order.index(lab), lab.lower())
    except ValueError:
        return (1000 + len(lab), lab.lower())
