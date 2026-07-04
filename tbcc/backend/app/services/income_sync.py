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
_ANY_EURO_RE = re.compile(r"€\s*([\d,]+(?:\.\d{1,2})?)")

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
    dollars, _ = _parse_amount_candidates(text)
    return dollars


def _parse_amount_candidates(text: str) -> tuple[list[float], list[float]]:
    dollars: list[float] = []
    euros: list[float] = []
    for m in _DOLLAR_RE.finditer(text or ""):
        g = m.group(1) or m.group(2)
        if not g:
            continue
        try:
            dollars.append(float(g.replace(",", "")))
        except ValueError:
            continue
    if not dollars:
        for m in _ANY_DOLLAR_RE.finditer(text or ""):
            try:
                dollars.append(float(m.group(1).replace(",", "")))
            except ValueError:
                continue
    for m in _ANY_EURO_RE.finditer(text or ""):
        try:
            euros.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    return dollars, euros


def _euro_to_usd(amount_eur: float) -> float:
    rate_raw = (os.getenv("TBCC_EUR_USD_RATE") or "1.08").strip()
    try:
        rate = float(rate_raw)
    except ValueError:
        rate = 1.08
    return round(float(amount_eur) * rate, 2)


def _pick_likely_total(amounts: list[float]) -> float | None:
    if not amounts:
        return None
    big = [a for a in amounts if a >= 0.01]
    pool = big if big else amounts
    return max(pool)


def _scrape_with_playwright(url: str, *, headed: bool = False, wait_ms: int = 5000) -> dict[str, Any]:
    if not url:
        return {"ok": False, "error": "missing_url"}
    try:
        from app.services.playwright_browser import open_playwright_session

        handle = open_playwright_session(headed=headed, slow_mo=30)
        try:
            page = handle.get_page()
            page.set_default_timeout(90000)
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(wait_ms)
            text = page.inner_text("body")
            dollars, euros = _parse_amount_candidates(text)
            if dollars:
                total = _pick_likely_total(dollars)
                if total is not None:
                    return {"ok": True, "total_usd": round(total, 2), "currency": "USD", "candidates": dollars[:12]}
            if euros:
                total_eur = _pick_likely_total(euros)
                if total_eur is not None:
                    return {
                        "ok": True,
                        "total_usd": _euro_to_usd(total_eur),
                        "total_eur": round(total_eur, 2),
                        "currency": "EUR",
                        "candidates": euros[:12],
                    }
            return {"ok": False, "error": "no_amount_found", "candidates": (dollars + euros)[:12]}
        finally:
            handle.close()
    except Exception as e:
        return {"ok": False, "error": str(e)}


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


def _scrape_url_total(
    url: str,
    *,
    cookie: str | None = None,
    headed: bool = False,
    allow_playwright: bool = True,
) -> dict[str, Any]:
    if cookie:
        try:
            html = _fetch_page_text(url, cookie=cookie)
            text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
            text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            dollars, euros = _parse_amount_candidates(text)
            if dollars:
                total = _pick_likely_total(dollars)
                if total is not None:
                    return {"ok": True, "total_usd": round(total, 2), "currency": "USD", "candidates": dollars[:12]}
            if euros:
                total_eur = _pick_likely_total(euros)
                if total_eur is not None:
                    return {
                        "ok": True,
                        "total_usd": _euro_to_usd(total_eur),
                        "total_eur": round(total_eur, 2),
                        "currency": "EUR",
                        "candidates": euros[:12],
                    }
        except Exception as e:
            if not allow_playwright and not headed:
                return {"ok": False, "error": str(e)}
    if not allow_playwright:
        return {"ok": False, "error": "no_cookie_or_playwright_disabled", "skipped": True}
    return _scrape_with_playwright(url, headed=headed)


def sync_linkvertise_income(db: Session, *, headed: bool = False, light: bool = False) -> dict[str, Any]:
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
    if light and not auth_path.is_file():
        return {
            "ok": True,
            "source": SOURCE_LINKVERTISE,
            "skipped": True,
            "reason": "no_saved_session",
        }
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


def sync_admaven_income(db: Session, *, headed: bool = False, light: bool = False) -> dict[str, Any]:
    url = (
        (os.getenv("TBCC_ADMAVEN_EARNINGS_URL") or "").strip()
        or "https://publishers.ad-maven.com/"
    )
    cookie = _cookie_header("TBCC_ADMAVEN_COOKIE", "TBCC_ADMAVEN_COOKIE_FILE")
    if light and not cookie:
        return {
            "ok": True,
            "source": SOURCE_ADMAVEN,
            "skipped": True,
            "reason": "no_cookie_configured",
        }
    scraped = _scrape_url_total(url, cookie=cookie, headed=headed, allow_playwright=not light)
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


def sync_workink_income(db: Session, *, headed: bool = False, light: bool = False) -> dict[str, Any]:
    url = (
        (os.getenv("TBCC_WORKINK_EARNINGS_URL") or "").strip()
        or "https://dashboard.work.ink/"
    )
    cookie = _cookie_header("TBCC_WORKINK_COOKIE", "TBCC_WORKINK_COOKIE_FILE")
    if light and not cookie:
        return {
            "ok": True,
            "source": SOURCE_WORKINK,
            "skipped": True,
            "reason": "no_cookie_configured",
        }
    scraped = _scrape_url_total(url, cookie=cookie, headed=headed, allow_playwright=not light)
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
    light: bool = False,
    include_registry: bool = True,
) -> dict[str, Any]:
    """Run configured external sync adapters."""
    want = set(sources or [])
    runners: list[tuple[str, Any]] = [
        (SOURCE_LINKVERTISE, lambda: sync_linkvertise_income(db, headed=headed, light=light)),
        (SOURCE_ADMAVEN, lambda: sync_admaven_income(db, headed=headed, light=light)),
        (SOURCE_WORKINK, lambda: sync_workink_income(db, headed=headed, light=light)),
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

    registry = affiliate_registry_status(db) if include_registry else None
    out: dict[str, Any] = {
        "ok": True,
        "results": results,
        "synced_at": datetime.utcnow().isoformat() + "Z",
        "light": light,
    }
    if registry is not None:
        out["affiliate_registry"] = registry
    return out


REDIS_INCOME_LAST_POLL = "tbcc:income:last_poll"


def income_poll_enabled() -> bool:
    return (os.getenv("TBCC_INCOME_POLL_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def income_poll_interval_hours() -> int:
    raw = (os.getenv("TBCC_INCOME_POLL_HOURS") or "6").strip()
    try:
        return max(1, min(168, int(raw)))
    except ValueError:
        return 6


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def save_income_poll_status(payload: dict[str, Any]) -> None:
    try:
        r = _redis_client()
        r.set(REDIS_INCOME_LAST_POLL, json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        logger.debug("income poll redis save: %s", e)


def get_income_poll_status() -> dict[str, Any]:
    out: dict[str, Any] = {
        "enabled": income_poll_enabled(),
        "interval_hours": income_poll_interval_hours(),
        "last_poll_at": None,
        "last_poll_ok": None,
        "last_results": [],
        "beat_task": "app.workers.income_poll_worker.poll_income_sources",
    }
    try:
        r = _redis_client()
        raw = r.get(REDIS_INCOME_LAST_POLL)
        if raw:
            data = json.loads(raw)
            if isinstance(data, dict):
                out.update(data)
    except Exception as e:
        out["redis_error"] = str(e)
    return out


def run_income_poll(db: Session, *, light: bool = True) -> dict[str, Any]:
    """
    Background-safe income refresh: idempotent subscription backfill + external delta sync.
    Light mode skips headed Playwright and Brave profile launch (cookie/API only).
    """
    from app.services.income_ledger import backfill_subscription_income, income_summary

    backfill: dict[str, Any]
    try:
        backfill = backfill_subscription_income(db)
    except Exception as e:
        logger.warning("income poll backfill skipped: %s", e)
        backfill = {"ok": False, "error": str(e)}
    external = sync_external_income(db, light=light, include_registry=False)
    try:
        summary = income_summary(db, backfill=False)
    except Exception as e:
        logger.warning("income poll summary skipped: %s", e)
        summary = {"ok": False, "error": str(e)}

    payload = {
        "ok": True,
        "polled_at": datetime.utcnow().isoformat() + "Z",
        "light": light,
        "backfill": backfill,
        "external": external,
        "totals": summary.get("totals"),
        "last_poll_at": datetime.utcnow().isoformat() + "Z",
        "last_poll_ok": True,
        "last_results": external.get("results") or [],
        "interval_hours": income_poll_interval_hours(),
    }
    save_income_poll_status(payload)
    return payload
