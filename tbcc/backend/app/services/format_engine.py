"""
Format Engine (FE-LLMv4) — adaptive emotional context for the secretary bot.

Observes tone and communication patterns over time, maintains a living interaction
format per user, and produces LLM context suffixes for emotionally calibrated replies.

Ethical guardrails (non-negotiable):
- Support and clarity only — no manipulation, false intimacy, or financial pressure.
- Distress → de-escalation and factual help; suggest human admin when appropriate.
- Never infer malicious intent; describe observable signals only.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.secretary_user_context import SecretaryMessageRecord, SecretaryUserContext
from app.services.secretary_settings_effective import get_effective_secretary_settings

logger = logging.getLogger(__name__)

FORMAT_VERSION = 4
PHASES = ("introduction", "engagement", "support", "recovery")

# Observable emotion signals — keyword/heuristic only; not diagnostic labels.
_EMOTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "distress": (
        "angry", "upset", "frustrated", "hate", "scam", "refund", "stolen",
        "worst", "terrible", "awful", "disappointed", "furious", "rip off",
        "ripoff", "never again", "report you",
    ),
    "confusion": (
        "confused", "don't understand", "dont understand", "how do i",
        "what is", "where is", "not working", "doesn't work", "doesnt work",
        "help me", "lost", "unclear",
    ),
    "positive": (
        "thanks", "thank you", "great", "awesome", "perfect", "helpful",
        "appreciate", "love it", "nice", "cool",
    ),
    "urgency": (
        "asap", "urgent", "immediately", "right now", "today", "deadline",
        "waiting", "still waiting", "no response",
    ),
    "disengagement": (
        "never mind", "nevermind", "forget it", "bye", "goodbye", "unsubscribe",
        "leave me alone", "stop",
    ),
}

_TONE_BY_DOMINANT: dict[str, str] = {
    "distress": "calm, empathetic, factual — acknowledge frustration without arguing; offer clear next steps",
    "confusion": "patient, step-by-step — one action at a time; confirm understanding",
    "positive": "warm, brief — match their energy without overselling",
    "urgency": "direct, prioritized — address the blocking issue first",
    "disengagement": "respectful, low-pressure — one concise helpful line; no follow-up pressure",
    "neutral": "clear, professional, concise",
}


def format_engine_enabled() -> bool:
    return bool(get_effective_secretary_settings().get("format_engine_enabled"))


def _message_retention_limit() -> int:
    raw = (os.getenv("TBCC_FORMAT_ENGINE_MESSAGE_RETENTION") or "80").strip()
    try:
        return max(10, min(500, int(raw)))
    except ValueError:
        return 80


def _history_for_llm_limit() -> int:
    raw = (os.getenv("TBCC_FORMAT_ENGINE_LLM_HISTORY") or "8").strip()
    try:
        return max(2, min(24, int(raw)))
    except ValueError:
        return 8


@dataclass
class EmotionAnalysis:
    dominant: str = "neutral"
    signals: dict[str, float] = field(default_factory=dict)
    triggers: list[str] = field(default_factory=list)
    distress_detected: bool = False
    disengagement_detected: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | None) -> EmotionAnalysis | None:
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            return cls(
                dominant=str(data.get("dominant") or "neutral"),
                signals={str(k): float(v) for k, v in (data.get("signals") or {}).items()},
                triggers=[str(x) for x in (data.get("triggers") or [])],
                distress_detected=bool(data.get("distress_detected")),
                disengagement_detected=bool(data.get("disengagement_detected")),
            )
        except Exception:
            return None


def analyze_message(text: str) -> EmotionAnalysis:
    """Lightweight observable signal extraction — no clinical claims."""
    lowered = (text or "").lower()
    signals: dict[str, float] = {}
    triggers: list[str] = []

    for emotion, keywords in _EMOTION_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits:
            signals[emotion] = min(1.0, hits * 0.35)
            triggers.extend(kw for kw in keywords if kw in lowered)

    dominant = "neutral"
    if signals:
        dominant = max(signals, key=lambda k: signals[k])

    return EmotionAnalysis(
        dominant=dominant,
        signals=signals,
        triggers=sorted(set(triggers))[:12],
        distress_detected=signals.get("distress", 0) >= 0.35,
        disengagement_detected=signals.get("disengagement", 0) >= 0.35,
    )


def _default_format() -> dict[str, Any]:
    return {
        "version": FORMAT_VERSION,
        "name": "support-adaptive",
        "phase": "introduction",
        "phase_history": [],
        "dominant_emotions": [],
        "observed_triggers": [],
        "communication_preferences": {
            "preferred_tone": "clear",
            "response_length": "medium",
            "distress_detected": False,
        },
        "interaction_guidelines": {
            "current_focus": "Welcome and orient the user to FAQ + payment bot",
            "tone_directive": _TONE_BY_DOMINANT["neutral"],
            "recovery_note": None,
            "escalation_hint": None,
        },
        "metrics": {
            "user_messages": 0,
            "assistant_messages": 0,
            "distress_events": 0,
            "positive_signals": 0,
        },
    }


def _load_format(raw: str | None) -> dict[str, Any]:
    if not raw:
        return _default_format()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return _default_format()
        base = _default_format()
        base.update({k: v for k, v in data.items() if k in base or k.startswith("observed")})
        if "communication_preferences" in data and isinstance(data["communication_preferences"], dict):
            base["communication_preferences"].update(data["communication_preferences"])
        if "interaction_guidelines" in data and isinstance(data["interaction_guidelines"], dict):
            base["interaction_guidelines"].update(data["interaction_guidelines"])
        if "metrics" in data and isinstance(data["metrics"], dict):
            base["metrics"].update(data["metrics"])
        return base
    except Exception:
        return _default_format()


def _save_format(fmt: dict[str, Any]) -> str:
    return json.dumps(fmt, ensure_ascii=False)


def _hours_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return (datetime.utcnow() - dt).total_seconds() / 3600.0


def _infer_phase(
    fmt: dict[str, Any],
    *,
    user_message_count: int,
    analysis: EmotionAnalysis,
    hours_since_last_user: float | None,
) -> str:
    current = str(fmt.get("phase") or "introduction")

    if analysis.distress_detected:
        return "support"
    if analysis.disengagement_detected and user_message_count > 2:
        return "recovery"
    if current == "support" and not analysis.distress_detected and analysis.dominant in ("neutral", "positive", "confusion"):
        return "engagement"
    if current == "recovery" and analysis.dominant not in ("disengagement",):
        return "engagement"
    if hours_since_last_user is not None and hours_since_last_user >= 48 and user_message_count > 1:
        return "recovery"
    if user_message_count <= 2:
        return "introduction"
    return "engagement"


def _update_format(
    fmt: dict[str, Any],
    *,
    analysis: EmotionAnalysis,
    user_text: str,
    new_phase: str,
) -> dict[str, Any]:
    metrics = fmt.setdefault("metrics", {})
    metrics["user_messages"] = int(metrics.get("user_messages") or 0) + 1
    if analysis.distress_detected:
        metrics["distress_events"] = int(metrics.get("distress_events") or 0) + 1
    if analysis.dominant == "positive":
        metrics["positive_signals"] = int(metrics.get("positive_signals") or 0) + 1

    prev_phase = str(fmt.get("phase") or "introduction")
    if new_phase != prev_phase:
        history = fmt.setdefault("phase_history", [])
        history.append({"from": prev_phase, "to": new_phase, "at": datetime.utcnow().isoformat()})
        fmt["phase_history"] = history[-20:]
        fmt["phase"] = new_phase

    emotions = fmt.setdefault("dominant_emotions", [])
    if analysis.dominant != "neutral":
        emotions.append(analysis.dominant)
    fmt["dominant_emotions"] = emotions[-12:]

    triggers = fmt.setdefault("observed_triggers", [])
    for t in analysis.triggers[:4]:
        if t not in triggers:
            triggers.append(t)
    fmt["observed_triggers"] = triggers[-16:]

    prefs = fmt.setdefault("communication_preferences", {})
    prefs["preferred_tone"] = analysis.dominant if analysis.dominant != "neutral" else prefs.get("preferred_tone", "clear")
    prefs["distress_detected"] = analysis.distress_detected
    if analysis.dominant == "urgency":
        prefs["response_length"] = "short"
    elif analysis.dominant == "confusion":
        prefs["response_length"] = "medium"

    guidelines = fmt.setdefault("interaction_guidelines", {})
    guidelines["tone_directive"] = _TONE_BY_DOMINANT.get(analysis.dominant, _TONE_BY_DOMINANT["neutral"])

    focus = _derive_focus(new_phase, analysis, user_text)
    guidelines["current_focus"] = focus

    if new_phase == "support":
        guidelines["escalation_hint"] = (
            "User may need human admin. Offer to escalate if the issue is account-specific "
            "or cannot be resolved with public FAQ info."
        )
    else:
        guidelines["escalation_hint"] = None

    if new_phase == "recovery":
        guidelines["recovery_note"] = (
            "User returned after tension or silence. Acknowledge briefly; do not guilt or pressure."
        )
    else:
        guidelines["recovery_note"] = None

    return fmt


def _derive_focus(phase: str, analysis: EmotionAnalysis, user_text: str) -> str:
    snippet = re.sub(r"\s+", " ", (user_text or "").strip())[:120]
    if phase == "introduction":
        return "Orient user: what this bot does, where checkout lives"
    if phase == "support":
        return f"De-escalate and resolve: {snippet or 'address stated concern'}"
    if phase == "recovery":
        return "Re-open support gently after prior friction or gap"
    if analysis.dominant == "confusion":
        return f"Clarify step-by-step: {snippet or 'user question'}"
    if analysis.dominant == "positive":
        return "Confirm helpful outcome; point to payment bot if relevant"
    return f"Answer FAQ: {snippet or 'latest question'}"


def _emotional_summary(fmt: dict[str, Any], analysis: EmotionAnalysis) -> str:
    phase = fmt.get("phase", "introduction")
    emotions = fmt.get("dominant_emotions") or []
    recent = emotions[-3:] if emotions else [analysis.dominant]
    return f"phase={phase}; recent_signals={','.join(recent)}; dominant_now={analysis.dominant}"


def get_or_create_context(db: Session, telegram_user_id: int, *, username: str | None = None) -> SecretaryUserContext:
    row = db.query(SecretaryUserContext).filter(SecretaryUserContext.telegram_user_id == telegram_user_id).one_or_none()
    if row:
        if username and row.telegram_username != username:
            row.telegram_username = username
        return row
    row = SecretaryUserContext(
        telegram_user_id=telegram_user_id,
        telegram_username=username,
        current_phase="introduction",
        interaction_format_json=_save_format(_default_format()),
    )
    db.add(row)
    db.flush()
    return row


def _prune_old_messages(db: Session, context_id: int) -> None:
    limit = _message_retention_limit()
    ids = (
        db.query(SecretaryMessageRecord.id)
        .filter(SecretaryMessageRecord.context_id == context_id)
        .order_by(SecretaryMessageRecord.created_at.desc())
        .offset(limit)
        .all()
    )
    if not ids:
        return
    drop_ids = [i[0] for i in ids]
    db.query(SecretaryMessageRecord).filter(SecretaryMessageRecord.id.in_(drop_ids)).delete(synchronize_session=False)


def preview_user_turn(telegram_user_id: int, user_text: str) -> str:
    """Build Format Engine suffix without persisting (admin test playground)."""
    if not format_engine_enabled():
        return ""
    db = SessionLocal()
    try:
        ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.telegram_user_id == telegram_user_id).one_or_none()
        analysis = analyze_message(user_text)
        if not ctx:
            fmt = _default_format()
            return build_context_suffix(
                SecretaryUserContext(telegram_user_id=telegram_user_id, current_phase="introduction"),
                analysis,
                fmt,
            )
        fmt = _load_format(ctx.interaction_format_json)
        return build_context_suffix(ctx, analysis, fmt)
    except Exception as e:
        logger.warning("format_engine preview failed uid=%s: %s", telegram_user_id, e)
        return ""
    finally:
        db.close()


def prepare_user_turn(
    telegram_user_id: int,
    user_text: str,
    *,
    username: str | None = None,
) -> tuple[str, int | None, bool]:
    """
    Record inbound user message, evolve format.

    Returns (LLM context suffix, context_id, is_new_lead).
    is_new_lead is True when this is the customer's first recorded user message.
    Returns ("", None, False) when disabled or on DB error.
    """
    if not format_engine_enabled():
        return "", None, False

    db = SessionLocal()
    try:
        ctx = get_or_create_context(db, telegram_user_id, username=username)
        analysis = analyze_message(user_text)
        fmt = _load_format(ctx.interaction_format_json)
        hours_gap = _hours_since(ctx.last_user_at)
        user_count = int((fmt.get("metrics") or {}).get("user_messages") or 0) + 1
        prev_phase = str(fmt.get("phase") or "introduction")
        new_phase = _infer_phase(fmt, user_message_count=user_count, analysis=analysis, hours_since_last_user=hours_gap)
        is_new_lead = int(ctx.message_count or 0) == 0

        if prev_phase != new_phase:
            from app.services.format_engine_llm import refine_emotion_on_phase_change

            analysis, llm_notes = refine_emotion_on_phase_change(
                user_text=user_text,
                heuristic=analysis,
                prev_phase=prev_phase,
                new_phase=new_phase,
                format_snapshot=fmt,
            )
            if llm_notes:
                fmt.setdefault("llm_refinements", []).append(llm_notes)
                fmt["llm_refinements"] = fmt["llm_refinements"][-10:]
                guidelines = fmt.setdefault("interaction_guidelines", {})
                if llm_notes.get("tone_directive"):
                    guidelines["tone_directive"] = llm_notes["tone_directive"]
                if llm_notes.get("current_focus"):
                    guidelines["current_focus"] = llm_notes["current_focus"]

        fmt = _update_format(fmt, analysis=analysis, user_text=user_text, new_phase=new_phase)

        ctx.current_phase = new_phase
        ctx.interaction_format_json = _save_format(fmt)
        ctx.emotional_summary = _emotional_summary(fmt, analysis)
        ctx.message_count = (ctx.message_count or 0) + 1
        ctx.last_user_at = datetime.utcnow()
        ctx.updated_at = datetime.utcnow()

        db.add(
            SecretaryMessageRecord(
                context_id=ctx.id,
                role="user",
                content=user_text[:8000],
                emotion_json=analysis.to_json(),
            )
        )
        db.commit()

        suffix = build_context_suffix(ctx, analysis, fmt)
        return suffix, ctx.id, is_new_lead
    except Exception as e:
        db.rollback()
        logger.warning("format_engine prepare_user_turn failed uid=%s: %s", telegram_user_id, e)
        return "", None, False
    finally:
        db.close()


def finalize_assistant_turn(context_id: int | None, assistant_text: str) -> None:
    """Persist bot reply and update format metrics."""
    if not format_engine_enabled() or context_id is None:
        return

    db = SessionLocal()
    try:
        ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == context_id).one_or_none()
        if not ctx:
            return
        _persist_assistant(db, ctx, assistant_text)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("format_engine finalize_assistant_turn failed ctx=%s: %s", context_id, e)
    finally:
        db.close()


def finalize_assistant_turn_for_user(telegram_user_id: int, assistant_text: str) -> None:
    """Same as finalize_assistant_turn but keyed by Telegram user (draft approve path)."""
    if not format_engine_enabled():
        return

    db = SessionLocal()
    try:
        ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.telegram_user_id == telegram_user_id).one_or_none()
        if not ctx:
            return
        _persist_assistant(db, ctx, assistant_text)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("format_engine finalize_for_user failed uid=%s: %s", telegram_user_id, e)
    finally:
        db.close()


def _persist_assistant(db: Session, ctx: SecretaryUserContext, assistant_text: str) -> None:
    fmt = _load_format(ctx.interaction_format_json)
    metrics = fmt.setdefault("metrics", {})
    metrics["assistant_messages"] = int(metrics.get("assistant_messages") or 0) + 1
    ctx.interaction_format_json = _save_format(fmt)
    ctx.last_assistant_at = datetime.utcnow()
    ctx.updated_at = datetime.utcnow()

    db.add(
        SecretaryMessageRecord(
            context_id=ctx.id,
            role="assistant",
            content=assistant_text[:8000],
            emotion_json=None,
        )
    )
    _prune_old_messages(db, ctx.id)


def load_recent_messages_for_llm(telegram_user_id: int) -> list[dict[str, str]]:
    """DB-backed history for LLM when in-memory context is empty or after restart."""
    if not format_engine_enabled():
        return []

    db = SessionLocal()
    try:
        ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.telegram_user_id == telegram_user_id).one_or_none()
        if not ctx:
            return []
        limit = _history_for_llm_limit()
        rows = (
            db.query(SecretaryMessageRecord)
            .filter(SecretaryMessageRecord.context_id == ctx.id)
            .order_by(SecretaryMessageRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        out: list[dict[str, str]] = []
        for row in reversed(rows):
            role = row.role if row.role in ("user", "assistant") else "user"
            out.append({"role": role, "content": row.content})
        return out
    except Exception as e:
        logger.warning("format_engine load_recent_messages failed uid=%s: %s", telegram_user_id, e)
        return []
    finally:
        db.close()


def build_context_suffix(
    ctx: SecretaryUserContext,
    analysis: EmotionAnalysis,
    fmt: dict[str, Any] | None = None,
    *,
    verbosity: str | None = None,
) -> str:
    """Human-readable block appended to the secretary system prompt."""
    fmt = fmt or _load_format(ctx.interaction_format_json)
    guidelines = fmt.get("interaction_guidelines") or {}
    prefs = fmt.get("communication_preferences") or {}
    metrics = fmt.get("metrics") or {}

    if verbosity is None:
        verbosity = str(get_effective_secretary_settings().get("fe_verbosity") or "compact")

    phase = fmt.get("phase", ctx.current_phase)
    tone = guidelines.get("tone_directive", "clear and helpful")
    focus = guidelines.get("current_focus", "Answer the FAQ")

    if verbosity == "compact":
        bits = [f"phase={phase}", f"signal={analysis.dominant}", f"tone={tone[:100]}"]
        if focus and focus != "Answer the FAQ":
            bits.append(f"focus={focus[:80]}")
        if analysis.triggers:
            bits.append(f"triggers={', '.join(analysis.triggers[:3])}")
        if guidelines.get("escalation_hint"):
            bits.append("escalate=human admin if needed")
        return "FE context: " + "; ".join(bits) + ". Support only — no manipulation."

    lines = [
        "--- Format Engine (FE-LLMv4) context ---",
        "Use this as observational context only. Do not manipulate, guilt, or create false intimacy.",
        f"Interaction phase: {phase}",
        f"Dominant signal (this message): {analysis.dominant}",
        f"Tone directive: {tone}",
        f"Current focus: {focus}",
        f"Preferred response length: {prefs.get('response_length', 'medium')}",
    ]

    if analysis.triggers:
        lines.append(f"Observed trigger phrases: {', '.join(analysis.triggers[:6])}")

    if guidelines.get("recovery_note"):
        lines.append(f"Recovery: {guidelines['recovery_note']}")

    if guidelines.get("escalation_hint"):
        lines.append(f"Escalation: {guidelines['escalation_hint']}")

    if metrics.get("user_messages"):
        lines.append(f"Prior user turns in this thread: {metrics.get('user_messages')}")

    gap = _hours_since(ctx.last_user_at)
    if gap is not None and gap >= 24:
        lines.append(f"User returned after ~{int(gap)}h since last message — acknowledge naturally if relevant.")

    lines.append("Ask implicitly: What emotion seems dominant? What would genuinely help right now?")
    lines.append("--- end Format Engine context ---")
    return "\n".join(lines)


def context_to_dict(ctx: SecretaryUserContext) -> dict[str, Any]:
    fmt = _load_format(ctx.interaction_format_json)
    return {
        "id": ctx.id,
        "telegram_user_id": ctx.telegram_user_id,
        "telegram_username": ctx.telegram_username,
        "current_phase": ctx.current_phase,
        "emotional_summary": ctx.emotional_summary,
        "message_count": ctx.message_count,
        "last_user_at": ctx.last_user_at.isoformat() if ctx.last_user_at else None,
        "last_assistant_at": ctx.last_assistant_at.isoformat() if ctx.last_assistant_at else None,
        "created_at": ctx.created_at.isoformat() if ctx.created_at else None,
        "updated_at": ctx.updated_at.isoformat() if ctx.updated_at else None,
        "interaction_format": fmt,
    }


def get_user_context_public_summary(telegram_user_id: int) -> dict[str, Any] | None:
    """Lightweight summary for /mystatus in Telegram (no private admin fields)."""
    if not format_engine_enabled():
        return None
    db = SessionLocal()
    try:
        ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.telegram_user_id == telegram_user_id).one_or_none()
        if not ctx:
            return None
        fmt = _load_format(ctx.interaction_format_json)
        return {
            "phase": ctx.current_phase or fmt.get("phase"),
            "message_count": ctx.message_count or 0,
            "emotional_summary": ctx.emotional_summary,
            "last_user_at": ctx.last_user_at.isoformat() if ctx.last_user_at else None,
        }
    finally:
        db.close()


def reset_user_context(db: Session, context_id: int) -> bool:
    ctx = db.query(SecretaryUserContext).filter(SecretaryUserContext.id == context_id).one_or_none()
    if not ctx:
        return False
    db.query(SecretaryMessageRecord).filter(SecretaryMessageRecord.context_id == context_id).delete(
        synchronize_session=False
    )
    ctx.current_phase = "introduction"
    ctx.interaction_format_json = _save_format(_default_format())
    ctx.emotional_summary = None
    ctx.message_count = 0
    ctx.last_user_at = None
    ctx.last_assistant_at = None
    ctx.updated_at = datetime.utcnow()
    return True
