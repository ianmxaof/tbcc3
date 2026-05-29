from __future__ import annotations

import html
import re
from typing import Any

# Allowed placeholders; anything else is ignored to avoid surprises if templates go wrong.
_ALLOWED_PLACEHOLDERS = frozenset(
    {
        "emoji",
        "headline",
        "artist",
        "title",
        "album",
        "album_line",
        "url",
        "source",
        "source_label",
        "link",
    }
)


def _safe_url_href(url: str) -> str:
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return "#"
    return html.escape(u, quote=True)


def default_template() -> str:
    return "{emoji} {headline}{album_line}\n{source_label} · {link}"


def format_relay_html(
    *,
    artist: str,
    title: str,
    album: str | None,
    url: str | None,
    source: str,
    source_label: str,
    template_html: str | None,
) -> str:
    em = "▶️" if (source or "").lower() in {"youtube", "video", "ifttt", "webhook"} else "🎵"
    art = (artist or "").strip()
    ttl = (title or "").strip()
    alb = (album or "").strip() or None
    raw_url = (url or "").strip() or None
    album_line = f"\n📀 <i>{html.escape(alb)}</i>" if alb else ""
    href = _safe_url_href(raw_url or "")
    link_html = f'<a href="{href}">open</a>' if raw_url else "<i>no link</i>"
    if art and ttl:
        headline = f"<b>{html.escape(art)}</b> — {html.escape(ttl)}"
    elif ttl:
        headline = f"<b>{html.escape(ttl)}</b>"
    elif art:
        headline = f"<b>{html.escape(art)}</b>"
    else:
        headline = ""
    values: dict[str, str] = {
        "emoji": em,
        "headline": headline,
        "artist": html.escape(art),
        "title": html.escape(ttl),
        "album": html.escape(alb) if alb else "",
        "album_line": album_line,
        "source": html.escape((source or "unknown").strip()),
        "source_label": html.escape((source_label or source or "Listening").strip()),
        "url": href,
        "link": link_html,
    }
    tpl = (template_html or "").strip() or default_template()

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in _ALLOWED_PLACEHOLDERS:
            return m.group(0)
        return values.get(key, "")

    out = re.sub(r"\{([a-z_]+)\}", repl, tpl)
    return out.strip()


def append_relay_footer(html_body: str, footer_html: str) -> str:
    """Append promo/flavor copy below the scrobble block (Telegram HTML; no placeholders)."""
    foot = (footer_html or "").strip()
    if not foot:
        return (html_body or "").strip()
    base = (html_body or "").strip()
    if not base:
        return foot
    return f"{base}\n\n{foot}"


def ensure_relay_pre_block(raw: str) -> str:
    """
    Wrap plain text or HTML in a Telegram <pre> block (tap-to-copy panel in clients).

    If the editor already contains <pre> or <pre><code>, leave unchanged.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if re.search(r"<\s*pre\b", s, re.I):
        return s
    return f"<pre>{html.escape(s)}</pre>"


def compose_listening_relay_messages(
    *,
    artist: str,
    title: str,
    album: str | None,
    url: str | None,
    source: str,
    source_label: str,
    template_html: str | None,
    footer_html: str,
    copy_block_html: str,
) -> tuple[str, str | None]:
    """
    Build main relay HTML (scrobble + flavor footer) and optional follow-up <pre> copy block.

    Telegram always renders link previews at the bottom of the first message, so the copy
    block is sent as a second silent message to appear under the Last.fm preview card.
    """
    main = append_relay_footer(
        format_relay_html(
            artist=artist,
            title=title,
            album=album,
            url=url,
            source=source,
            source_label=source_label,
            template_html=template_html,
        ),
        footer_html,
    )
    followup = ensure_relay_pre_block(copy_block_html)
    return main, (followup or None)


def parse_lastfm_recent_track(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extract newest track from Last.fm user.getrecenttracks JSON."""
    try:
        recent = payload["recenttracks"]["track"]
    except (KeyError, TypeError):
        return None
    if isinstance(recent, dict):
        newest = recent
    elif isinstance(recent, list) and recent:
        newest = recent[0]
    else:
        return None

    title = _lf_text(newest.get("name"))
    artist = _lf_text((newest.get("artist") or {}).get("#text"))
    album = _lf_text((newest.get("album") or {}).get("#text")) or None
    url = (newest.get("url") or "").strip() or None
    date_obj = newest.get("date") or {}
    uts = date_obj.get("uts") if isinstance(date_obj, dict) else None
    nowplaying = False
    if isinstance(newest.get("@attr"), dict):
        nowplaying = str(newest["@attr"].get("nowplaying", "")).lower() == "true"
    if not title and not artist:
        return None
    sig_parts = [artist or "", title or "", str(uts or ("np" if nowplaying else ""))]
    mbid = newest.get("mbid")
    if mbid:
        sig_parts.insert(0, f"mbid:{mbid}")
    signature = "|".join(sig_parts)
    return {
        "artist": artist,
        "title": title,
        "album": album,
        "url": url,
        "signature": signature,
        "nowplaying": nowplaying,
    }


def _lf_text(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip()
