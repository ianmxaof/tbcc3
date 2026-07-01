"""GA4 Data API — AllMyLinks hub clicks by UTM (optional service account)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def ga4_enabled() -> bool:
    return (os.getenv("TBCC_GA4_DATA_API_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def ga4_property_id() -> str:
    return (os.getenv("TBCC_GA4_PROPERTY_ID") or "").strip()


def ga4_credentials_path() -> str:
    return (os.getenv("TBCC_GA4_CREDENTIALS_JSON") or "").strip()


def ga4_configured() -> bool:
    if not ga4_enabled():
        return False
    pid = ga4_property_id()
    cred = ga4_credentials_path()
    return bool(pid and cred and os.path.isfile(cred))


def ga4_lookback_days() -> int:
    raw = (os.getenv("TBCC_GA4_LOOKBACK_DAYS") or "7").strip()
    try:
        return max(1, min(30, int(raw)))
    except ValueError:
        return 7


def ga4_status() -> dict[str, Any]:
    from app.services.utm_links import ga4_measurement_id

    return {
        "enabled": ga4_enabled(),
        "configured": ga4_configured(),
        "property_id": ga4_property_id() or None,
        "measurement_id": ga4_measurement_id() or None,
        "credentials_path": ga4_credentials_path() or None,
        "lookback_days": ga4_lookback_days(),
    }


def _run_report(*, dimensions: list[str], metrics: list[str], days: int) -> list[dict[str, str]]:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
    from google.oauth2 import service_account

    cred_path = ga4_credentials_path()
    creds = service_account.Credentials.from_service_account_file(
        cred_path,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    client = BetaAnalyticsDataClient(credentials=creds)
    end = datetime.utcnow().date()
    start = end - timedelta(days=max(1, days))
    request = RunReportRequest(
        property=f"properties/{ga4_property_id()}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        limit=50,
    )
    response = client.run_report(request)
    rows: list[dict[str, str]] = []
    dim_names = [d.name for d in dimensions]
    metric_names = [m.name for m in metrics]
    for row in response.rows:
        item: dict[str, str] = {}
        for i, name in enumerate(dim_names):
            item[name] = row.dimension_values[i].value
        for i, name in enumerate(metric_names):
            item[name] = row.metric_values[i].value
        rows.append(item)
    return rows


def fetch_utm_session_report(*, days: int | None = None) -> dict[str, Any]:
    """
    Sessions + active users grouped by utm_source / utm_medium / utm_campaign.
    Requires TBCC_GA4_PROPERTY_ID + TBCC_GA4_CREDENTIALS_JSON (service account with GA4 Viewer).
    """
    days = days or ga4_lookback_days()
    if not ga4_configured():
        return {"ok": False, "configured": False, "rows": []}

    try:
        rows = _run_report(
            dimensions=["sessionSource", "sessionMedium", "sessionCampaignName"],
            metrics=["sessions", "activeUsers"],
            days=days,
        )
    except ImportError:
        return {
            "ok": False,
            "configured": True,
            "error": "google_analytics_data_not_installed",
            "rows": [],
        }
    except Exception as e:
        logger.warning("GA4 hub report failed: %s", e)
        return {"ok": False, "configured": True, "error": str(e), "rows": []}

    parsed: list[dict[str, Any]] = []
    for row in rows:
        try:
            sessions = int(row.get("sessions") or 0)
        except ValueError:
            sessions = 0
        try:
            users = int(row.get("activeUsers") or 0)
        except ValueError:
            users = 0
        if sessions <= 0 and users <= 0:
            continue
        parsed.append(
            {
                "utm_source": row.get("sessionSource") or "(not set)",
                "utm_medium": row.get("sessionMedium") or "(not set)",
                "utm_campaign": row.get("sessionCampaignName") or "(not set)",
                "sessions": sessions,
                "active_users": users,
            }
        )
    parsed.sort(key=lambda x: (-int(x["sessions"]), -int(x["active_users"])))
    return {
        "ok": True,
        "configured": True,
        "lookback_days": days,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "rows": parsed,
    }


def hub_traffic_signals(*, days: int | None = None) -> list[dict[str, Any]]:
    """Convert GA4 UTM rows into content_signals-compatible signal dicts."""
    report = fetch_utm_session_report(days=days)
    if not report.get("ok"):
        return []

    out: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        sessions = int(row.get("sessions") or 0)
        if sessions < 2:
            continue
        src = str(row.get("utm_source") or "")
        med = str(row.get("utm_medium") or "")
        camp = str(row.get("utm_campaign") or "")
        strength = min(1.0, round(sessions / 20.0, 3))
        conf = "high" if sessions >= 10 else "medium" if sessions >= 5 else "low"
        out.append(
            {
                "signal_type": "hub_web_traffic",
                "strength": strength,
                "confidence": conf,
                "utm_source": src,
                "utm_medium": med,
                "utm_campaign": camp,
                "sessions": sessions,
                "active_users": int(row.get("active_users") or 0),
                "recommendation": (
                    f"AllMyLinks hub: {sessions} sessions from {src}/{med}/{camp} "
                    f"({report.get('lookback_days')}d) — double down on this surface."
                ),
            }
        )
    out.sort(key=lambda x: (-float(x["strength"]), -int(x["sessions"])))
    return out[:8]


def fetch_device_country_report(*, days: int | None = None) -> dict[str, Any]:
    """Sessions grouped by deviceCategory and country (GA4 dimensions)."""
    days = days or ga4_lookback_days()
    if not ga4_configured():
        return {"ok": False, "configured": False, "rows": []}

    try:
        rows = _run_report(
            dimensions=["deviceCategory", "country"],
            metrics=["sessions", "activeUsers"],
            days=days,
        )
    except ImportError:
        return {
            "ok": False,
            "configured": True,
            "error": "google_analytics_data_not_installed",
            "rows": [],
        }
    except Exception as e:
        logger.warning("GA4 device/country report failed: %s", e)
        return {"ok": False, "configured": True, "error": str(e), "rows": []}

    parsed: list[dict[str, Any]] = []
    for row in rows:
        try:
            sessions = int(row.get("sessions") or 0)
        except ValueError:
            sessions = 0
        if sessions <= 0:
            continue
        parsed.append(
            {
                "device_category": row.get("deviceCategory") or "(not set)",
                "country": row.get("country") or "(not set)",
                "sessions": sessions,
                "active_users": int(row.get("activeUsers") or 0),
            }
        )
    parsed.sort(key=lambda x: -int(x["sessions"]))
    return {
        "ok": True,
        "configured": True,
        "lookback_days": days,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "rows": parsed,
    }


def _aggregate_dimension(rows: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    totals: dict[str, int] = {}
    for row in rows:
        k = str(row.get(key) or "(not set)")
        totals[k] = totals.get(k, 0) + int(row.get("sessions") or 0)
    out = [{"key": k, "sessions": v} for k, v in totals.items()]
    out.sort(key=lambda x: -x["sessions"])
    return out


def hub_device_signals(*, days: int | None = None) -> list[dict[str, Any]]:
    """Mobile/desktop bias from GA4 deviceCategory."""
    report = fetch_device_country_report(days=days)
    if not report.get("ok"):
        return []

    by_device = _aggregate_dimension(report.get("rows") or [], key="device_category")
    if not by_device:
        return []

    total = sum(d["sessions"] for d in by_device)
    mobile = next((d for d in by_device if d["key"].lower() == "mobile"), None)
    if not mobile or total <= 0:
        return []

    mobile_share = mobile["sessions"] / total
    if mobile_share < 0.55:
        return []

    strength = min(1.0, round(mobile_share, 3))
    conf = "high" if mobile_share >= 0.7 else "medium"
    return [
        {
            "signal_type": "hub_mobile_bias",
            "strength": strength,
            "confidence": conf,
            "mobile_session_share": round(mobile_share, 3),
            "sessions": mobile["sessions"],
            "total_sessions": total,
            "recommendation": (
                f"AllMyLinks hub: {mobile_share:.0%} mobile sessions ({report.get('lookback_days')}d) "
                f"— bias media-heavy surfaces (IG carousel, short video) on hub exits."
            ),
        }
    ]


def hub_geo_signals(*, days: int | None = None, top_n: int = 3) -> list[dict[str, Any]]:
    """Top geo clusters from GA4 country dimension."""
    report = fetch_device_country_report(days=days)
    if not report.get("ok"):
        return []

    by_country = _aggregate_dimension(report.get("rows") or [], key="country")
    if not by_country:
        return []

    total = sum(d["sessions"] for d in by_country)
    out: list[dict[str, Any]] = []
    for row in by_country[:top_n]:
        sessions = int(row["sessions"])
        if sessions < 3:
            continue
        share = sessions / total if total else 0
        strength = min(1.0, round(sessions / max(total * 0.5, 1), 3))
        out.append(
            {
                "signal_type": "hub_geo_skew",
                "strength": strength,
                "confidence": "high" if share >= 0.35 else "medium" if share >= 0.2 else "low",
                "country": row["key"],
                "sessions": sessions,
                "session_share": round(share, 3),
                "recommendation": (
                    f"Hub traffic skew: {row['key']} = {sessions} sessions ({share:.0%} of {total} "
                    f"over {report.get('lookback_days')}d) — tune checkout/copy for this geo cluster."
                ),
            }
        )
    return out
