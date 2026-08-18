"""Conversion playbook engine — capture and re-apply winning client trajectories.

The playbook system is read-only with respect to the Format Engine: it observes
``interaction_format_json`` snapshots and never steers the FE. On conversion the
trajectory is captured as a playbook; later, clients whose psych markers/phase
overlap a stored playbook are matched and the playbook is surfaced to the sales
coach as supplemental guidance.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.conversion_playbook import ConversionPlaybook
from app.services.format_engine import build_behavioral_directive

logger = logging.getLogger(__name__)

MATCH_SCORE_FINANCIAL_INTENT = 3
MATCH_SCORE_TRUST_LEVEL = 2
MATCH_SCORE_SAME_PHASE = 1
PLBOOK_MIN_MATCH_SCORE = 3


def _as_format_dict(format_json: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(format_json, dict):
        return format_json
    if isinstance(format_json, str):
        try:
            data = json.loads(format_json)
            if isinstance(data, dict):
                return data
        except (ValueError, TypeError):
            return {}
    return {}


def _extract_trajectory(fmt: dict[str, Any]) -> list[str]:
    """Ordered, de-duplicated list of phases the client passed through."""
    phases: list[str] = []
    history = fmt.get("phase_history")
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            for key in ("from", "to"):
                val = str(item.get(key) or "").strip()
                if val and val not in phases:
                    phases.append(val)
    current = str(fmt.get("phase") or "").strip()
    if current and current not in phases:
        phases.append(current)
    return phases


def _psych_snapshot(fmt: dict[str, Any]) -> dict[str, Any]:
    markers = fmt.get("psych_markers")
    if isinstance(markers, dict):
        return {k: markers[k] for k in ("financial_intent", "trust_level", "urgency_score") if k in markers}
    return {}


def _message_count(fmt: dict[str, Any]) -> int:
    metrics = fmt.get("metrics")
    if isinstance(metrics, dict):
        try:
            return int(metrics.get("user_messages") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _behavioral_directive(fmt: dict[str, Any]) -> str:
    metrics = fmt.get("metrics") if isinstance(fmt.get("metrics"), dict) else {}
    state = {
        "message_count": _message_count(fmt),
        "phase": str(fmt.get("phase") or "").strip(),
        "distress_events": int(metrics.get("distress_events") or 0),
    }
    return build_behavioral_directive(state) or ""


def _build_summary(fmt: dict[str, Any], trajectory: list[str]) -> str:
    metrics = fmt.get("metrics") if isinstance(fmt.get("metrics"), dict) else {}
    mc = _message_count(fmt)
    distress = int(metrics.get("distress_events") or 0)
    phase = str(fmt.get("phase") or "").strip()
    intent = _psych_snapshot(fmt).get("financial_intent")
    parts = [f"{mc} msgs to conversion"]
    if distress:
        parts.append(f"distress x{distress}")
    if trajectory:
        parts.append(f"phases: {' -> '.join(trajectory)}")
    if phase:
        parts.append(f"final_phase={phase}")
    if intent:
        parts.append(f"intent={intent}")
    return "; ".join(parts)


def save_playbook_on_conversion(
    telegram_user_id: int | None,
    format_json: dict[str, Any] | str | None,
    payment_lane: str,
    outcome: str = "unknown",
    *,
    db: Session | None = None,
) -> ConversionPlaybook | None:
    """Extract trajectory from ``format_json`` and persist a ConversionPlaybook."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        fmt = _as_format_dict(format_json)
        trajectory = _extract_trajectory(fmt)
        pb = ConversionPlaybook(
            telegram_user_id=telegram_user_id,
            phase_trajectory=json.dumps(trajectory, ensure_ascii=False) or None,
            psych_markers_at_conversion=json.dumps(_psych_snapshot(fmt), ensure_ascii=False) or None,
            message_count_at_conversion=_message_count(fmt),
            payment_lane_used=str(payment_lane or "")[:16] or None,
            behavioral_directive_at_conversion=_behavioral_directive(fmt)[:512] or None,
            conversion_outcome=str(outcome or "unknown")[:32],
            format_summary=_build_summary(fmt, trajectory) or None,
            is_active=True,
            times_matched=0,
        )
        db.add(pb)
        db.commit()
        db.refresh(pb)
        return pb
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("playbook save failed uid=%s: %s", telegram_user_id, e)
        return None
    finally:
        if own and db is not None:
            db.close()


def _playbook_phase(pb: ConversionPlaybook) -> str | None:
    try:
        trajectory = json.loads(pb.phase_trajectory) if pb.phase_trajectory else []
    except (ValueError, TypeError):
        trajectory = []
    if isinstance(trajectory, list) and trajectory:
        last = trajectory[-1]
        return str(last).strip() if str(last).strip() else None
    return None


def playbook_match_score(
    pb: ConversionPlaybook,
    psych_markers: dict[str, Any] | None,
    phase: str | None,
) -> int:
    """Score a playbook against the current client's signals."""
    try:
        snapshot = json.loads(pb.psych_markers_at_conversion) if pb.psych_markers_at_conversion else {}
    except (ValueError, TypeError):
        snapshot = {}
    if not isinstance(snapshot, dict):
        snapshot = {}

    markers = psych_markers or {}
    score = 0
    if markers.get("financial_intent") and snapshot.get("financial_intent") == markers.get("financial_intent"):
        score += MATCH_SCORE_FINANCIAL_INTENT
    if markers.get("trust_level") and snapshot.get("trust_level") == markers.get("trust_level"):
        score += MATCH_SCORE_TRUST_LEVEL
    if phase and _playbook_phase(pb) == str(phase).strip().lower():
        score += MATCH_SCORE_SAME_PHASE
    return score


def search_playbooks(
    psych_markers: dict[str, Any] | None,
    phase: str | None,
    message_count: int,
    limit: int = 3,
    *,
    db: Session | None = None,
) -> list[ConversionPlaybook]:
    """Find active playbooks whose conversion profile overlaps the client.

    Returns top-N by score (score >= PLBOOK_MIN_MATCH_SCORE). ``message_count``
    is accepted for call-site symmetry with the sales coach; scoring is driven by
    psych-marker/phase overlap only.
    """
    _ = message_count
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = (
            db.query(ConversionPlaybook)
            .filter(ConversionPlaybook.is_active.is_(True))
            .order_by(ConversionPlaybook.times_matched.desc(), ConversionPlaybook.id.desc())
            .all()
        )
        scored = [
            (playbook_match_score(pb, psych_markers, phase), pb)
            for pb in rows
            if playbook_match_score(pb, psych_markers, phase) >= PLBOOK_MIN_MATCH_SCORE
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [pb for _score, pb in scored[: max(0, int(limit))]]
    finally:
        if own and db is not None:
            db.close()


def capture_conversion_for_user(
    db: Session,
    telegram_user_id: int | None,
    payment_lane: str,
    outcome: str = "unknown",
) -> ConversionPlaybook | None:
    """Load the converter's FE snapshot and persist a playbook (never raises)."""
    if telegram_user_id is None:
        return None
    from app.models.secretary_user_context import SecretaryUserContext

    ctx = (
        db.query(SecretaryUserContext)
        .filter(SecretaryUserContext.telegram_user_id == int(telegram_user_id))
        .one_or_none()
    )
    if not ctx or not ctx.interaction_format_json:
        return None
    return save_playbook_on_conversion(
        int(telegram_user_id),
        ctx.interaction_format_json,
        payment_lane,
        outcome,
        db=db,
    )


def build_playbook_suffix(playbooks: list[ConversionPlaybook], *, db: Session | None = None) -> str:
    """Format matched playbooks into a coaching string and bump times_matched."""
    if not playbooks:
        return ""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        sections = []
        for pb in playbooks:
            summary = (pb.format_summary or "an effective trajectory").strip()
            directive = (pb.behavioral_directive_at_conversion or "guide toward checkout").strip()
            sections.append(f"Similar converted clients showed: {summary}. Consider: {directive}.")
            pb.times_matched = (pb.times_matched or 0) + 1
        db.commit()
        return "\n".join(sections)
    finally:
        if own and db is not None:
            db.close()