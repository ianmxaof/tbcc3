"""
Macro / model search engine — parity with tbcc/extension/model-search-shared.js.

Loads built-in sites from extension/model-search-sites.json, merges DB custom sources,
probes search pages, and extracts video links from result HTML.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

MODEL_SEARCH_CATEGORY_ONLYFANS = "onlyfans"
MODEL_SEARCH_CATEGORY_LIVECAMS = "livecams"
MODEL_SEARCH_CATEGORY_VIDEOS = "videos"
MODEL_SEARCH_CATEGORY_MACRO = "macro"

_BUILTIN_JSON = (
    Path(__file__).resolve().parent.parent.parent.parent / "extension" / "model-search-sites.json"
)


def normalize_model_search_category(raw: object | None) -> str:
    s = str(raw or "").strip().lower()
    if s in ("archives", "archive", "onlyfans", "onlyfans_search"):
        return MODEL_SEARCH_CATEGORY_ONLYFANS
    if s in ("cam", "cams", "livecams", "live_cams"):
        return MODEL_SEARCH_CATEGORY_LIVECAMS
    if s in ("video", "videos", "video_search", "clips"):
        return MODEL_SEARCH_CATEGORY_VIDEOS
    if s in ("macro", "macro_search", "native", "engine"):
        return MODEL_SEARCH_CATEGORY_MACRO
    return MODEL_SEARCH_CATEGORY_ONLYFANS


def build_model_search_url(template: str, username: str) -> str:
    return str(template or "").replace("{username}", quote(str(username).strip(), safe=""))


def derive_username_template_from_search_url(raw_url: str, sample_username: str) -> str | None:
    """Turn a completed search URL into a {username} template (extension panel helper)."""
    url = str(raw_url or "").strip()
    user = str(sample_username or "").strip().lstrip("@")
    if not url or not user:
        return None
    enc = quote(user, safe="")
    variants = [user, enc, user.lower(), enc.lower()]
    for v in variants:
        if not v:
            continue
        idx = url.find(v)
        if idx >= 0:
            return url[:idx] + "{username}" + url[idx + len(v) :]
    return None


def _host_from_url(url: str) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return ""


def _url_matches_host(url: str, *hosts: str) -> bool:
    host = _host_from_url(url)
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in hosts if h)


# Host-specific probe rules ported from ARNA userscript (reduces false +/- on cam archives).
_SITE_PROBE_RULES: tuple[dict[str, Any], ...] = (
    {
        "hosts": ("livecamrips.to",),
        "deny_contains": ("no records found", "no models found", "no results", "0 models found"),
        "require_any": ('class="video"', "model-card"),
    },
    {
        "hosts": ("cumcams.cc",),
        "deny_regex": (r"<h1[^>]*>\s*404\s*</h1>", r"performer\s+not\s+found"),
        "require_any": ("profile-info", 'class="performer"'),
    },
    {
        "hosts": ("allmy.cam",),
        "require_any": ('class="video-card"',),
    },
    {
        "hosts": ("showcamrips.com",),
        "deny_contains": ("data:image/png;base64",),
    },
    {
        "hosts": ("camshowrecordings.com",),
        "require_any": ('class="h1modelpage"',),
    },
    {
        "hosts": ("livecamsrip.com",),
        "deny_contains": ("no records found",),
    },
    {
        "hosts": ("camwhores.tv", "camwhoresbay.com"),
        "deny_regex": (
            r"there\s+is\s+no\s+data\s+in\s+this\s+list",
            r"no\s+videos?\s+found",
            r"\b0\s+videos\b",
        ),
    },
)


def _extract_title_lower(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip().lower()


def apply_site_probe_rules(html: str, final_url: str = "") -> dict[str, Any] | None:
    """Return deny/confirm override for known archive hosts, or None to continue generic analysis."""
    if not html:
        return None
    lower = html.lower()
    for rule in _SITE_PROBE_RULES:
        if not _url_matches_host(final_url, *rule.get("hosts", ())):
            continue
        for needle in rule.get("deny_contains", ()):
            if str(needle).lower() in lower:
                return {"action": "deny", "signal": "site_deny", "reason": "none"}
        for pattern in rule.get("deny_regex", ()):
            if re.search(str(pattern), html, re.I):
                return {"action": "deny", "signal": "site_deny", "reason": "none"}
        required = rule.get("require_any", ())
        if required:
            if not any(str(marker).lower() in lower for marker in required):
                return {"action": "deny", "signal": "site_require", "reason": "none"}
            return {"action": "confirm", "count": 1, "signal": "site_markers", "reason": "ok"}
    return None


def guess_result_count_from_html(html: str) -> int | None:
    if not html or not isinstance(html, str):
        return None
    m = re.search(r"(\d[\d,]*)\s*(results?|entries|posts?|items?|found|hits?|videos?|photos?|models?)\b", html, re.I)
    if m:
        return int(m.group(1).replace(",", "")) or None
    m2 = re.search(r"(?:total|about|count|results?)\s*[:\s]*\s*(\d[\d,]*)", html, re.I)
    if m2:
        return int(m2.group(1).replace(",", "")) or None
    m3 = re.search(r'"total(?:Count|_count)?"\s*:\s*(\d+)', html, re.I)
    if m3:
        return int(m3.group(1)) or None
    return None


def analyze_model_search_html(html: str, final_url: str = "", *, username: str = "") -> dict[str, Any]:
    """Best-effort: does this search page look like it has content?

    Returns confidence: high | medium | none — weak page-size/keyword fallback removed.
    """
    if not html or not isinstance(html, str) or len(html) < 40:
        return {"has_results": False, "count": 0, "reason": "empty", "confidence": "none", "signal": "empty"}

    lower = html.lower()
    user_lc = str(username or "").strip().lower()
    blocked = bool(
        re.search(
            r"just a moment|cf-browser-verification|attention required|enable javascript|"
            r"ddos protection|checking your browser|cloudflare",
            html,
            re.I,
        )
    )
    if blocked:
        return {"has_results": False, "count": 0, "reason": "blocked", "confidence": "none", "signal": "blocked"}

    site_rule = apply_site_probe_rules(html, final_url)
    if site_rule and site_rule.get("action") == "deny":
        return {
            "has_results": False,
            "count": 0,
            "reason": site_rule.get("reason") or "none",
            "confidence": "none",
            "signal": site_rule.get("signal") or "site_deny",
            "final_url": final_url or "",
        }

    title_lc = _extract_title_lower(html)
    if title_lc and any(term in title_lc for term in ("not found", "404", "error")):
        return {
            "has_results": False,
            "count": 0,
            "reason": "none",
            "confidence": "none",
            "signal": "title_not_found",
            "final_url": final_url or "",
        }

    stripped = html.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            data = json.loads(html)
            arr = data if isinstance(data, list) else data.get("items") if isinstance(data, dict) else None
            if isinstance(arr, list):
                n = len(arr)
                conf = "high" if n >= 2 else ("medium" if n == 1 else "none")
                return {
                    "has_results": n > 0,
                    "count": n,
                    "reason": "ok" if n > 0 else "none",
                    "confidence": conf,
                    "signal": "json",
                    "final_url": final_url or "",
                }
            if isinstance(data, dict) and data.get("total") is not None:
                n = int(data["total"])
                if n >= 0:
                    conf = "high" if n >= 2 else ("medium" if n == 1 else "none")
                    return {
                        "has_results": n > 0,
                        "count": n,
                        "reason": "ok" if n > 0 else "none",
                        "confidence": conf,
                        "signal": "json_total",
                        "final_url": final_url or "",
                    }
        except Exception:
            pass

    explicit_empty = bool(
        re.search(
            r"\bno\s+results?\b|\b0\s+results?\b|nothing\s+found|no\s+matches|not\s+found|"
            r"no\s+videos?\s+found|\b0\s+videos\b|does\s+not\s+exist|no\s+records\s+found|"
            r"there\s+is\s+no\s+data\s+in\s+this\s+list|keine\s+ergebnisse|aucun\s+résultat",
            lower,
            re.I,
        )
    )
    count = guess_result_count_from_html(html)
    signal = "count_regex" if count is not None else "none"

    if explicit_empty and (count is None or count == 0):
        return {
            "has_results": False,
            "count": 0,
            "reason": "none",
            "confidence": "none",
            "signal": "explicit_empty",
            "final_url": final_url or "",
        }

    if count is None:
        patterns = [
            r'class="[^"]*(?:video-card|result-item|post-item|model-card|thumb-card|grid-item|album-item)',
            r"<article\b",
            r"data-post-id=",
            r'class="[^"]*post\b[^"]*"',
        ]
        cards = 0
        for p in patterns:
            cards = max(cards, len(re.findall(p, html, re.I)))
        if cards >= 2:
            count = cards
            signal = "cards"
        elif cards == 1:
            count = 1
            signal = "cards"

    if (count is None or count == 0) and re.search(
        r"404|page not found|doesn't exist|user not found|model not found", lower, re.I
    ):
        return {
            "has_results": False,
            "count": 0,
            "reason": "none",
            "confidence": "none",
            "signal": "not_found",
            "final_url": final_url or "",
        }

    if site_rule and site_rule.get("action") == "confirm":
        count = max(int(site_rule.get("count") or 1), int(count or 0))
        signal = str(site_rule.get("signal") or "site_markers")
        has_results = True
    else:
        has_results = count is not None and count > 0
        if has_results and user_lc and user_lc not in lower:
            # Count signals without the searched handle in static HTML are usually template noise.
            has_results = False
            count = 0
            signal = "no_username_in_html"

    confidence = "none"
    if has_results:
        if signal in ("json", "json_total", "site_markers") or (count or 0) >= 2:
            confidence = "high"
        else:
            confidence = "medium"

    return {
        "has_results": has_results,
        "count": count if has_results else 0,
        "reason": "ok" if has_results else "none",
        "confidence": confidence,
        "signal": signal,
        "final_url": final_url or "",
    }


def load_builtin_model_search_config() -> dict[str, Any]:
    if not _BUILTIN_JSON.is_file():
        return {"version": 0, "sites": []}
    with _BUILTIN_JSON.open(encoding="utf-8") as f:
        return json.load(f)


def _normalize_site_row(site: dict[str, Any], *, builtin: bool) -> dict[str, Any] | None:
    sid = str(site.get("id") or "").strip()
    name = str(site.get("name") or sid).strip()
    url = str(site.get("url") or "").strip()
    if not sid or not name or "{username}" not in url:
        return None
    if not url.startswith(("http://", "https://")):
        return None
    try:
        probe = url.replace("{username}", "x")
        urlparse(probe)
    except Exception:
        return None
    row: dict[str, Any] = {
        "id": sid[:64],
        "name": name[:128],
        "url": url[:1024],
        "category": normalize_model_search_category(site.get("category")),
        "builtin": builtin,
    }
    for key in ("result_link_regex",):
        v = str(site.get(key) or "").strip()
        if v:
            row[key] = v[:512]
    for key in ("result_link_must_include", "result_link_deny_include"):
        raw = site.get(key)
        if isinstance(raw, list):
            vals = [str(x).strip()[:128] for x in raw if str(x).strip()]
            if vals:
                row[key] = vals[:20]
    return row


def merge_model_search_sites(
    custom_sites: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    cfg = load_builtin_model_search_config()
    built: list[dict[str, Any]] = []
    for s in cfg.get("sites") or []:
        if not isinstance(s, dict):
            continue
        row = _normalize_site_row(s, builtin=True)
        if row:
            built.append(row)
    out = list(built)
    seen = {x["id"] for x in out}
    for s in custom_sites or []:
        if not isinstance(s, dict):
            continue
        row = _normalize_site_row(s, builtin=False)
        if row and row["id"] not in seen:
            out.append(row)
            seen.add(row["id"])
    return out


def get_macro_search_sites(
    *,
    custom_sites: list[dict[str, Any]] | None = None,
    disabled_ids: set[str] | None = None,
    category: str = MODEL_SEARCH_CATEGORY_MACRO,
) -> list[dict[str, Any]]:
    disabled = {str(x).strip() for x in (disabled_ids or set()) if str(x).strip()}
    cat = normalize_model_search_category(category)
    sites = merge_model_search_sites(custom_sites)
    return [s for s in sites if s.get("category") == cat and s["id"] not in disabled]


def validate_custom_source_url(url: str) -> str | None:
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return "URL must start with http:// or https://"
    if "{username}" not in u:
        return "URL must include {username} where the search term goes."
    try:
        urlparse(u.replace("{username}", "probe"))
    except Exception:
        return "Invalid URL."
    return None


def extract_video_links_from_html(
    html_text: str,
    page_url: str,
    source_cfg: dict[str, Any],
    username: str,
    max_links: int,
) -> list[str]:
    """Port of payment_bot._extract_urls_from_html — shared for macro search results."""
    links: list[str] = []
    seen: set[str] = set()
    pattern = str(source_cfg.get("result_link_regex") or "").strip()
    must_inc = [str(x).strip().lower() for x in (source_cfg.get("result_link_must_include") or []) if str(x).strip()]
    deny_inc = [str(x).strip().lower() for x in (source_cfg.get("result_link_deny_include") or []) if str(x).strip()]
    root_host = (urlparse(page_url).hostname or "").lower()

    raw_hits: list[str] = []
    if pattern:
        try:
            rx = re.compile(pattern, re.IGNORECASE)
            for m in rx.finditer(html_text):
                if m.groups():
                    raw_hits.append(m.group(1))
                else:
                    raw_hits.append(m.group(0))
        except re.error:
            raw_hits = []
    if not raw_hits:
        raw_hits = re.findall(r"""href\s*=\s*["']([^"'#]+)["']""", html_text, flags=re.IGNORECASE)

    for raw in raw_hits:
        if not raw:
            continue
        u = str(raw).strip()
        full = urljoin(page_url, u)
        if not full.startswith(("http://", "https://")):
            continue
        try:
            pu = urlparse(full)
        except Exception:
            continue
        host = (pu.hostname or "").lower()
        if root_host and host and host != root_host:
            continue
        lower = full.lower()
        if any(x in lower for x in ("javascript:", "mailto:", "/cdn-cgi/", ".css", ".js")):
            continue
        if any(d in lower for d in deny_inc):
            continue
        if must_inc and not any(m in lower for m in must_inc):
            continue
        if not must_inc:
            looks_like_video = any(k in lower for k in ("/video", "/videos", "/watch", "/clip", "/movie"))
            has_username = username.lower() in lower
            if not (looks_like_video or has_username):
                continue
        if full in seen:
            continue
        seen.add(full)
        links.append(full)
        if len(links) >= max_links:
            break
    return links


def new_custom_site_id() -> str:
    import time

    return f"custom_{int(time.time() * 1000):x}"
