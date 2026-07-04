"""Optional LLM refinement of emotion analysis on Format Engine phase transitions."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import httpx

from app.services.format_engine import EmotionAnalysis, PHASES
from app.services.secretary_settings_effective import get_effective_secretary_settings

logger = logging.getLogger(__name__)


def llm_refine_enabled(db=None) -> bool:
    eff = get_effective_secretary_settings(db)
    return bool(eff.get("llm_refine_on_phase_change"))


def _model() -> str:
    from app.services.llm_completions import resolve_text_model

    explicit = (os.getenv("TBCC_SECRETARY_LLM_MODEL") or "").strip()
    return resolve_text_model(explicit or None)


def refine_emotion_on_phase_change(
    *,
    user_text: str,
    heuristic: EmotionAnalysis,
    prev_phase: str,
    new_phase: str,
    format_snapshot: dict[str, Any],
) -> tuple[EmotionAnalysis, dict[str, Any] | None]:
    """
    When phase changes, ask the LLM to refine observable signals and tone guidance.
    Returns (possibly updated analysis, optional llm_notes dict for format JSON).
    """
    if prev_phase == new_phase or new_phase not in PHASES:
        return heuristic, None
    from app.services.llm_completions import post_chat_completions_sync
    from app.services.secretary_llm_config import resolve_secretary_text_llm_runtime, secretary_llm_configured

    runtime = resolve_secretary_text_llm_runtime()
    if not llm_refine_enabled() or not secretary_llm_configured():
        return heuristic, None

    system = (
        "You refine customer-support emotion signals for a FAQ bot. "
        "Output ONLY valid JSON with keys: dominant (one of distress, confusion, positive, urgency, "
        "disengagement, neutral), distress_detected (bool), disengagement_detected (bool), "
        "tone_directive (one sentence), current_focus (one sentence), llm_note (optional short string). "
        "Describe observable signals only. No manipulation, clinical diagnosis, or inferred bad intent."
    )
    user = json.dumps(
        {
            "user_message": user_text[:1500],
            "heuristic_dominant": heuristic.dominant,
            "heuristic_signals": heuristic.signals,
            "phase_transition": {"from": prev_phase, "to": new_phase},
            "recent_emotions": (format_snapshot.get("dominant_emotions") or [])[-5:],
        },
        ensure_ascii=False,
    )

    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 280,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        from app.services.llm_completions import post_chat_completions_sync

        data = post_chat_completions_sync(payload, timeout=45.0, runtime=runtime)
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return heuristic, None

        dominant = str(parsed.get("dominant") or heuristic.dominant)
        if dominant not in (*_EMOTION_SET(), "neutral"):
            dominant = heuristic.dominant

        refined = EmotionAnalysis(
            dominant=dominant,
            signals=dict(heuristic.signals),
            triggers=list(heuristic.triggers),
            distress_detected=bool(parsed.get("distress_detected", heuristic.distress_detected)),
            disengagement_detected=bool(parsed.get("disengagement_detected", heuristic.disengagement_detected)),
        )
        notes = {
            "tone_directive": str(parsed.get("tone_directive") or "").strip() or None,
            "current_focus": str(parsed.get("current_focus") or "").strip() or None,
            "llm_note": str(parsed.get("llm_note") or "").strip() or None,
            "refined_at": datetime.utcnow().isoformat(),
            "phase_transition": {"from": prev_phase, "to": new_phase},
        }
        return refined, notes
    except Exception as e:
        logger.warning("format_engine LLM refine failed: %s", e)
        return heuristic, None


def _EMOTION_SET():
    return ("distress", "confusion", "positive", "urgency", "disengagement")
