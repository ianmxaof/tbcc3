"""Replace bare Linkvertise URLs in Telegram HTML copy with contextual <a href> anchors."""

from __future__ import annotations

import html
import re
from base64 import b64decode
from urllib.parse import parse_qs, unquote, urlparse

_LV_HOSTS = (
    "linkvertise.com",
    "link-center.net",
    "link-to.net",
    "direct-link.net",
    "up-to-down.net",
)

_LV_URL_RE = re.compile(
    r"https?://(?:"
    + "|".join(re.escape(h) for h in _LV_HOSTS)
    + r")[^\s\]\)<>\"']+",
    re.IGNORECASE,
)

_A_TAG_RE = re.compile(r"<a\s+[^>]*href\s*=", re.IGNORECASE)

_CONTEXT_ANCHORS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bAOF\s+ASS\b", re.I), "AOF ASS"),
    (re.compile(r"\bAOF\s+AI\b", re.I), "AOF AI"),
    (re.compile(r"\bBIG\s*TITS\b", re.I), "big tits vault"),
    (re.compile(r"\bMILF\b", re.I), "MILF pack"),
    (re.compile(r"\bTABOO\b", re.I), "taboo gate"),
    (re.compile(r"\bVOYEUR\b", re.I), "voyeur feed"),
    (re.compile(r"\bLOOT\b", re.I), "loot room"),
    (re.compile(r"\bADDLIST\b", re.I), "full map"),
    (re.compile(r"\bMAIN\s+(HUB|GROUP)\b", re.I), "main hub"),
    (re.compile(r"\bMEGA\b", re.I), "mega vault"),
    (re.compile(r"\bPACK\b", re.I), "pack drop"),
    (re.compile(r"\bHUB\b", re.I), "links hub"),
]

_FALLBACK_ANCHORS = (
    "unlock",
    "enter",
    "gate",
    "vault",
    "corridor",
    "threshold",
    "pack",
    "drop",
    "access",
)


def is_linkvertise_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _LV_HOSTS)


def decode_lv_destination(url: str) -> str | None:
    """Best-effort decode of dynamic ?r= payload to the wrapped destination."""
    try:
        qs = parse_qs(urlparse(url).query)
        raw = (qs.get("r") or [None])[0]
        if not raw:
            return None
        for decoder in (lambda s: b64decode(s + "=="), lambda s: b64decode(s)):
            try:
                return unquote(decoder(raw).decode("utf-8", errors="replace"))
            except Exception:
                continue
    except Exception:
        return None
    return None


def _line_for_index(text: str, idx: int) -> str:
    start = text.rfind("\n", 0, idx) + 1
    end = text.find("\n", idx)
    if end < 0:
        end = len(text)
    return text[start:end]


def _label_before_url_on_line(line: str, url: str) -> str | None:
    """e.g. '🔥 AOF ASS: https://...' → 'AOF ASS'."""
    pos = line.find(url)
    if pos < 0:
        return None
    prefix = line[:pos].strip()
    if not prefix:
        return None
    prefix = re.sub(r"^[\s\W_]+", "", prefix)
    prefix = re.sub(r"[:：\-–—>]+$", "", prefix).strip()
    if not prefix or len(prefix) > 48:
        return None
    # Drop leading emoji / symbols, keep words.
    cleaned = re.sub(
        r"^[\U0001F300-\U0001FAFF\u2600-\u27BF\W_]+",
        "",
        prefix,
    ).strip()
    return cleaned or prefix


def _anchor_from_destination(dest: str | None) -> str | None:
    if not dest:
        return None
    low = dest.lower()
    if "/addlist/" in low:
        return "full map"
    if "loot" in low:
        return "loot room"
    if "mega.nz" in low or "pixeldrain" in low:
        return "vault"
    if "t.me" in low or "telegram" in low:
        return "enter"
    return None


def pick_anchor_text(*, url: str, text: str, match_start: int) -> str:
    line = _line_for_index(text, match_start)
    label = _label_before_url_on_line(line, url)
    if label and not is_linkvertise_url(label):
        return label

    window = text[max(0, match_start - 240) : match_start + 80]
    for pat, anchor in _CONTEXT_ANCHORS:
        if pat.search(window):
            return anchor

    dest_anchor = _anchor_from_destination(decode_lv_destination(url))
    if dest_anchor:
        return dest_anchor

    idx = sum(ord(c) for c in url) % len(_FALLBACK_ANCHORS)
    return _FALLBACK_ANCHORS[idx]


def _inside_html_anchor(text: str, url_start: int) -> bool:
    """True when url_start falls inside an existing <a href=…>…</a> block."""
    before = text[:url_start]
    last_open = before.rfind("<a")
    if last_open < 0:
        return False
    chunk = before[last_open:]
    if not _A_TAG_RE.search(chunk):
        return False
    after = text[url_start:]
    close = after.find("</a>")
    if close < 0:
        return True
    return False


def obfuscate_bare_lv_urls_in_text(text: str) -> tuple[str, list[dict]]:
    """
    Replace naked Linkvertise URLs with Telegram HTML hyperlinks.
    Skips URLs already inside <a href>. Returns (new_text, change log).
    """
    raw = text or ""
    if not raw or not _LV_URL_RE.search(raw):
        return raw, []

    changes: list[dict] = []
    out: list[str] = []
    pos = 0
    for m in _LV_URL_RE.finditer(raw):
        url = m.group(0)
        start, end = m.start(), m.end()
        if _inside_html_anchor(raw, start):
            out.append(raw[pos:end])
            pos = end
            continue

        anchor = pick_anchor_text(url=url, text=raw, match_start=start)
        tag = f'<a href="{html.escape(url, quote=True)}">{html.escape(anchor)}</a>'
        line = _line_for_index(raw, start)
        prefix = line[: line.find(url)]
        label = _label_before_url_on_line(line, url)
        replace_start = start
        if label and anchor.lower() == label.lower() and prefix.strip():
            emoji_m = re.match(r"^([\U0001F300-\U0001FAFF\u2600-\u27BF\W_\s]*)", prefix)
            if emoji_m:
                replace_start = start - (len(prefix) - len(emoji_m.group(1)))
                out.append(raw[pos:replace_start])
                out.append(f"{emoji_m.group(1)}{tag}")
            else:
                replace_start = start - len(prefix)
                out.append(raw[pos:replace_start])
                out.append(tag)
        else:
            out.append(raw[pos:start])
            out.append(tag)
        changes.append({"url": url[:120], "anchor": anchor})
        pos = end
    out.append(raw[pos:])
    return "".join(out), changes


def count_bare_lv_urls(text: str | None) -> int:
    if not text:
        return 0
    n = 0
    for m in _LV_URL_RE.finditer(text):
        if not _inside_html_anchor(text, m.start()):
            n += 1
    return n
