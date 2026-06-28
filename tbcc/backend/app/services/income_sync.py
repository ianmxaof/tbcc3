"""External income sync — Linkvertise, AdMaven, Work.ink, BMC, affiliate registry."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services.income_ledger import (
    SOURCE_ADMAVEN,
    SOURCE_AFFILIATE,
    SOURCE_BMC,
    SOURCE_LINKVERTISE,
    SOURCE_WORKINK,
    record_cumulative_sync_delta,
)

logger = logging.getLogger(__name__)

_DOLLAR_RE = re.compile(
    r"(?:total|balance|earnings|revenue|paid|available)[^\$]{0,40}\$\s*([\d,]+(?:\.\d{1,2})?)|"
    r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*(?:total|earned|balance|available)",
    re.IGNORECASE,
)
_ANY_DOLLAR_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")

_BMC_API = "https://developers.buymeacoffee.com/api/v1"


def _cookie_header(env_key: str, file_key: str) -> str | None:
    raw = (os.getenv(env_key) or "").strip()
    if raw:
        return raw
    path = (os.getenv(file_key) or "").strip()
    if path and os.path.isfile(path):
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    return None


def _parse_dollar_candidates(text: str) -> list[float]:
    vals: list[float] = []
    for m in _DOLLAR_RE.finditer(text or ""):
        g = m.group(1) or m.group(2)
        if not g:
            continue
        try:
            vals.append(float(g.replace(",", "")))
        except ValueError:
            continue
    if not vals:
        for m in _ANY_DOLLAR_RE.finditer(text or ""):
            try:
                vals.append(float(m.group(1).replace(",", "")))
            except ValueError:
                continue
    return vals


def _pick_likely_total(amounts: list[float]) -> float | None:
    if not amounts:
        return None
    # Prefer the largest plausible dashboard total (exclude tiny ad CPM noise).
    big = [a for a in amounts if a >= 0.5]
    pool = big if big else amounts
    return max(pool)


def _fetch_page_text(url: str, *, cookie: str | None = None, timeout: float = 45.0) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    if cookie:
        headers["Cookie"] = cookie
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        return r.text


def _scrape_url_total(url: str, *, cookie: str | None = None) -> dict[str, Any]:
    if not url:
        return {"ok": False, "error": "missing_url"}
    try:
        html = _fetch_page_text(url, cookie=cookie)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    # Strip tags loosely for regex scan.
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    amounts = _parse_dollar_candidates(text)
    total = _pick_likely_total(amounts)
    if total is None:
        return {"ok": False, "error": "no_dollar_amount_found", "candidates": amounts[:12]}
    return {"ok": True, "total_usd": round(total, 2), "candidates": amounts[:12]}


def sync_linkvertise_income(db: Session, *, headed: bool = False) -> dict[str, Any]:
    """Scrape Linkvertise publisher dashboard cumulative earnings (Playwright)."""
    from app.services.linkvertise_dashboard_provision import (
        auth_state_path,
        load_flow_config,
        open_playwright_session,
        _dismiss_banners,
        _looks_logged_in,
    )

    stats_url = (
        (os.getenv("TBCC_LINKVERTISE_EARNINGS_URL") or "").strip()
        or "https://publisher.linkvertise.com/dashboard"
    )
    auth_path = auth_state_path()
    if not auth_path.is_file() and not headed:
        return {
            "ok": False,
            "source": SOURCE_LINKVERTISE,
            "error": "missing_linkvertise_auth",
            "hint": "Run: py scripts/provision_linkvertise_dashboard_links.py --login (headed), then retry sync",
        }

    cfg = load_flow_config()
    try:
        handle = open_playwright_session(
            headed=headed,
            slow_mo=30,
            storage_state=auth_path if auth_path.is_file() else None,
        )
        try:
            page = handle.get_page()
            page.set_default_timeout(60000)
            page.goto(stats_url, wait_until="domcontentloaded", timeout=120000)
            _dismiss_banners(page)
            if not _looks_logged_in(page, cfg):
                if not headed:
                    return {
                        "ok": False,
                        "source": SOURCE_LINKVERTISE,
                        "error": "not_logged_in",
                        "hint": "py scripts/tbcc_cli.py income sync --headed (log in when Brave opens)",
                    }
                from app.services.linkvertise_dashboard_provision import _ensure_logged_in

                _ensure_logged_in(page, cfg, headed=True)
            text = page.inner_text("body")
            amounts = _parse_dollar_candidates(text)
            total = _pick_likely_total(amounts)
            if total is None:
                return {
                    "ok": False,
                    "source": SOURCE_LINKVERTISE,
                    "error": "no_dollar_amount_found",
                    "hint": f"Set TBCC_LINKVERTISE_EARNINGS_URL to your stats page (currently {stats_url})",
                }
            result = record_cumulative_sync_delta(
                db,
                SOURCE_LINKVERTISE,
                total,
                source_label="Linkvertise gates",
                sync_kind="playwright_scrape",
                raw={"url": stats_url, "candidates": amounts[:12]},
            )
            result["source"] = SOURCE_LINKVERTISE
            handle.context.storage_state(path=str(auth_path))
            return result
        finally:
            handle.close()
    except Exception as e:
        logger.warning("linkvertise income sync failed: %s", e)
        return {"ok": False, "source": SOURCE_LINKVERTISE, "error": str(e)}


def sync_admaven_income(db: Session) -> dict[str, Any]:
    url = (
        (os.getenv("TBCC_ADMAVEN_EARNINGS_URL") or "").strip()
        or "https://publishers.ad-maven.com/"
    )
    cookie = _cookie_header("TBCC_ADMAVEN_COOKIE", "TBCC_ADMAVEN_COOKIE_FILE")
    token = (os.getenv("TBCC_ADMAVEN_API_TOKEN") or "").strip()
    if not cookie and not token:
        return {
            "ok": False,
            "source": SOURCE_ADMAVEN,
            "error": "admaven_not_configured",
            "hint": "Export browser cookies from publishers.ad-maven.com → TBCC_ADMAVEN_COOKIE_FILE, or manual entry weekly",
        }
    scraped = _scrape_url_total(url, cookie=cookie)
    if not scraped.get("ok"):
        return {
            "ok": False,
            "source": SOURCE_ADMAVEN,
            **scraped,
            "hint": "Log into https://publishers.ad-maven.com → Statistics → copy session cookie to TBCC_ADMAVEN_COOKIE_FILE",
        }
    result = record_cumulative_sync_delta(
        db,
        SOURCE_ADMAVEN,
        float(scraped["total_usd"]),
        source_label="AdMaven",
        sync_kind="api_poll",
        raw={"url": url, **scraped},
    )
    result["source"] = SOURCE_ADMAVEN
    return result


def sync_workink_income(db: Session) -> dict[str, Any]:
    url = (
        (os.getenv("TBCC_WORKINK_EARNINGS_URL") or "").strip()
        or "https://dashboard.work.ink/"
    )
    cookie = _cookie_header("TBCC_WORKINK_COOKIE", "TBCC_WORKINK_COOKIE_FILE")
    api_key = (os.getenv("TBCC_WORKINK_API_KEY") or "").strip()
    if not cookie and not api_key:
        return {
            "ok": False,
            "source": SOURCE_WORKINK,
            "error": "workink_not_configured",
            "hint": "Log into dashboard.work.ink → export cookie to TBCC_WORKINK_COOKIE_FILE, or manual entry",
        }
    scraped = _scrape_url_total(url, cookie=cookie)
    if not scraped.get("ok"):
        return {
            "ok": False,
            "source": SOURCE_WORKINK,
            **scraped,
            "hint": "Open https://dashboard.work.ink while logged in → export cookies for scrape sync",
        }
    result = record_cumulative_sync_delta(
        db,
        SOURCE_WORKINK,
        float(scraped["total_usd"]),
        source_label="Work.ink",
        sync_kind="api_poll",
        raw={"url": url, **scraped},
    )
    result["source"] = SOURCE_WORKINK
    return result


def _bmc_paginate(path: str, token: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while page <= 50:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{_BMC_API}/{path}",
                params={"access_token": token, "page": page},
            )
            r.raise_for_status()
            payload = r.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or not data:
            break
        items.extend(data)
        if not payload.get("next_page_url"):
            break
        page += 1
    return items


def _bmc_amount(row: dict[str, Any]) -> float:
    for key in (
        "total_amount_charged",
        "amount",
        "coffee_price",
        "price",
        "support_coffee_price",
        "subscription_amount",
    ):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def sync_bmc_income(db: Session) -> dict[str, Any]:
    token = (os.getenv("TBCC_BMC_ACCESS_TOKEN") or os.getenv("TBCC_BUYMEACOFFEE_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "source": SOURCE_BMC, "error": "TBCC_BMC_ACCESS_TOKEN not set"}

    try:
        supporters = _bmc_paginate("supporters", token)
        extras = _bmc_paginate("extras", token)
        subs = _bmc_paginate("subscriptions", token)
    except Exception as e:
        return {"ok": False, "source": SOURCE_BMC, "error": str(e)}

    total = 0.0
    for bucket in (supporters, extras, subs):
        for row in bucket:
            if isinstance(row, dict):
                total += _bmc_amount(row)

    total = round(total, 2)
    result = record_cumulative_sync_delta(
        db,
        SOURCE_BMC,
        total,
        source_label="Buy Me a Coffee",
        sync_kind="api_poll",
        raw={
            "supporters": len(supporters),
            "extras": len(extras),
            "subscriptions": len(subs),
            "cumulative_usd": total,
        },
    )
    result["source"] = SOURCE_BMC
    return result


def affiliate_registry_status(db: Session) -> dict[str, Any]:
    """Affiliate programs from promo_affiliate_links + last ledger entry per link."""
    from app.models.income_entry import IncomeEntry
    from app.models.promo_affiliate_link import PromoAffiliateLink

    rows = (
        db.query(PromoAffiliateLink)
        .filter(PromoAffiliateLink.active.is_(True))
        .order_by(PromoAffiliateLink.priority_tier.asc(), PromoAffiliateLink.id.asc())
        .all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        ref = f"affiliate:{int(row.id)}"
        last = (
            db.query(IncomeEntry)
            .filter(IncomeEntry.source == SOURCE_AFFILIATE, IncomeEntry.external_ref == ref)
            .order_by(IncomeEntry.id.desc())
            .first()
        )
        items.append(
            {
                "id": int(row.id),
                "label": row.label,
                "url": row.url,
                "payout_kind": row.payout_kind,
                "last_usd_cents": int(last.amount_usd_cents) if last else 0,
                "last_earned_at": last.earned_at.isoformat() + "Z" if last and last.earned_at else None,
                "last_sync_kind": last.sync_kind if last else None,
            }
        )
    return {"ok": True, "count": len(items), "items": items}


def sync_external_income(
    db: Session,
    *,
    sources: list[str] | None = None,
    headed: bool = False,
) -> dict[str, Any]:
    """Run configured external sync adapters."""
    want = set(sources or [])
    runners: list[tuple[str, Any]] = [
        (SOURCE_LINKVERTISE, lambda: sync_linkvertise_income(db, headed=headed)),
        (SOURCE_ADMAVEN, lambda: sync_admaven_income(db)),
        (SOURCE_WORKINK, lambda: sync_workink_income(db)),
        (SOURCE_BMC, lambda: sync_bmc_income(db)),
    ]
    results: list[dict[str, Any]] = []
    for key, fn in runners:
        if want and key not in want:
            continue
        try:
            results.append(fn())
        except Exception as e:
            results.append({"ok": False, "source": key, "error": str(e)})

    registry = affiliate_registry_status(db)
    return {
        "ok": True,
        "results": results,
        "affiliate_registry": registry,
        "synced_at": datetime.utcnow().isoformat() + "Z",
    }
