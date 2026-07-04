"""Caption body for AOF FULL LENGTH — performer/title line, hashtags, diamond tag footer."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.llm_shop_suggest import hashtag_line_from_slugs
from app.services.send_tag_enrich import is_junk_label

MOVIE_BODY_PLACEHOLDER = "{{MOVIE_BODY}}"

_SKIP_SLUG_PREFIXES = ("type-", "src-")
_SKIP_SLUGS = frozenset(
    {
        "nsfw-unknown",
        "explicit",
        "suggestive",
        "sfw",
        "porn",
        "sexy",
        "hentai",
        "drawings",
        "neutral",
    }
)

_CATEGORY_EMOJI: dict[str, str] = {
    "milf": "🍑",
    "gilf": "🍑",
    "blowjob": "💋",
    "blowjobs": "💋",
    "big-tits": "🍈",
    "just-boobs": "🍈",
    "ass": "🍑",
    "thick-booty": "🍑",
    "taboo": "🔞",
    "voyeur": "👀",
    "public": "👀",
    "amateur": "📸",
    "amateur-girls": "📸",
    "blonde": "👱‍♀️",
    "ebony": "✨",
    "latina": "🌶️",
    "asian": "🌸",
    "abg": "🌸",
    "lbfm": "🌸",
    "goon": "🌀",
    "gloryhole": "🕳️",
    "hardcore": "🔥",
    "full-length": "🎬",
}


def _classification_extras(media) -> dict[str, Any]:
    raw = getattr(media, "classification_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _lustpress_title(media) -> str:
    extras = _classification_extras(media)
    lp = extras.get("lustpress")
    if isinstance(lp, dict):
        title = (lp.get("title") or "").strip()
        if title and not is_junk_label(title):
            return title
    return ""


def _filename_hint(media) -> str:
    for raw in (
        getattr(media, "source_channel", None) or "",
        getattr(media, "file_unique_id", None) or "",
        getattr(media, "file_id", None) or "",
    ):
        s = str(raw).strip()
        if not s or s.startswith("http"):
            continue
        base = s.rsplit("/", 1)[-1]
        base = re.sub(r"\.[a-z0-9]{2,5}$", "", base, flags=re.I)
        base = re.sub(r"[_\-.]+", " ", base).strip()
        if len(base) >= 3 and not is_junk_label(base):
            return base[:80]
    return ""


def _tag_rows_for_media(db: Session, media_id: int) -> list[tuple[str, str, str | None, str]]:
    from app.models.tbcc_tag import MediaTagLink, TbccTag

    rows = (
        db.query(MediaTagLink, TbccTag)
        .join(TbccTag, TbccTag.id == MediaTagLink.tag_id)
        .filter(MediaTagLink.media_id == int(media_id))
        .order_by(MediaTagLink.confidence.desc().nullslast(), TbccTag.slug.asc())
        .all()
    )
    out: list[tuple[str, str, str | None, str]] = []
    seen: set[str] = set()
    for link, tag in rows:
        slug = (tag.slug or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append((slug, (tag.name or slug).strip(), tag.category, link.source or ""))
    return out


def _public_tag_rows(
    rows: list[tuple[str, str, str | None, str]],
) -> list[tuple[str, str, str | None]]:
    out: list[tuple[str, str, str | None]] = []
    for slug, name, cat, _src in rows:
        if any(slug.startswith(p) for p in _SKIP_SLUG_PREFIXES):
            continue
        if slug in _SKIP_SLUGS:
            continue
        if is_junk_label(name):
            continue
        out.append((slug, name, cat))
    return out


def _title_emojis(primary_slug: str | None) -> str:
    if not primary_slug:
        return "🎬🎬🎬"
    em = _CATEGORY_EMOJI.get(primary_slug.lower())
    if em:
        return f"{em}{em}{em}"
    return "🎬🎬🎬"


def _title_line(media, rows: list[tuple[str, str, str | None]]) -> str:
    lp = _lustpress_title(media)
    if lp:
        base = lp.upper()
        slug = rows[0][0] if rows else None
        return f"{base}{_title_emojis(slug)}"

    if rows:
        slug, name, _cat = rows[0]
        label = name if name and not is_junk_label(name) else slug.replace("-", " ")
        return f"{label.upper()}{_title_emojis(slug)}"

    hint = _filename_hint(media)
    if hint:
        return f"{hint.upper()}🎬🎬🎬"
    return "FULL LENGTH DROP🎬🎬🎬"


def _duration_line(media) -> str:
    extras = _classification_extras(media)
    for key in ("duration_sec", "duration_seconds", "duration"):
        raw = extras.get(key)
        if raw is None:
            continue
        try:
            sec = int(float(raw))
        except (TypeError, ValueError):
            continue
        if sec <= 0:
            continue
        mins, rem = divmod(sec, 60)
        return f"{mins}m : {rem}s"
    return ""


def _diamond_tag_line(names: list[str], *, limit: int = 8) -> str:
    clean = [n.strip() for n in names if n and n.strip() and not is_junk_label(n)]
    if not clean:
        return ""
    parts = clean[:limit]
    return "🔶 " + " 🔶 ".join(parts)


def build_movie_body_for_media(db: Session, media) -> str:
    """MILF-FAN / GloryHole hybrid: title + optional duration + hashtags + diamond tags."""
    rows = _public_tag_rows(_tag_rows_for_media(db, int(media.id)))
    title = _title_line(media, rows)
    duration = _duration_line(media)
    slugs = [slug for slug, _name, _cat in rows]
    hashtags = hashtag_line_from_slugs(slugs, limit=12)
    display_names = [name for _slug, name, _cat in rows]
    diamonds = _diamond_tag_line(display_names)

    lines: list[str] = [title]
    if duration:
        lines.append(duration)
    if hashtags:
        lines.append(hashtags)
    if diamonds:
        lines.append(diamonds)
    return "\n\n".join(lines)


def inject_movie_body(template: str, body: str) -> str:
    tpl = (template or "").strip()
    if MOVIE_BODY_PLACEHOLDER in tpl:
        return tpl.replace(MOVIE_BODY_PLACEHOLDER, body.strip())
    if tpl:
        return f"{tpl}\n\n{body.strip()}"
    return body.strip()


def full_length_caption_templates() -> list[str]:
    """Shell templates rotated on send; body is injected from pool media tags."""
    headers = (
        "🎬 <b>AOF FULL LENGTH</b> — feature drop, zero filler",
        "🍿 <b>FEATURE FILM</b> — chronological lane, curated not scraped blind",
        "🎞️ <b>FULL RUN</b> — another movie cleared the pipeline",
        "⭐ <b>PREMIERE DROP</b> — long-form lane · search tags below",
    )
    ctas = (
        "➡️ ✅ WATCH FULL VIDEO ⬅️",
        "▶️ Full movie below — tap tags to browse the vault",
        "🎬 New full-length deposit — hashtags are your search keys",
    )
    out: list[str] = []
    seen: set[str] = set()
    for h in headers:
        for cta in ctas:
            block = f"{h}\n\n{cta}\n\n{MOVIE_BODY_PLACEHOLDER}"
            if block in seen:
                continue
            seen.add(block)
            out.append(block)
    return out
