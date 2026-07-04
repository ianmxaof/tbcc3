"""Rotating gate / link-wrap FOMO + how-to copy for AOF network post variations."""

from __future__ import annotations

import html


def gate_fomo_post_bodies() -> list[str]:
    """
    HTML caption bodies (no footer) — instructional + FOMO for Linkvertise / wrapped gates.
    Appended to scheduler variations and liveness copy pools.
    """
    return [
        (
            "🔗 <b>Gate in 30 seconds</b>\n"
            "Still don't know how to open Linkvertise links in 2026?\n"
            "Tap the link → <b>Complete Actions</b> → <b>Get Link</b>. Folder unlocks."
        ),
        (
            "📎 <b>Wrapped link = one step</b>\n"
            "One short ad between you and the file. Open the gate, finish the task, "
            "hit <b>Continue</b> — that's the whole ritual."
        ),
        (
            "🧠 <b>First time on a gate?</b>\n"
            "Don't skip the middle page. Complete Actions → Get Link. "
            "If it loops, wait 5s and tap Continue again."
        ),
        (
            "⏱ <b>2026 meta</b>\n"
            "People who complain about gates never learned the 3-tap flow. "
            "You already know: open → complete → download."
        ),
        (
            "🔓 <b>Gate completion tip</b>\n"
            "Work.ink / Linkvertise / hub links all work the same — "
            "finish the step, then the real URL appears. Worth the 30 seconds."
        ),
    ]


def gate_fomo_with_lane(name: str, gate_url: str) -> str:
    """Single variation naming a lane gate (when a wrapped URL is available)."""
    anchor = html.escape(name)
    url = html.escape(gate_url, quote=True)
    return (
        f"🔗 <b>{anchor}</b> — gate reminder\n"
        f"Still stuck on wrapped links? {_a(url, 'open gate')} → Complete Actions → Get Link."
    )


def _a(url: str, label: str) -> str:
    return f'<a href="{url}">{html.escape(label)}</a>'
