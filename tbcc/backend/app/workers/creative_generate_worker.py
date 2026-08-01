"""Celery: optional creative asset generation from catalog (Gemini primary)."""

from __future__ import annotations

import logging
import os

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


def creative_gen_enabled() -> bool:
    return (os.getenv("TBCC_CREATIVE_GEN_ENABLED") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def creative_gen_provider() -> str:
    return (os.getenv("TBCC_CREATIVE_GEN_PROVIDER") or "gemini").strip().lower()


@celery.task(name="app.workers.creative_generate_worker.run_creative_generate_tick")
def run_creative_generate_tick(*, limit: int = 3) -> dict:
    if not creative_gen_enabled():
        return {"ok": True, "skipped": True, "reason": "TBCC_CREATIVE_GEN_ENABLED=0"}

    from app.database.session import SessionLocal
    from app.services.creative_rag import search_creative

    provider = creative_gen_provider()
    report: dict = {"ok": True, "provider": provider, "generated": 0, "errors": []}

    db = SessionLocal()
    try:
        rows = search_creative(
            db,
            entry_type="image_prompt",
            limit=max(1, min(int(limit), 10)),
            require_asset=False,
        )
        for row in rows:
            if row.asset_url:
                continue
            key = (row.catalog_key or "").strip()
            if not key:
                continue
            try:
                if provider == "perchance":
                    report["errors"].append(f"{key}: perchance_manual_required")
                    continue
                from app.services.gemini_promo_generate import generate_image_bytes

                body = (row.body or "").strip()
                if not body:
                    continue
                image_bytes = generate_image_bytes(prompt=body, aspect_ratio="9:16")
                if not image_bytes:
                    report["errors"].append(f"{key}: empty_bytes")
                    continue
                from app.services.r2_promo_upload import upload_bytes_to_r2

                uploaded = upload_bytes_to_r2(
                    image_bytes,
                    filename=f"creative-{key}.png",
                    destination="sfw-x-promo",
                )
                url = uploaded.get("direct_url")
                if url:
                    row.asset_url = url
                    row.use_count = int(row.use_count or 0) + 1
                    db.commit()
                    report["generated"] += 1
            except Exception as e:
                logger.warning("creative_generate key=%s failed: %s", key, e)
                report["errors"].append(f"{key}: {str(e)[:120]}")
    finally:
        db.close()

    return report
