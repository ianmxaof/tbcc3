"""prompt_gate catalog lifecycle — queue, supersede, and provision result application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.models.prompt_gate import (
    PROMPT_GATE_STATUS_FAILED,
    PROMPT_GATE_STATUS_PENDING,
    PROMPT_GATE_STATUS_PROVISIONED,
    PROMPT_GATE_STATUS_SUPERSEDED,
    PROMPT_GATE_STATUS_TAKEDOWN,
    PROMPT_GATE_SURFACE_TELEGRAM_ONLY,
    PromptGate,
)
from app.services.prompt_gate_lookup import active_prompt_gate_row, hash_prompt_body, normalize_prompt_body

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ProvisionWorkItem:
    row: PromptGate
    body: str
    title: str
    reason: str  # pending | failed_retry | takedown_requeue | body_drift


def normalize_prompt_key(key: str) -> str:
    return (key or "").strip().lower()


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _title_for_key(key: str) -> str:
    return f"AOF Prompt {key.replace('_', ' ').title()} Card Lab Access"


def row_prompt_body(row: PromptGate) -> str:
    return (row.prompt_body or row.prompt_ref or "").strip()


def upsert_catalog_row(
    db: Session,
    key: str,
    prompt_body: str,
    *,
    tier: str | None = None,
    prompt_ref: str | None = None,
    surface_policy: str = PROMPT_GATE_SURFACE_TELEGRAM_ONLY,
) -> tuple[PromptGate, str]:
    """
    Insert or refresh a catalog row.

    Returns (row, action) where action is unchanged | updated_pending | queued_drift.
    """
    k = normalize_prompt_key(key)
    body = normalize_prompt_body(prompt_body)
    if not k or not body:
        raise ValueError("key_and_prompt_body_required")

    body_hash = hash_prompt_body(body)
    active = active_prompt_gate_row(db, k)
    if active and active.body_hash == body_hash:
        return active, "unchanged"

    open_row = (
        db.query(PromptGate)
        .filter(
            PromptGate.key == k,
            PromptGate.status.in_((PROMPT_GATE_STATUS_PENDING, PROMPT_GATE_STATUS_FAILED)),
        )
        .order_by(PromptGate.id.desc())
        .first()
    )
    if open_row:
        open_row.prompt_body = body
        open_row.body_hash = body_hash
        open_row.tier = tier or open_row.tier
        open_row.prompt_ref = prompt_ref or open_row.prompt_ref
        open_row.surface_policy = surface_policy or open_row.surface_policy
        if open_row.status == PROMPT_GATE_STATUS_FAILED:
            open_row.status = PROMPT_GATE_STATUS_PENDING
        open_row.updated_at = _utc_now_naive()
        db.commit()
        db.refresh(open_row)
        return open_row, "updated_pending"

    row = PromptGate(
        key=k,
        prompt_body=body,
        body_hash=body_hash,
        status=PROMPT_GATE_STATUS_PENDING,
        tier=tier,
        prompt_ref=prompt_ref,
        surface_policy=surface_policy,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, "queued_drift" if active else "queued_new"


def list_provision_queue(
    db: Session,
    *,
    limit: int | None = None,
    keys: list[str] | None = None,
    include_failed: bool = True,
) -> list[ProvisionWorkItem]:
    """Rows ready for Playwright batch provision (resume-safe)."""
    statuses = [PROMPT_GATE_STATUS_PENDING]
    if include_failed:
        statuses.append(PROMPT_GATE_STATUS_FAILED)

    q = db.query(PromptGate).filter(PromptGate.status.in_(statuses))
    if keys:
        wanted = {normalize_prompt_key(k) for k in keys if k.strip()}
        q = q.filter(PromptGate.key.in_(wanted))
    q = q.order_by(PromptGate.id.asc())
    if limit is not None:
        rows = q.limit(limit).all()
    else:
        rows = q.all()

    out: list[ProvisionWorkItem] = []
    for row in rows:
        body = row_prompt_body(row)
        if not body:
            continue
        reason = "failed_retry" if row.status == PROMPT_GATE_STATUS_FAILED else "pending"
        out.append(
            ProvisionWorkItem(
                row=row,
                body=body,
                title=_title_for_key(row.key),
                reason=reason,
            )
        )
    return out


def apply_provision_success(
    db: Session,
    row: PromptGate,
    lv_url: str,
    *,
    probe: dict[str, Any] | None = None,
) -> None:
    """Mark row provisioned and supersede prior active slug for the same key."""
    row.body_hash = row.body_hash or hash_prompt_body(row_prompt_body(row))
    row.lv_url = (lv_url or "").strip()
    row.status = PROMPT_GATE_STATUS_PROVISIONED
    row.updated_at = _utc_now_naive()
    if probe:
        row.last_probe_at = _utc_now_naive()
        row.last_probe_flags = ",".join(probe.get("flags") or [])

    prior = (
        db.query(PromptGate)
        .filter(
            PromptGate.key == row.key,
            PromptGate.status == PROMPT_GATE_STATUS_PROVISIONED,
            PromptGate.id != row.id,
        )
        .order_by(PromptGate.id.desc())
        .all()
    )
    for old in prior:
        old.status = PROMPT_GATE_STATUS_SUPERSEDED
        old.superseded_by_id = row.id
        old.updated_at = _utc_now_naive()

    db.commit()
    db.refresh(row)


def mark_provision_failed(db: Session, row: PromptGate, *, reason: str | None = None) -> None:
    row.status = PROMPT_GATE_STATUS_FAILED
    row.updated_at = _utc_now_naive()
    if reason:
        flags = (row.last_probe_flags or "").strip()
        row.last_probe_flags = f"{flags},{reason}".strip(",")
    db.commit()


def probe_and_requeue_takedowns(db: Session, *, limit: int | None = None) -> list[ProvisionWorkItem]:
    """
    Probe active slugs; on TAKEDOWN mark old row and queue a fresh pending row (same body).
    """
    from app.services.linkvertise_dashboard_provision import probe_lv_gate

    q = (
        db.query(PromptGate)
        .filter(PromptGate.status == PROMPT_GATE_STATUS_PROVISIONED, PromptGate.lv_url.isnot(None))
        .order_by(PromptGate.id.asc())
    )
    rows = q.limit(limit).all() if limit is not None else q.all()

    queued: list[ProvisionWorkItem] = []
    for row in rows:
        url = (row.lv_url or "").strip()
        if not url:
            continue
        probe = probe_lv_gate(url)
        row.last_probe_at = _utc_now_naive()
        row.last_probe_flags = ",".join(probe.get("flags") or [])
        if "TAKEDOWN" not in (probe.get("flags") or []):
            db.commit()
            continue

        row.status = PROMPT_GATE_STATUS_TAKEDOWN
        row.updated_at = _utc_now_naive()
        db.commit()

        body = row_prompt_body(row)
        if not body:
            continue
        new_row, _action = upsert_catalog_row(
            db,
            row.key,
            body,
            tier=row.tier,
            prompt_ref=row.prompt_ref,
            surface_policy=row.surface_policy or PROMPT_GATE_SURFACE_TELEGRAM_ONLY,
        )
        queued.append(
            ProvisionWorkItem(
                row=new_row,
                body=body,
                title=_title_for_key(new_row.key),
                reason="takedown_requeue",
            )
        )
    return queued


def import_catalog_items(db: Session, items: list[dict[str, Any]]) -> dict[str, int]:
    """Bulk upsert from JSON catalog. Returns action counts."""
    counts = {"unchanged": 0, "updated_pending": 0, "queued_new": 0, "queued_drift": 0, "skipped": 0}
    for raw in items:
        key = str(raw.get("key") or "").strip()
        body = str(raw.get("prompt_body") or raw.get("body") or "").strip()
        if not key or not body:
            counts["skipped"] += 1
            continue
        _row, action = upsert_catalog_row(
            db,
            key,
            body,
            tier=(str(raw.get("tier")).strip() if raw.get("tier") else None),
            prompt_ref=(str(raw.get("prompt_ref")).strip() if raw.get("prompt_ref") else None),
        )
        counts[action] = counts.get(action, 0) + 1
    return counts


def status_counts(db: Session) -> dict[str, int]:
    from sqlalchemy import func

    out: dict[str, int] = {}
    for status, n in (
        db.query(PromptGate.status, func.count(PromptGate.id))
        .group_by(PromptGate.status)
        .all()
    ):
        out[str(status)] = int(n)
    return out
