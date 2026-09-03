"""Readonly money-path surface sweep → silent-fail verdicts + vault health file.

Public HTTP checks only (island /health, loot CTA, optional Gumroad URL, optional
click beacon). No Start bots, no .env writes, no LV retarget.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_MONOREPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_VAULT = _MONOREPO_ROOT / "llm-rag" / "knowledge" / "notes"
_HEALTH_REL = Path("3-Resources") / "Revenue" / "money-path-health.md"
_DEFAULT_HEALTH_URL = "https://api.powercore.app/health"
_DEFAULT_BEACON_BASE = "https://api.powercore.app"
# Documented live loot gate beacon (GATE_LINK_AUDIT / WK31_BEACON_PASTE). Set
# TBCC_MONEY_PATH_BEACON_SLUG=0 to skip all beacon rows. Prefer
# TBCC_MONEY_PATH_BEACON_SLUGS for an explicit CSV list.
_DEFAULT_BEACON_WEEK = "wk31"
_DEFAULT_BEACON_KEYS = (
    "loot",
    "lootgod",
    "mainhub",
    "main_group",
    "packs",
    "abg",
    "ai",
    "ass",
    "big_tits",
    "blowjob",
    "bop",
    "goon",
    "milf",
    "taboo",
    "voyeur",
)
_DEFAULT_BEACON_SLUG = f"{_DEFAULT_BEACON_WEEK}-lv-loot"
# click_only gates redirect straight to a channel/addlist link with no bot deep-link to
# attribute through, so they never carry ?start= — GATE_LINK_AUDIT.md "Gate classes".
_CLICK_ONLY_BEACON_KEYS = frozenset({"mainhub", "addlist"})

# Lower index = worse (for aggregate).
_VERDICT_RANK = {
    "never_seen": 0,
    "stale": 1,
    "blocked": 2,
    "ok": 3,
    "idle": 4,
}


@dataclass(frozen=True)
class HttpFetchResult:
    status_code: int
    body: str
    error: str | None = None
    final_url: str | None = None


def vault_notes_root() -> Path:
    raw = (os.getenv("TBCC_VAULT_NOTES_PATH") or os.getenv("OBSIDIAN_VAULT_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_VAULT.resolve()


def money_path_health_path() -> Path:
    override = (os.getenv("TBCC_MONEY_PATH_HEALTH_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (vault_notes_root() / _HEALTH_REL).resolve()


def worst_verdict(verdicts: list[str]) -> str:
    if not verdicts:
        return "blocked"
    return min(verdicts, key=lambda v: _VERDICT_RANK.get(str(v), 9))


def fetch_url(url: str, *, timeout: float = 15.0) -> HttpFetchResult:
    """Readonly GET with redirects followed (island health, CTAs)."""
    return fetch_url_ex(url, timeout=timeout, follow_redirects=True)


def fetch_url_ex(
    url: str,
    *,
    timeout: float = 15.0,
    follow_redirects: bool = True,
) -> HttpFetchResult:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "TBCC-money-path-health/1.0"},
    )
    try:
        if follow_redirects:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(8192)
                body = raw.decode("utf-8", errors="replace")
                return HttpFetchResult(
                    status_code=int(resp.status),
                    body=body,
                    final_url=str(resp.geturl() or url),
                )
        # No redirects: treat HTTPError 3xx as success for beacon probes.
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
                return None

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read(8192)
                body = raw.decode("utf-8", errors="replace")
                return HttpFetchResult(
                    status_code=int(resp.status),
                    body=body,
                    final_url=str(resp.geturl() or url),
                )
        except urllib.error.HTTPError as e:
            if 300 <= int(e.code) < 400:
                loc = e.headers.get("Location") if e.headers else None
                return HttpFetchResult(
                    status_code=int(e.code),
                    body="",
                    final_url=loc,
                )
            body = ""
            try:
                body = e.read(2048).decode("utf-8", errors="replace")
            except Exception:
                pass
            return HttpFetchResult(status_code=int(e.code), body=body, error=str(e)[:200])
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(2048).decode("utf-8", errors="replace")
        except Exception:
            pass
        return HttpFetchResult(status_code=int(e.code), body=body, error=str(e)[:200])
    except Exception as e:
        logger.debug("money_path fetch failed url=%s", url, exc_info=True)
        return HttpFetchResult(status_code=0, body="", error=str(e)[:300])


def _island_health_url() -> str:
    return (os.getenv("TBCC_MONEY_PATH_HEALTH_URL") or _DEFAULT_HEALTH_URL).strip()


def _beacon_slugs() -> list[str]:
    """Resolve beacon slugs for the money-path HTTP sweep."""
    raw_single = os.getenv("TBCC_MONEY_PATH_BEACON_SLUG")
    if raw_single is not None:
        slug = raw_single.strip().strip("/")
        if not slug or slug.lower() in ("0", "off", "false", "no", "none", "idle"):
            return []
        # Explicit single slug still wins when SLUGS is unset.
        raw_multi = (os.getenv("TBCC_MONEY_PATH_BEACON_SLUGS") or "").strip()
        if not raw_multi:
            return [slug]

    raw_multi = (os.getenv("TBCC_MONEY_PATH_BEACON_SLUGS") or "").strip()
    if raw_multi:
        if raw_multi.lower() in ("0", "off", "false", "no", "none", "idle"):
            return []
        out: list[str] = []
        for part in raw_multi.split(","):
            s = part.strip().strip("/")
            if s and s not in out:
                out.append(s)
        return out

    week = (os.getenv("TBCC_MONEY_PATH_BEACON_WEEK") or _DEFAULT_BEACON_WEEK).strip() or _DEFAULT_BEACON_WEEK
    return [f"{week}-lv-{key}" for key in _DEFAULT_BEACON_KEYS]


def _beacon_slug() -> str | None:
    slugs = _beacon_slugs()
    return slugs[0] if slugs else None


def _beacon_url() -> str | None:
    slug = _beacon_slug()
    if not slug:
        return None
    base = (os.getenv("TBCC_CLICK_BEACON_PUBLIC_BASE") or _DEFAULT_BEACON_BASE).strip().rstrip("/")
    return f"{base}/r/{slug}"


def _beacon_expects_start_payload(slug: str) -> bool:
    """Full-attribution LV gates carry ?start=src_lv_<lane>_<wk>; click_only gates
    (mainhub, addlist) do not — a missing ?start= there is not a stale signal."""
    if "-lv-" not in slug:
        return False
    key = slug.rsplit("-lv-", 1)[-1].strip().lower()
    return key not in _CLICK_ONLY_BEACON_KEYS


def _beacon_urls() -> list[tuple[str, str]]:
    base = (os.getenv("TBCC_CLICK_BEACON_PUBLIC_BASE") or _DEFAULT_BEACON_BASE).strip().rstrip("/")
    return [(slug, f"{base}/r/{slug}") for slug in _beacon_slugs()]


def _check_island_health() -> dict[str, Any]:
    url = _island_health_url()
    row: dict[str, Any] = {
        "id": "island_api_health",
        "url": url,
        "stop_kind": "http",
    }
    result = fetch_url(url)
    if result.error and result.status_code == 0:
        row["verdict"] = "blocked"
        row["stop_evidence"] = result.error
        return row
    if result.status_code < 200 or result.status_code >= 300:
        row["verdict"] = "stale"
        row["stop_evidence"] = f"http={result.status_code}"
        return row
    try:
        data = json.loads(result.body or "{}")
    except json.JSONDecodeError:
        row["verdict"] = "stale"
        row["stop_evidence"] = "non-json health body"
        return row
    status = str(data.get("status") or "").strip().lower()
    crypto = data.get("crypto_auto_checkout")
    epo = data.get("external_payment_orders_impl")
    evidence = f"status={status!r} crypto_auto_checkout={crypto!r} epo={epo!r}"
    row["stop_evidence"] = evidence
    if status != "ok":
        row["verdict"] = "stale"
        return row
    row["verdict"] = "ok"
    row["health_fields"] = {
        "status": status,
        "crypto_auto_checkout": crypto,
        "external_payment_orders_impl": epo,
    }
    return row


def _check_http_surface(
    *,
    surface_id: str,
    url: str,
    ok_statuses: frozenset[int],
    follow_redirects: bool = True,
    expect_start_payload: bool = False,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": surface_id,
        "url": _safe_url_for_log(url),
        "stop_kind": "http",
    }
    result = fetch_url_ex(url, follow_redirects=follow_redirects)
    if result.error and result.status_code == 0:
        row["verdict"] = "blocked"
        row["stop_evidence"] = result.error
        return row
    code = int(result.status_code)
    row["stop_evidence"] = f"http={code}"
    loc = result.final_url or ""
    if loc and loc != url:
        row["stop_evidence"] += f" loc={_safe_url_for_log(loc)}"
    if code in ok_statuses:
        row["verdict"] = "ok"
        if expect_start_payload and loc:
            low = loc.lower()
            if "start=" not in low and "start%3d" not in low:
                row["verdict"] = "stale"
                row["stop_evidence"] += " missing_start_payload"
                row["destination_audit"] = "no_start"
            else:
                row["destination_audit"] = "has_start"
    else:
        row["verdict"] = "stale"
    return row


def _safe_url_for_log(url: str) -> str:
    """Drop query string so tbcc_ref / tokens never land in vault files."""
    u = urlparse((url or "").strip())
    if not u.scheme or not u.netloc:
        return (url or "")[:120]
    return f"{u.scheme}://{u.netloc}{u.path}"


def _friction_hypotheses(surfaces: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    by_id = {str(s.get("id")): s for s in surfaces}
    health = by_id.get("island_api_health") or {}
    if health.get("verdict") not in ("ok", "idle"):
        out.append(
            "Island /health is not cleanly ok — checkout and fulfillment may look dead "
            "even when CTAs still resolve."
        )
    loot = by_id.get("loot_public_cta") or {}
    if loot.get("verdict") not in ("ok", "idle"):
        out.append(
            "Public loot CTA (telegram.me loot bot) failed HTTP check — top-of-funnel "
            "Buffer/X and hub links may send buyers nowhere."
        )
    gum = by_id.get("gumroad_default") or {}
    if gum.get("verdict") == "idle":
        out.append(
            "Gumroad default product URL unset (TBCC_GUMROAD_PRODUCT_URL) — fiat VIP "
            "CTA cannot be verified from this workstation."
        )
    elif gum.get("verdict") not in ("ok",):
        out.append(
            "Gumroad product URL returned non-OK — card checkout CTA may be broken "
            "while Stars/crypto still appear live."
        )
    beacon = by_id.get("click_beacon") or {}
    beacon_rows = [
        s
        for s in surfaces
        if str(s.get("id") or "") == "click_beacon"
        or str(s.get("id") or "").startswith("click_beacon:")
    ]
    if any(r.get("verdict") not in ("ok", "idle") for r in beacon_rows):
        missing_start = [
            r
            for r in beacon_rows
            if r.get("destination_audit") == "no_start"
            or "missing_start_payload" in str(r.get("stop_evidence") or "")
        ]
        if missing_start:
            out.append(
                f"{len(missing_start)} LV beacon(s) 3xx without ?start= on Location — "
                "explains src_lv_* clicks_without_touches (destination audit)."
            )
        else:
            out.append(
                "One or more click beacons failed HTTP check — attribution /r/{slug} may be "
                "dead for the configured TBCC_MONEY_PATH_BEACON_SLUG(S)."
            )
    elif beacon.get("verdict") not in ("ok", "idle") and not beacon_rows:
        out.append(
            "Click beacon slug did not 3xx — attribution /r/{slug} may be dead for the "
            "configured TBCC_MONEY_PATH_BEACON_SLUG."
        )
    if not out:
        out.append(
            "All configured money-path surfaces returned ok/idle — next leverage is "
            "conversion copy/SKU (see revenue thinktank), not link repair."
        )
    return out[:5]


def format_money_path_health_markdown(payload: dict[str, Any]) -> str:
    generated = str(payload.get("generated_at") or _now_iso())
    verdict = str(payload.get("verdict") or "blocked")
    lines = [
        "---",
        "type: money-path-health",
        f"created: {generated}",
        "source: tbcc-money-path-health",
        "suggested: true",
        "tags:",
        "  - tbcc",
        "  - money-path",
        "  - health",
        "  - revenue",
        "---",
        "",
        f"# Money-path health — {generated[:10]}",
        "",
        f"**Aggregate verdict:** `{verdict}`",
        "",
        "Readonly HTTP sweep of customer-facing payment/CTA surfaces. "
        "Corpus / revenue thinktank may cite this file when proposing revenue moves.",
        "",
        "## Sweep",
        "",
        "| Surface | Verdict | URL | Evidence |",
        "|---------|---------|-----|----------|",
    ]
    for s in payload.get("surfaces") or []:
        sid = str(s.get("id") or "")
        sv = str(s.get("verdict") or "")
        url = str(s.get("url") or "—")
        ev = str(s.get("stop_evidence") or s.get("error") or "—").replace("|", "/")
        lines.append(f"| `{sid}` | `{sv}` | `{url}` | {ev} |")
    lines.extend(["", "## Friction hypotheses", ""])
    for h in payload.get("friction_hypotheses") or []:
        lines.append(f"- {h}")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- No Start bots; no `.env` edits; LV destinations not retargeted.",
            "- Gumroad stays `idle` when product URL unset; beacons default to "
            "`wk31-lv-{loot,lootgod,mainhub,main_group,packs}` "
            "(set `TBCC_MONEY_PATH_BEACON_SLUG=0` to skip; or CSV via "
            "`TBCC_MONEY_PATH_BEACON_SLUGS`).",
            "- Re-run: `cd tbcc/backend && py -3.13 scripts/silent_fail_probe.py money-path`",
            "",
        ]
    )
    return "\n".join(lines)


def write_money_path_health_vault(payload: dict[str, Any]) -> dict[str, Any]:
    path = money_path_health_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = format_money_path_health_markdown(payload)
    path.write_text(body, encoding="utf-8")
    return {"ok": True, "path": str(path), "bytes": len(body.encode("utf-8"))}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def probe_money_path(*, write_vault: bool = True) -> dict[str, Any]:
    """Sweep money-path surfaces; optionally overwrite vault health markdown."""
    surfaces: list[dict[str, Any]] = [_check_island_health()]

    from app.services.aof_social_links import loot_public_cta_url

    loot_url = loot_public_cta_url()
    if loot_url:
        surfaces.append(
            _check_http_surface(
                surface_id="loot_public_cta",
                url=loot_url,
                ok_statuses=frozenset(range(200, 300)),
            )
        )
    else:
        surfaces.append(
            {
                "id": "loot_public_cta",
                "verdict": "idle",
                "url": "",
                "stop_kind": "http",
                "stop_evidence": "loot CTA URL empty",
            }
        )

    from app.services.gumroad_ping import gumroad_default_product_url

    gum_url = gumroad_default_product_url()
    if gum_url.startswith("https://"):
        surfaces.append(
            _check_http_surface(
                surface_id="gumroad_default",
                url=gum_url,
                ok_statuses=frozenset(range(200, 300)),
            )
        )
    else:
        surfaces.append(
            {
                "id": "gumroad_default",
                "verdict": "idle",
                "url": "",
                "stop_kind": "http",
                "stop_evidence": "TBCC_GUMROAD_PRODUCT_URL unset",
            }
        )

    beacon_pairs = _beacon_urls()
    if beacon_pairs:
        for slug, url in beacon_pairs:
            surfaces.append(
                _check_http_surface(
                    surface_id=f"click_beacon:{slug}",
                    url=url,
                    ok_statuses=frozenset(range(300, 400)),
                    follow_redirects=False,
                    expect_start_payload=_beacon_expects_start_payload(slug),
                )
            )
    else:
        surfaces.append(
            {
                "id": "click_beacon",
                "verdict": "idle",
                "url": "",
                "stop_kind": "http",
                "stop_evidence": "beacon disabled (TBCC_MONEY_PATH_BEACON_SLUG=0)",
            }
        )

    # Idle surfaces do not drag aggregate down when others are ok.
    active = [str(s.get("verdict")) for s in surfaces if s.get("verdict") != "idle"]
    if not active:
        verdict = "idle"
    else:
        verdict = worst_verdict(active)

    friction = _friction_hypotheses(surfaces)
    payload: dict[str, Any] = {
        "id": "money_path",
        "verdict": verdict,
        "enabled": True,
        "generated_at": _now_iso(),
        "surfaces": surfaces,
        "friction_hypotheses": friction,
        "stop_kind": "http",
        "stop_evidence": "; ".join(
            f"{s.get('id')}={s.get('verdict')}" for s in surfaces
        ),
    }

    if write_vault:
        try:
            payload["vault_export"] = write_money_path_health_vault(payload)
        except Exception as e:
            logger.warning("money_path vault write failed: %s", e)
            payload["vault_export"] = {"ok": False, "error": str(e)[:300]}
            if payload["verdict"] == "ok":
                payload["verdict"] = "blocked"

    return payload
