"""strftime-inspired template expansion for social copy (before fill_armory_template)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_DATE_RE = re.compile(r"\{date:([^}]+)\}")
_WEEKDAY_RE = re.compile(r"\{weekday\}")
_LANE_RE = re.compile(r"\{lane:([a-z0-9_]+)\}")
_PROMPT_LV_RE = re.compile(r"\{prompt_lv:([a-z0-9_]+)\}")
_PROMPT_TEASER_RE = re.compile(r"\{prompt_teaser:([a-z0-9_]+)\}")


def expand_template_tokens(text: str, *, db: "Session | None" = None, for_x: bool = False) -> str:
    """Expand dynamic tokens in template body."""
    out = text or ""

    def _date_sub(m: re.Match[str]) -> str:
        fmt = m.group(1).strip()
        try:
            return datetime.now().strftime(fmt)
        except ValueError:
            return datetime.now().strftime("%Y%m%d")

    out = _DATE_RE.sub(_date_sub, out)
    out = _WEEKDAY_RE.sub(datetime.now().strftime("%A"), out)

    def _lane_sub(m: re.Match[str]) -> str:
        lane = m.group(1).strip().lower()
        try:
            from app.data.aof_manual_gate_links import manual_gate_url

            url = manual_gate_url(lane)
            if url:
                return url
        except Exception:
            pass
        from app.services.aof_social_links import aof_hub_invite_url

        return aof_hub_invite_url()

    out = _LANE_RE.sub(_lane_sub, out)

    def _prompt_lv_sub(m: re.Match[str]) -> str:
        key = m.group(1).strip().lower()
        if db is None:
            return f"prompt:{key}"
        from app.services.prompt_gate_lookup import prompt_gate_url

        url = prompt_gate_url(key, db=db)
        return url or f"prompt:{key}"

    def _prompt_teaser_sub(m: re.Match[str]) -> str:
        key = m.group(1).strip().lower()
        if for_x:
            return f"prompt pack → @aofmainhub ({key})"
        return _prompt_lv_sub(m)

    out = _PROMPT_LV_RE.sub(_prompt_lv_sub, out)
    out = _PROMPT_TEASER_RE.sub(_prompt_teaser_sub, out)
    return out


def expand_and_fill(
    text: str,
    *,
    db: "Session | None" = None,
    for_x: bool = False,
    **fill_kwargs: Any,
) -> str:
    from app.services.aof_social_links import fill_armory_template

    expanded = expand_template_tokens(text, db=db, for_x=for_x)
    return fill_armory_template(expanded, db=db, for_x=for_x, **fill_kwargs)
