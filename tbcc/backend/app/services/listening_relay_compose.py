"""Build listening-relay Telegram payloads (main + copy follow-ups)."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.listening_relay_ascii import (
    note_scrobble_for_ascii,
    pick_random_ascii,
    pick_tryptych_ascii_panels,
    split_ascii_into_panels,
)
from app.services.listening_relay_format import compose_listening_relay_messages, ensure_relay_pre_block
from app.services.listening_relay_send import RelayCopyFollowup
from app.services.listening_relay_slot import resolve_slot_extra
from app.services.listening_relay_templates import RelaySlotPick, consume_relay_slots, peek_relay_slots


@dataclass
class RelayOutbound:
    main_html: str
    copy_followups: list[RelayCopyFollowup]
    ascii_beat: bool = False
    tryptych: bool = False


def _followup_from_pick(row: ListeningRelaySettings, pick: RelaySlotPick, copy_html: str) -> RelayCopyFollowup:
    extra = resolve_slot_extra(row, pick.slot_idx, pick.n_templates)
    return RelayCopyFollowup.from_slot_extra(extra, copy_html)


def build_relay_outbound(
    row: ListeningRelaySettings,
    *,
    artist: str,
    title: str,
    album: str | None,
    url: str | None,
    source: str,
    source_label: str,
    consume: bool,
) -> RelayOutbound:
    ascii_beat = note_scrobble_for_ascii(row) if consume else False
    tryptych = bool(
        ascii_beat
        and bool(getattr(row, "tryptych_enabled", False))
        and bool(getattr(row, "tryptych_on_ascii_beat", True))
    )
    slot_count = 3 if tryptych else 1

    if consume:
        picks = consume_relay_slots(row, count=slot_count)
    else:
        picks = peek_relay_slots(row, count=slot_count)

    primary = picks[0]
    main_html, _ = compose_listening_relay_messages(
        artist=artist,
        title=title,
        album=album,
        url=url,
        source=source,
        source_label=source_label,
        template_html=primary.template_html,
        footer_html=primary.footer_html,
        copy_block_html="",
    )

    followups: list[RelayCopyFollowup] = []

    if tryptych:
        panels = pick_tryptych_ascii_panels(row)
        if not panels:
            art = pick_random_ascii(row)
            panels = split_ascii_into_panels(art, 3) if art else []
        for i in range(3):
            pick = picks[i] if i < len(picks) else primary
            copy_html = pick.copy_block_html
            if panels and i < len(panels):
                copy_html = panels[i]
            fu = _followup_from_pick(row, pick, copy_html)
            if fu.html or fu.media_ids or fu.attachment_urls:
                followups.append(fu)
    else:
        pick = primary
        copy_html = pick.copy_block_html
        if ascii_beat:
            art = pick_random_ascii(row)
            if art:
                copy_html = art
        fu = _followup_from_pick(row, pick, copy_html)
        if fu.html or fu.media_ids or fu.attachment_urls:
            followups.append(fu)

    return RelayOutbound(
        main_html=main_html,
        copy_followups=followups,
        ascii_beat=ascii_beat,
        tryptych=tryptych,
    )
