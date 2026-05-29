"""Rotate listening-relay message templates (same idea as scheduled post caption_variations)."""



from __future__ import annotations



import json

import random

from dataclasses import dataclass

from typing import TYPE_CHECKING



if TYPE_CHECKING:

    from app.models.listening_relay_settings import ListeningRelaySettings





@dataclass

class RelaySlotPick:

    slot_idx: int

    n_templates: int

    template_html: str | None

    footer_html: str

    copy_block_html: str





def get_template_variations_list(row: ListeningRelaySettings) -> list[str]:

    raw_json = getattr(row, "message_template_variations", None)

    if raw_json:

        try:

            arr = json.loads(raw_json)

            if isinstance(arr, list) and len(arr) > 0:

                return [str(x).strip() if x is not None else "" for x in arr]

        except (json.JSONDecodeError, TypeError):

            pass

    single = (row.message_template_html or "").strip()

    return [single] if single else []





def _footer_slots_raw(row: ListeningRelaySettings) -> list[str]:

    raw_json = getattr(row, "message_footer_variations", None)

    if raw_json:

        try:

            arr = json.loads(raw_json)

            if isinstance(arr, list) and len(arr) > 0:

                return [str(x) if x is not None else "" for x in arr]

        except (json.JSONDecodeError, TypeError):

            pass

    single = (getattr(row, "message_footer_html", None) or "").strip()

    return [single] if single else []





def _copy_block_slots_raw(row: ListeningRelaySettings) -> list[str]:

    raw_json = getattr(row, "message_copy_block_variations", None)

    if raw_json:

        try:

            arr = json.loads(raw_json)

            if isinstance(arr, list) and len(arr) > 0:

                return [str(x) if x is not None else "" for x in arr]

        except (json.JSONDecodeError, TypeError):

            pass

    return []





def _slot_parallel_text(slots: list[str], slot_idx: int, n_templates: int) -> str:

    if not slots:

        return ""

    nt = max(1, n_templates)

    if len(slots) == 1:

        return slots[0].strip()

    padded = list(slots)

    while len(padded) < nt:

        padded.append("")

    if slot_idx < 0 or slot_idx >= len(padded):

        return ""

    return padded[slot_idx].strip()





def resolve_footer_for_template_slot(row: ListeningRelaySettings, slot_idx: int, n_templates: int) -> str:

    """Footer for rotation slot slot_idx (0..n-1). Single stored footer repeats for every slot."""

    return _slot_parallel_text(_footer_slots_raw(row), slot_idx, n_templates)





def resolve_copy_block_for_template_slot(row: ListeningRelaySettings, slot_idx: int, n_templates: int) -> str:

    """Tap-to-copy block for rotation slot (sent as follow-up under Last.fm preview)."""

    return _slot_parallel_text(_copy_block_slots_raw(row), slot_idx, n_templates)





def _rotation_mode(row: ListeningRelaySettings) -> str:

    mode = str(getattr(row, "template_rotation_mode", None) or "sequential").strip().lower()

    return mode if mode in ("sequential", "random") else "sequential"





def _slot_pick_indices(row: ListeningRelaySettings, n: int, count: int, *, advance: bool) -> list[int]:

    if n <= 0:

        return [0] * count

    mode = _rotation_mode(row)

    if mode == "random":

        indices = [random.randrange(n) for _ in range(count)]

        if advance and n >= 2:

            row.message_template_rotation_index = (

                (row.message_template_rotation_index or 0) + count

            ) % n

        return indices

    start = (row.message_template_rotation_index or 0) % n

    indices = [(start + i) % n for i in range(count)]

    if advance and n >= 2:

        row.message_template_rotation_index = (start + count) % n

    elif advance and n == 1:

        row.message_template_rotation_index = 0

    return indices





def _pick_at(row: ListeningRelaySettings, slot_idx: int) -> RelaySlotPick:

    vars_ = get_template_variations_list(row)

    n = len(vars_)

    nt = n if n else 1

    if n >= 2:

        tpl = vars_[slot_idx % n]

    elif n == 1:

        tpl = vars_[0]

        slot_idx = 0

    else:

        tpl = None

        slot_idx = 0

    return RelaySlotPick(

        slot_idx=slot_idx,

        n_templates=nt,

        template_html=tpl,

        footer_html=resolve_footer_for_template_slot(row, slot_idx, nt),

        copy_block_html=resolve_copy_block_for_template_slot(row, slot_idx, nt),

    )





def peek_relay_slots(row: ListeningRelaySettings, count: int = 1) -> list[RelaySlotPick]:

    vars_ = get_template_variations_list(row)

    n = len(vars_)

    indices = _slot_pick_indices(row, n, count, advance=False)

    return [_pick_at(row, i) for i in indices]





def consume_relay_slots(row: ListeningRelaySettings, count: int = 1) -> list[RelaySlotPick]:

    vars_ = get_template_variations_list(row)

    n = len(vars_)

    indices = _slot_pick_indices(row, n, count, advance=True)

    return [_pick_at(row, i) for i in indices]





def peek_relay_template_and_footer(row: ListeningRelaySettings) -> tuple[str | None, str, str]:

    """Preview next send; does not advance rotation."""

    p = peek_relay_slots(row, 1)[0]

    return p.template_html, p.footer_html, p.copy_block_html





def consume_relay_template_and_footer(row: ListeningRelaySettings) -> tuple[str | None, str, str]:

    """Template + footer + copy block for an actual send; advances rotation when 2+ templates."""

    p = consume_relay_slots(row, 1)[0]

    return p.template_html, p.footer_html, p.copy_block_html





def get_footer_variations_for_api(row: ListeningRelaySettings) -> list[str]:

    """One entry per template variation for the dashboard (repeat single footer for all slots)."""

    vars_ = get_template_variations_list(row)

    n = len(vars_)

    if n == 0:

        return []

    slots = _footer_slots_raw(row)

    if not slots:

        return [""] * n

    if len(slots) == 1:

        return [slots[0]] * n

    padded = list(slots)

    while len(padded) < n:

        padded.append("")

    return padded[:n]





def get_copy_block_variations_for_api(row: ListeningRelaySettings) -> list[str]:

    """One entry per template variation for the dashboard (repeat single block for all slots)."""

    vars_ = get_template_variations_list(row)

    n = len(vars_)

    if n == 0:

        return []

    slots = _copy_block_slots_raw(row)

    if not slots:

        return [""] * n

    if len(slots) == 1:

        return [slots[0]] * n

    padded = list(slots)

    while len(padded) < n:

        padded.append("")

    return padded[:n]





def peek_template_html(row: ListeningRelaySettings) -> str | None:

    """Next template only — prefer peek_relay_template_and_footer when footer matters."""

    tpl, _, _ = peek_relay_template_and_footer(row)

    return tpl

