"""Bundle zip parts: ordered list of .zip files per plan (split packs, N parts)."""

from __future__ import annotations

import json

from app.models.subscription_plan import SubscriptionPlan
from app.services.bundle_storage import (
    MAX_BUNDLE_PARTS,
    bundle_zip2_path,
    bundle_zip_nth_path,
    bundle_zip_path,
)


def get_bundle_parts(plan: SubscriptionPlan) -> list[str]:
    """
    Return original filenames for each on-disk part, in order.
    Prefers bundle_zip_parts_json; falls back to legacy two-name columns.
    """
    raw = plan.bundle_zip_parts_json
    if raw:
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                names = [str(x).strip()[:500] for x in arr if str(x).strip()]
                verified: list[str] = []
                for i, name in enumerate(names):
                    if bundle_zip_nth_path(plan.id, i).is_file():
                        verified.append(name)
                return verified
        except Exception:
            pass
    out: list[str] = []
    if plan.bundle_zip_original_name and bundle_zip_path(plan.id).is_file():
        out.append(plan.bundle_zip_original_name.strip()[:500])
    if plan.bundle_zip2_original_name and bundle_zip2_path(plan.id).is_file():
        out.append(plan.bundle_zip2_original_name.strip()[:500])
    return out


def save_bundle_parts(plan: SubscriptionPlan, parts: list[str]) -> None:
    """Persist ordered filenames; keep legacy columns for first two names."""
    plan.bundle_zip_parts_json = json.dumps(parts) if parts else None
    plan.bundle_zip_original_name = parts[0] if len(parts) >= 1 else None
    plan.bundle_zip2_original_name = parts[1] if len(parts) >= 2 else None


def append_bundle_filename(plan: SubscriptionPlan, filename: str) -> None:
    """Call after bytes were written to bundle_zip_nth_path(plan.id, len(parts))."""
    parts = get_bundle_parts(plan)
    if len(parts) >= MAX_BUNDLE_PARTS:
        raise ValueError("too many parts")
    i = len(parts)
    if not bundle_zip_nth_path(plan.id, i).is_file():
        raise ValueError("expected file on disk")
    parts.append(filename.strip()[:500])
    save_bundle_parts(plan, parts)


def delete_all_bundle_part_files(plan_id: int) -> None:
    for i in range(MAX_BUNDLE_PARTS):
        p = bundle_zip_nth_path(plan_id, i)
        if p.is_file():
            p.unlink()


def delete_bundle_part_at(plan: SubscriptionPlan, index: int) -> None:
    parts = get_bundle_parts(plan)
    if index < 0 or index >= len(parts):
        raise ValueError("invalid part index")
    n = len(parts)
    bundle_zip_nth_path(plan.id, index).unlink(missing_ok=True)
    for j in range(index + 1, n):
        src = bundle_zip_nth_path(plan.id, j)
        dst = bundle_zip_nth_path(plan.id, j - 1)
        if src.is_file():
            dst.unlink(missing_ok=True)
            src.rename(dst)
    new_parts = parts[:index] + parts[index + 1 :]
    save_bundle_parts(plan, new_parts)


def bundle_parts_for_api(plan: SubscriptionPlan) -> list[str]:
    """Filenames exposed in GET /subscription-plans (same as get_bundle_parts)."""
    return get_bundle_parts(plan)
