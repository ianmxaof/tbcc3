"""Zip / media flywheel: hybrid host (R2 vs Pixeldrain) → gate wrap → loot/shop register."""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.data.loot_lane_economy import PACK_DROP
from app.services.bundle_storage import MAX_BUNDLE_ZIP_BYTES, is_zip_magic
from app.services.pack_gate_wrap import wrap_pack_gates_on_ingest
from app.services.pixeldrain_upload import PixeldrainUploadError, pixeldrain_configured, upload_bytes_to_pixeldrain

logger = logging.getLogger(__name__)

HostKind = Literal["r2", "pixeldrain", "auto"]
FlywheelAction = Literal["host_gated", "loot_modifier", "shop_bundle"]

# Below this size (and auto mode) prefer R2; large packs go to Pixeldrain.
DEFAULT_R2_MAX_BYTES = 40 * 1024 * 1024
# Absolute ceiling for a single flywheel upload (Pixeldrain path).
DEFAULT_FLYWHEEL_MAX_BYTES = 500 * 1024 * 1024


def r2_max_bytes() -> int:
    raw = (os.getenv("TBCC_ZIP_FLYWHEEL_R2_MAX_BYTES") or "").strip()
    try:
        return max(1_000_000, int(raw)) if raw else DEFAULT_R2_MAX_BYTES
    except ValueError:
        return DEFAULT_R2_MAX_BYTES


def flywheel_max_bytes() -> int:
    raw = (os.getenv("TBCC_ZIP_FLYWHEEL_MAX_BYTES") or "").strip()
    try:
        return max(r2_max_bytes(), int(raw)) if raw else DEFAULT_FLYWHEEL_MAX_BYTES
    except ValueError:
        return DEFAULT_FLYWHEEL_MAX_BYTES


def choose_host(*, size: int, host: HostKind = "auto", prefer_r2: bool = False) -> HostKind:
    """Hybrid router: small/SFW → R2; large → Pixeldrain."""
    if host in ("r2", "pixeldrain"):
        return host  # type: ignore[return-value]
    if prefer_r2 or size <= r2_max_bytes():
        return "r2"
    return "pixeldrain"


def _safe_leaf(filename: str) -> str:
    base = Path(filename or "pack.zip").name
    base = re.sub(r"[^\w.\-]+", "_", base).strip("._") or "pack.zip"
    return base[:120]


@dataclass
class FlywheelResult:
    ok: bool
    host: str
    destination_url: str
    primary_url: str
    gate_adm_url: str | None
    filename: str
    bytes: int
    modifier_id: int | None = None
    plan_id: int | None = None
    plan_name: str | None = None
    object_key: str | None = None
    detail: str | None = None
    gate_lv_url: str | None = None
    gate_workink_url: str | None = None
    gate_provider: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "host": self.host,
            "destination_url": self.destination_url,
            "primary_url": self.primary_url,
            "gate_adm_url": self.gate_adm_url,
            "gate_lv_url": self.gate_lv_url,
            "gate_workink_url": self.gate_workink_url,
            "gate_provider": self.gate_provider,
            "filename": self.filename,
            "bytes": self.bytes,
            "modifier_id": self.modifier_id,
            "plan_id": self.plan_id,
            "plan_name": self.plan_name,
            "object_key": self.object_key,
            "detail": self.detail,
        }


def _upload_r2(data: bytes, *, filename: str) -> tuple[str, str]:
    from app.services.r2_promo_upload import upload_bytes_to_r2

    key_prefix = (os.getenv("TBCC_ZIP_FLYWHEEL_R2_PREFIX") or "packs/flywheel").strip().strip("/")
    leaf = _safe_leaf(filename)
    object_key = f"{key_prefix}/{uuid.uuid4().hex[:12]}_{leaf}"
    result = upload_bytes_to_r2(
        data,
        filename=leaf,
        object_key=object_key,
        content_type="application/zip" if leaf.lower().endswith(".zip") else "application/octet-stream",
    )
    url = (result.get("direct_url") or result.get("url") or "").strip()
    if not url:
        raise RuntimeError("r2_upload_missing_url")
    return url, str(result.get("object_key") or object_key)


def _upload_pixeldrain(data: bytes, *, filename: str) -> tuple[str, str | None]:
    out = upload_bytes_to_pixeldrain(data, filename=filename)
    return out["public_url"], out.get("id")


def resolve_curated_pack_plan_id(db: Session, plan_id: int | None = None) -> tuple[int, str]:
    from app.models.subscription_plan import SubscriptionPlan

    if plan_id is not None:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
        if not plan:
            raise ValueError("plan_not_found")
        return int(plan.id), str(plan.name)

    name = PACK_DROP.sku_name
    plan = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.name == name, SubscriptionPlan.is_active.is_(True))
        .first()
    )
    if not plan:
        plan = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.bot_section == "packs", SubscriptionPlan.product_type == "bundle")
            .order_by(SubscriptionPlan.id.asc())
            .first()
        )
    if not plan:
        raise ValueError("curated_pack_plan_missing")
    return int(plan.id), str(plan.name)


def run_zip_flywheel(
    db: Session,
    data: bytes,
    *,
    filename: str = "pack.zip",
    action: FlywheelAction = "host_gated",
    host: HostKind = "auto",
    prefer_r2: bool = False,
    label: str | None = None,
    plan_id: int | None = None,
    source_note: str | None = None,
) -> FlywheelResult:
    """
    Host bytes → gate wrap → optional loot modifier / shop bundle attach.

    ``downloads_promo`` is client-only (extension rename + Chrome download).
    """
    if not data:
        raise ValueError("empty_file")
    if len(data) > flywheel_max_bytes():
        raise ValueError(f"file_too_large max={flywheel_max_bytes()}")

    leaf = _safe_leaf(filename)
    is_zip = leaf.lower().endswith(".zip")
    if is_zip and not is_zip_magic(data[:8]):
        raise ValueError("invalid_zip")

    chosen = choose_host(size=len(data), host=host, prefer_r2=prefer_r2)
    if chosen == "pixeldrain" and not pixeldrain_configured():
        if len(data) <= r2_max_bytes():
            chosen = "r2"
            logger.warning("pixeldrain not configured; falling back to R2")
        else:
            raise PixeldrainUploadError("TBCC_PIXELDRAIN_API_KEY required for large flywheel uploads")

    object_key: str | None = None
    if chosen == "r2":
        dest_url, object_key = _upload_r2(data, filename=leaf)
    else:
        dest_url, object_key = _upload_pixeldrain(data, filename=leaf)

    gates = wrap_pack_gates_on_ingest(dest_url)
    modifier_id: int | None = None
    out_plan_id: int | None = None
    out_plan_name: str | None = None
    detail: str | None = None

    if action == "loot_modifier":
        from app.models.loot import LootModifier

        # Prefer gated primary as the roll target so buyers hit the wrap.
        m = LootModifier(
            kind="mega_pack" if is_zip else "other",
            label=(label or leaf).strip()[:256] or leaf,
            target_url=gates.primary_url,
            weight_base=1.0,
            rarity_focus=7.0,
            min_rarity_tier=5,
            active=True,
            source_note=(source_note or "zip_flywheel").strip()[:512],
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        modifier_id = int(m.id)
        detail = "loot_modifier_created"

    elif action == "shop_bundle":
        if not is_zip:
            raise ValueError("shop_bundle_requires_zip")
        if len(data) > MAX_BUNDLE_ZIP_BYTES:
            raise ValueError(
                f"shop_bundle_too_large max_mib={MAX_BUNDLE_ZIP_BYTES // (1024 * 1024)} "
                "(use host_gated / loot_modifier for larger packs)"
            )
        from app.models.subscription_plan import SubscriptionPlan
        from app.services.bundle_parts import append_bundle_filename, get_bundle_parts
        from app.services.bundle_storage import bundle_zip_nth_path, ensure_bundle_dir
        from app.services.zip_promo_inject import inject_promo_into_zip_path

        pid, pname = resolve_curated_pack_plan_id(db, plan_id)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == pid).first()
        if not plan:
            raise ValueError("plan_not_found")
        if (plan.product_type or "").strip().lower() != "bundle":
            plan.product_type = "bundle"
        existing = get_bundle_parts(plan)
        idx = len(existing)
        ensure_bundle_dir()
        out_path = bundle_zip_nth_path(pid, idx)
        out_path.write_bytes(data)
        inject_promo_into_zip_path(out_path, db)
        try:
            append_bundle_filename(plan, leaf)
        except ValueError as e:
            out_path.unlink(missing_ok=True)
            raise ValueError(str(e)) from e
        db.commit()
        out_plan_id = pid
        out_plan_name = pname
        detail = f"shop_bundle_part_{idx}"

    return FlywheelResult(
        ok=True,
        host=chosen,
        destination_url=gates.destination_url,
        primary_url=gates.primary_url,
        gate_adm_url=gates.gate_adm_url,
        filename=leaf,
        bytes=len(data),
        modifier_id=modifier_id,
        plan_id=out_plan_id,
        plan_name=out_plan_name,
        object_key=object_key,
        detail=detail or "hosted_and_gated",
        gate_lv_url=gates.gate_lv_url,
        gate_workink_url=gates.gate_workink_url,
        gate_provider=gates.provider,
    )
