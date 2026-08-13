"""Telegram HTML voice for secretary operator reports (inbox, pulse, heuristic briefs).

Telegram HTML only: <b> <i> <u> <code> <pre> <blockquote> <a> — no Markdown.
"""

from __future__ import annotations

import html
import re
from typing import Any

# Longest placement suffix first so "links_hub_sfw" wins over "links_hub".
_PLACEMENT_SUFFIXES: list[tuple[str, str]] = [
    ("telegram_footer", "TG caption footer"),
    ("links_hub_sfw", "@thecheckoutlist"),
    ("links_hub_ai", "link hub · AI row"),
    ("links_hub", "@aofmainhub link hub"),
    ("x_buffer", "Buffer X"),
    ("loot_roll", "Loot God roll"),
    ("manual_only", "dashboard insert"),
]

_BRAND_ALIASES: list[tuple[str, str]] = [
    ("undress_ai_bot", "Undress AI"),
    ("undress_ai", "Undress AI"),
    ("loot_goblin_channel_fomo", "Loot Goblin FOMO"),
    ("loot_goblin_channel_fomc", "Loot Goblin FOMO"),
    ("loot_goblin", "Loot Goblin"),
    ("cloud_farm_wallet", "Cloud Farm Wallet"),
    ("aof_spicy_companion", "Spicy Companion"),
    ("honeypot", "Honeypot"),
    ("t_me", "t.me"),
    ("drawai", "DrawAI"),
    ("bangbros", "BangBros"),
]

_PULSE_KIND: dict[str, str] = {
    "post_ok": "scheduler posts landed",
    "post_fail": "scheduler posts failed",
    "affiliate_served": "sponsor links rotated into captions",
    "beacon": "tracked link clicks",
    "start": "bot /start arrivals",
    "loot_roll": "loot rolls delivered",
}

_HORIZON_HUMAN = {"ST": "now", "OPS": "this week", "LT": "this quarter", "now": "now", "week": "this week", "quarter": "this quarter"}

_BLOCKER_PLAYBOOK: dict[str, str] = {
    "revenue_stall": (
        "Fire a Loot Room CTA plus the $10 VIP intro on the next scheduler tick. "
        "Packs still need a first charge — that unlocks the scoreboard."
    ),
    "companion_zero": (
        "On loot exhaustion, send the companion deep link. Zero photos sold means the "
        "undress trial is burning cost with no upsell."
    ),
    "attribution_blind": (
        "Wrap every CTA in a /r/ beacon with ?start= so the next Stars payment can join "
        "to a source. Until then we cannot scale winners."
    ),
    "post_failures": (
        "Open /stack and unstick the failing scheduler. FOMO and checkout never reach "
        "the room while posts die."
    ),
    "import_failures": (
        "Clear the import error on the lane that's failing — empty pools starve rolls "
        "and auto-post."
    ),
    "gate_no_touches": (
        "Click one live gate yourself. If it 302s but no /start lands, the bot payload "
        "is wrong — fix ?start= before buying more traffic."
    ),
    "pool_thin": (
        "Run the loot refill on thin lanes (ass / big_tits / goon / full_length) so "
        "the next /roll is not empty."
    ),
}


def esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def code(s: Any) -> str:
    return f"<code>{esc(s)}</code>"


def quote(inner: str) -> str:
    return f"<blockquote>{inner}</blockquote>"


def humanize_source_ref(ref: str | None) -> dict[str, str]:
    """Turn src_aff_undress_ai_bot_telegram_footer into a human label + surface."""
    raw = (ref or "").strip()
    if not raw:
        return {"label": "unknown source", "surface": "", "display": "unknown source", "raw": ""}
    key = raw.lower()
    if key.startswith("src_"):
        key = key[4:]
    surface = ""
    for suffix, human in _PLACEMENT_SUFFIXES:
        token = f"_{suffix}"
        if key.endswith(token):
            surface = human
            key = key[: -len(token)]
            break
    if key.startswith("aff_"):
        key = key[4:]
    label = ""
    for alias, brand in _BRAND_ALIASES:
        if key == alias or key.startswith(alias + "_") or key.endswith("_" + alias):
            label = brand
            rest = key.replace(alias, "", 1).strip("_")
            if rest and rest not in alias:
                extra = rest.replace("_", " ").strip()
                if extra and extra.lower() not in brand.lower():
                    label = f"{brand} · {extra}"
            break
    if not label:
        if key.startswith("lv_"):
            parts = key[3:].replace("_", " ")
            label = f"Linkvertise · {parts}"
        elif key.startswith("web_"):
            label = f"Web hub · {key[4:].replace('_', ' ')}"
        elif key.startswith("bait_"):
            label = f"Bait · {key[5:].replace('_', ' ')}"
        elif key.startswith("loot_"):
            label = f"Loot · {key[5:].replace('_', ' ')}"
        else:
            label = key.replace("_", " ").strip() or raw
            label = re.sub(r"\s+", " ", label).title()
    display = f"{label} · {surface}" if surface else label
    return {"label": label, "surface": surface, "display": display, "raw": raw}


def humanize_pulse_kind(kind: str | None) -> str:
    key = (kind or "").strip().lower()
    return _PULSE_KIND.get(key, key.replace("_", " ") or "traffic")


def _count_map(counts: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, v in (counts or {}).items():
        try:
            out[str(k)] = int(v or 0)
        except (TypeError, ValueError):
            continue
    return out


def pulse_read(counts: dict[str, Any], refs: list[dict[str, Any]] | None = None) -> str:
    """One charitable paragraph from the real numbers."""
    c = _count_map(counts)
    served = c.get("affiliate_served", 0)
    beacons = c.get("beacon", 0)
    posts = c.get("post_ok", 0)
    fails = c.get("post_fail", 0)
    starts = c.get("start", 0)
    rolls = c.get("loot_roll", 0)
    top = ""
    if refs:
        top = str((refs[0] or {}).get("display") or (refs[0] or {}).get("label") or "")

    if fails and fails >= max(posts, 1):
        return (
            f"{fails} scheduler send(s) failed this window. "
            f"FOMO and checkout CTAs never reached the room — that is a <u>revenue outage</u>, not noise."
        )
    if served and beacons == 0:
        return (
            f"{served} sponsor slot(s) went into captions, and this window recorded "
            f"<u>zero tracked clicks</u>. The network is talking; nobody is tapping. "
            f"That is a conversion hole, not a posting hole."
        )
    if posts and starts == 0 and beacons == 0:
        return (
            f"{posts} post(s) landed, but nobody entered a bot from them. "
            f"The caption is shipping; the <u>deep link</u> is not doing work yet."
        )
    if starts and rolls == 0 and beacons == 0:
        return (
            f"{starts} person(s) opened a bot. They already raised their hand — "
            f"the next message should sell <u>/loot</u> or VIP, not another FAQ."
        )
    if beacons and served:
        extra = f" Loudest source: <b>{esc(top)}</b>." if top else ""
        return (
            f"{beacons} tracked click(s) on {served} sponsor rotation(s). "
            f"Something is converting — double the winner this cycle.{extra}"
        )
    if posts:
        return (
            f"{posts} post(s) made it to Telegram. Quiet on clicks is fine for a short window — "
            f"keep loot/VIP on the next tick so idle time still earns."
        )
    return "Quiet window. Keep checkout live; idle ops cost still runs whether we post or not."


def pulse_playbook(counts: dict[str, Any], refs: list[dict[str, Any]] | None = None) -> list[str]:
    c = _count_map(counts)
    served = c.get("affiliate_served", 0)
    beacons = c.get("beacon", 0)
    posts = c.get("post_ok", 0)
    fails = c.get("post_fail", 0)
    starts = c.get("start", 0)
    rolls = c.get("loot_roll", 0)
    actions: list[str] = []
    if fails:
        actions.append(
            f"Unstick the scheduler — {fails} failed send(s) means FOMO never hit the channel. "
            f"Open {code('/stack')} then {code('/inbox ops')}."
        )
    if served and beacons == 0:
        actions.append(
            "Tap one caption footer yourself. If it does not 302 through a "
            f"{code('/r/')} slug, the beacon is dead and we cannot attribute a dollar."
        )
    if posts and starts == 0 and beacons == 0:
        actions.append(
            "Check the CTA is a bot deep link with "
            f"{code('?start=')} — a bare t.me invite will not show up here as a start."
        )
    if starts and rolls == 0:
        actions.append(
            f"{starts} arrival(s) with no loot roll. Next secretary/payment reply should push "
            f"{code('/loot')} or the $10 VIP intro."
        )
    if beacons:
        actions.append(
            "Clicks are landing — raise the winning sponsor's rotation weight this cycle and park cold slots."
        )
    if refs:
        top = refs[0]
        disp = esc(top.get("display") or top.get("label") or "top source")
        actions.append(
            f"<b>{disp}</b> is loudest this window. Leave it in rotation; do not shuffle it out for a cold sponsor."
        )
    if not actions:
        actions.append(
            f"Quiet is not broken. Keep loot/VIP on the next scheduler tick — {code('/sponsors')} if a slot looks stale."
        )
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for a in actions:
        if a in seen:
            continue
        seen.add(a)
        out.append(a)
        if len(out) >= 3:
            break
    return out


def format_pulse_digest_html(
    counts: dict[str, Any],
    refs: dict[str, Any] | list[tuple[Any, Any]] | None = None,
) -> str | None:
    """Beat digest DM — human counts, charitable read, do-this-now."""
    c = _count_map(counts)
    if not c or sum(c.values()) <= 0:
        return None

    ref_pairs: list[tuple[str, int]] = []
    if isinstance(refs, dict):
        for k, v in refs.items():
            try:
                ref_pairs.append((str(k), int(v or 0)))
            except (TypeError, ValueError):
                continue
    elif isinstance(refs, list):
        for item in refs:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                try:
                    ref_pairs.append((str(item[0]), int(item[1] or 0)))
                except (TypeError, ValueError):
                    continue
    ref_pairs.sort(key=lambda x: -x[1])
    human_refs = [{**humanize_source_ref(k), "count": n} for k, n in ref_pairs[:8]]

    lines = [
        "📡 <b>Traffic Pulse</b> · <u>digest</u>",
        "<i>what actually moved — not the raw Redis keys</i>",
        "",
        "<b>What happened</b>",
    ]
    for kind, n in sorted(c.items(), key=lambda kv: -kv[1]):
        lines.append(f"• <b>{n}</b> {esc(humanize_pulse_kind(kind))}")

    if human_refs:
        lines.append("")
        lines.append("<b>Who showed up</b>")
        for row in human_refs:
            n = int(row.get("count") or 0)
            lines.append(
                f"• <b>{esc(row['label'])}</b>"
                + (f" · <i>{esc(row['surface'])}</i>" if row.get("surface") else "")
                + f" — {code(n)}"
            )

    lines.append("")
    lines.append("<b>Read</b>")
    lines.append(quote(pulse_read(c, human_refs)))
    lines.append("")
    lines.append("<b>Do this now</b>")
    play = pulse_playbook(c, human_refs)
    numbered = "\n".join(f"{i}. {step}" for i, step in enumerate(play, start=1))
    lines.append(quote(numbered))
    lines.append("")
    lines.append(
        f"<i>Full feed: {code('/inbox')} · instant types: {code('TBCC_TRAFFIC_PULSE_INSTANT')}</i>"
    )
    return "\n".join(lines)


def _horizon_label(raw: str | None) -> str:
    key = (raw or "ST").strip()
    return _HORIZON_HUMAN.get(key, _HORIZON_HUMAN.get(key.upper(), "now"))


def _playbook_for_direction(d: dict[str, Any]) -> str:
    bid = str(d.get("blocker_id") or d.get("source_id") or d.get("action_kind") or "")
    if bid in _BLOCKER_PLAYBOOK:
        return _BLOCKER_PLAYBOOK[bid]
    follow = str(d.get("mcp_followup") or "").strip()
    rationale = str(d.get("rationale") or "").strip()
    if rationale and follow:
        return f"{rationale.rstrip('.')} — next: {follow}."
    if rationale:
        return rationale
    if follow:
        return f"Next lever: {follow}."
    return "Keep loot/VIP checkout on the next scheduler tick."


def _snapshot_lines(bundle: dict[str, Any]) -> list[str]:
    lines = ["<b>Snapshot</b>"]
    usd = bundle.get("income_usd")
    stars = bundle.get("income_stars")
    if usd is not None or stars is not None:
        usd_s = f"${float(usd):.2f}" if usd is not None else "—"
        stars_s = f"{int(stars)}⭐" if stars is not None else "—"
        lines.append(f"• Ledger this window: <b>{esc(usd_s)}</b> · {esc(stars_s)}")
    sold = bundle.get("companion_photos_sold")
    if sold is not None:
        lines.append(f"• Companion photos sold: <b>{esc(sold)}</b>")
    funnel = bundle.get("bot_funnel") or {}
    pct = funnel.get("attributed_revenue_pct")
    if pct is not None:
        lines.append(f"• Bot-attributed revenue: <b>{esc(pct)}%</b>")
    pulse = bundle.get("traffic_pulse") or {}
    counts = _count_map(pulse.get("counts") or {})
    if counts:
        bits = [f"{n} {humanize_pulse_kind(k)}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])[:3]]
        lines.append("• Pulse: " + ", ".join(esc(b) for b in bits))
    spike = bundle.get("undress_spike") or {}
    if spike.get("spike_active"):
        ratio = f"{spike.get('hits_in_window')}/{spike.get('threshold')}"
        lines.append(f"• Undress spike: <u>active</u> · {code(ratio)}")
    if len(lines) == 1:
        lines.append("• No ledger snapshot in this bundle — using blockers and directions only.")
    return lines


def format_heuristic_brief_html(bundle: dict[str, Any]) -> str:
    """Daily revenue brief when LLM is off or failed — numbers → plain-language moves."""
    lines = [
        "💰 <b>Daily revenue brief</b> · <u>operator read</u>",
        "<i>heuristic — LLM skipped or unavailable</i>",
        "",
    ]
    lines.extend(_snapshot_lines(bundle))
    lines.append("")
    lines.append("<b>Moves, ranked by $</b>")

    items: list[dict[str, Any]] = []
    for d in (bundle.get("directions") or [])[:5]:
        items.append(d)
    if not items:
        spike = bundle.get("undress_spike") or {}
        if spike.get("spike_active"):
            items.append(
                {
                    "horizon": "ST",
                    "title": "Undress traffic is spiking — bridge it to loot/VIP now",
                    "rationale": (
                        f"{spike.get('hits_in_window')}/{spike.get('threshold')} hits in the window."
                    ),
                    "blocker_id": "gate_no_touches",
                    "mcp_followup": "/surge",
                }
            )
        for b in bundle.get("blockers") or []:
            if len(items) >= 5:
                break
            items.append(
                {
                    "horizon": "ST",
                    "title": b.get("what"),
                    "rationale": b.get("why"),
                    "blocker_id": b.get("id"),
                    "mcp_followup": "GET /analytics/ops-picture",
                }
            )
        sold = bundle.get("companion_photos_sold")
        if sold == 0 and len(items) < 5:
            items.append(
                {
                    "horizon": "ST",
                    "title": "Companion sold 0 paid photos",
                    "blocker_id": "companion_zero",
                    "rationale": "Trial traffic with no upsell.",
                }
            )
        for p in bundle.get("growth_proposals") or []:
            if len(items) >= 5:
                break
            items.append(
                {
                    "horizon": "OPS",
                    "title": p.get("recommendation") or p.get("action_kind"),
                    "rationale": p.get("recommendation") or "",
                    "mcp_followup": "growth_signal_proposals",
                }
            )
        if not items:
            items.append(
                {
                    "horizon": "ST",
                    "title": "No critical blockers — keep loot and VIP checkout on schedulers",
                    "rationale": "Idle time still costs. Next post should carry a pay CTA.",
                    "mcp_followup": "/sponsors",
                }
            )

    for i, d in enumerate(items[:5], start=1):
        horizon = _horizon_label(str(d.get("horizon") or "ST"))
        title = esc(str(d.get("title") or "Move")[:160])
        play = _playbook_for_direction(d)
        lines.append("")
        lines.append(f"{i}. <u>{esc(horizon)}</u> — <b>{title}</b>")
        lines.append(quote(esc(play)))

    lines.append("")
    lines.append(
        f"<i>Deeper: {code('/direction')} · undress blast: {code('/surge')} · sponsors: {code('/sponsors')}</i>"
    )
    text = "\n".join(lines)
    return text[:3500]


def format_direction_report_html(
    directions: list[dict[str, Any]],
    *,
    narrative: str | None = None,
    evidence_summary: dict[str, Any] | None = None,
    days: int | None = None,
) -> str:
    lines = [
        "🎯 <b>Analytics direction</b> · <u>Top 5 $ bets</u>",
        "<i>highest short-term revenue first</i>",
        "",
    ]
    if evidence_summary:
        usd = evidence_summary.get("income_usd")
        pool = evidence_summary.get("pool_approved")
        bits = []
        if usd is not None:
            bits.append(f"ledger <b>{esc(usd)}</b>")
        if pool is not None:
            bits.append(f"pool approved <b>{esc(pool)}</b>")
        if days:
            bits.append(f"{code(f'{days}d')}")
        if bits:
            lines.append(" · ".join(bits))
            lines.append("")
    if not directions:
        lines.append(quote("No ranked bets in this window. Keep loot/VIP checkout live and check /inbox."))
    for d in directions:
        horizon = _horizon_label(str(d.get("horizon") or "ST"))
        rank = d.get("rank") or ""
        title = esc(str(d.get("title") or "")[:160])
        play = _playbook_for_direction(d)
        conf = esc(str(d.get("confidence") or ""))
        lines.append(f"{rank}. <u>{esc(horizon)}</u> — <b>{title}</b>")
        if conf:
            lines.append(f"   <i>confidence {conf}</i>")
        lines.append(quote(esc(play)))
        lines.append("")
    if narrative:
        lines.append("<b>Read</b>")
        lines.append(quote(esc(narrative[:600])))
    return "\n".join(lines).strip()[:3900]


def format_draft_fail_html(*, who: str, customer_text: str) -> str:
    said = esc((customer_text or "").strip()[:280] or "(empty)")
    return "\n".join(
        [
            f"🚫 <b>Draft failed</b> · <u>{esc(who)}</u>",
            "",
            "<b>Customer said</b>",
            quote(said),
            "",
            "<b>What happened</b>",
            "The LLM never answered — they got <u>silence</u>. Nothing was sent to them.",
            "",
            "<b>Do this now</b>",
            quote(
                f"1. Fix keys in {code('/config')} (OpenRouter / Featherless).\n"
                f"2. Reply to this person yourself in the business chat so they are not left hanging.\n"
                f"3. If it keeps failing, flip that lead to Pilot and draft by hand."
            ),
        ]
    )


def format_new_lead_html(
    *,
    surface: str,
    mode_label: str,
    phase: str,
    user_id: int,
    customer_text: str,
) -> str:
    said = esc((customer_text or "").strip()[:400] or "(empty)")
    return "\n".join(
        [
            "👋 <b>New lead</b>",
            f"Surface <b>{esc(surface)}</b> · mode <u>{esc(mode_label)}</u>",
            f"Phase {code(phase)} · uid {code(user_id)}",
            "",
            "<b>They said</b>",
            quote(said),
            "",
            quote(
                "If this is a buyer question, answer with a checkout CTA "
                f"({code('/subscribe')} / {code('/packs')} / {code('/loot')}) — not a long FAQ."
            ),
        ]
    )


def format_inbox_header(*, title: str, unread_count: int) -> str:
    header = f"📬 <b>{esc(title)}</b> · <u>operator feed</u>"
    if unread_count:
        header += f"\n<i><b>{unread_count}</b> unread — money and failures first</i>"
    return header


def format_inbox_status_html(
    *,
    capture_on: bool,
    stored: int,
    unread: int,
    last_read_set: bool,
    focus: str,
    lock_events: int,
    triage_on: bool,
    triage_used: int,
    triage_cap: int,
) -> str:
    return "\n".join(
        [
            "📊 <b>Inbox status</b> · <u>capture</u>",
            "",
            f"Capture {code('on' if capture_on else 'off')} · stored {code(stored)} · unread <b>{unread}</b>",
            f"Last {code('/read')}: <i>{'set' if last_read_set else 'never'}</i>",
            f"Focus {code(focus or 'off')} · lock events {code(lock_events)}",
            f"Cursor triage {code('on' if triage_on else 'off')} "
            f"({code(f'{triage_used}/{triage_cap}')} today)",
            "",
            quote(
                "Unread payment/loot rows are the ones that print money. "
                f"Clear noise with {code('/read')} after you act."
            ),
        ]
    )


def format_stack_card_html(data: dict[str, Any] | None) -> str:
    """Tray-aligned stack status in secretary card voice."""
    if not data:
        return (
            "🖥 <b>Stack status</b> · <u>unavailable</u>\n"
            + quote(f"Empty response. Check tray {code('tbcc-stack-cli.ps1')} Status — not a terminal guess.")
        )
    if data.get("available") is False or (data.get("ok") is False and data.get("error")):
        err = esc(data.get("error") or "stack control unavailable")
        return "\n".join(
            [
                "🖥 <b>Stack status</b> · <u>unavailable</u>",
                "",
                quote(
                    f"{code(err)}\n"
                    "Tray supervisor / "
                    f"{code('tbcc-stack-cli.ps1')} required on Windows. "
                    "Do not start a second secretary from this PC."
                ),
            ]
        )
    enabled_up = data.get("enabled_up")
    enabled = data.get("enabled")
    up = data.get("up")
    total = data.get("total")
    profile = esc(data.get("profile") or "—")
    summary = f"{enabled_up}/{enabled}" if enabled_up is not None and enabled is not None else "—"
    down_on: list[str] = []
    lines = [
        "🖥 <b>Stack status</b> · <u>money processes</u>",
        "<i>truth is tray N/M — not a guess from terminals</i>",
        "",
        f"Enabled up <b>{esc(summary)}</b> · all {code(f'{up}/{total}')} · profile {code(profile)}",
        "",
    ]
    services = data.get("services")
    if isinstance(services, list) and services:
        lines.append("<b>Services</b>")
        for row in services:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("id") or "?")
            st = str(row.get("status") or ("up" if row.get("running") else "down"))
            running = bool(row.get("running") or st == "up")
            mark = "●" if running else "○"
            user_on = row.get("user_enabled")
            flag = ""
            if user_on is None:
                flag = ""
            elif user_on:
                flag = " · <i>on</i>"
            else:
                flag = " · <i>off</i>"
            st_html = f"<u>{esc(st)}</u>" if not running else esc(st)
            lines.append(f"{mark} {code(sid)} {st_html}{flag}")
            if user_on and not running:
                down_on.append(sid)
    else:
        lines.append("<i>No per-service rows (CLI may be unavailable).</i>")
    lines.append("")
    if down_on:
        names = ", ".join(down_on[:6])
        lines.append(
            quote(
                f"<b>{esc(names)}</b> is enabled but down — that can starve checkout/FOMO. "
                "Restart from tray Services or "
                f"{code('tbcc-stack-cli.ps1')} — never "
                f"{code('python -m bots.*')} in a second terminal."
            )
        )
    else:
        lines.append(
            quote(
                "Restarts: tray Services menu or "
                f"{code('tbcc-stack-cli.ps1')} — not this bot. "
                "A second spawn causes Telegram 409."
            )
        )
    return "\n".join(lines)


def format_surge_card_html(*, state: dict[str, Any], result: dict[str, Any]) -> str:
    hits = state.get("hits_in_window")
    threshold = state.get("threshold")
    spike = bool(state.get("spike_active"))
    ok = result.get("ok")
    skipped = result.get("skipped")
    reason = result.get("reason")
    queued = result.get("queued") or []
    err = result.get("error")
    lines = [
        "🔥 <b>Undress surge</b> · <u>blast</u>",
        f"Hits {code(f'{hits}/{threshold}')} · spike "
        + ("<u>active</u>" if spike else "<i>quiet</i>"),
        f"Blast {code(ok)}",
    ]
    if skipped:
        lines.append(f"Skipped {code(reason)}")
    if queued:
        lines.append(f"Queued <b>{len(queued)}</b> scheduler(s)")
    if err:
        lines.append(f"Error {code(err)}")
    lines.append("")
    if ok and queued:
        read = (
            "Surge copy is on the scheduler. Watch the next @aofmainhub / Loot Room post "
            "for the undress CTA — then confirm a beacon click lands."
        )
        action = f"Open {code('/inbox traffic')} in a few minutes. If zero clicks, the deep link is wrong."
    elif skipped:
        read = f"Blast did not fire ({esc(reason) or 'skipped'}). Traffic may already be in cooldown or below threshold."
        action = f"If you still want it live, check {code('/inbox')} then retry {code('/surge')}."
    elif err:
        read = "The blast hit an error — undress traffic is not being bridged to loot/VIP."
        action = f"Read the error above, then {code('/stack')} if workers look down."
    elif spike:
        read = "Spike is active. If the blast did not queue, FOMO is leaking."
        action = f"Retry {code('/surge')} once. Do not spam it."
    else:
        read = "No spike right now. Forcing a blast still posts — only do that if you saw undress clicks."
        action = f"Prefer waiting for a real spike, or check {code('/direction')} for a better $ move."
    lines.append("<b>Read</b>")
    lines.append(quote(read))
    lines.append("<b>Do this now</b>")
    lines.append(quote(action))
    return "\n".join(lines)


def format_flywheel_card_html(*, status: dict[str, Any], pending: list[dict[str, Any]]) -> str:
    enabled = status.get("enabled")
    approval = status.get("approval")
    codes = status.get("registry_codes") or []
    n = len(pending)
    lines = [
        "🔄 <b>Ops flywheel</b> · <u>infra proposals</u>",
        f"Enabled {code(enabled)} · approval {code(approval)} · pending <b>{n}</b>",
        f"Registry {code(len(codes))} codes",
        "",
    ]
    if pending:
        lines.append("<b>Waiting on you</b>")
        for p in pending[:5]:
            label = esc(str(p.get("label") or "")[:80])
            lines.append(
                f"• {code(p.get('id'))} <b>{esc(p.get('code'))}</b>"
                + (f" — <i>{label}</i>" if label else "")
            )
        lines.append("")
        lines.append(
            quote(
                "These do not auto-run destructive lanes. Tap <b>Approve</b> in this chat "
                "only when you want the infra fix. Growth proposals stay observe-only."
            )
        )
    else:
        lines.append(
            quote(
                "Nothing pending. Tick is "
                f"{code('tbcc/scripts/run-tbcc-flywheel-tick.ps1')} "
                f"or {code('POST /ops/flywheel/tick')}. "
                "OpenClaw notes: "
                f"{code('tbcc/docs/OPENCLAW_TBCC_INTEGRATION.md')}."
            )
        )
    return "\n".join(lines)
