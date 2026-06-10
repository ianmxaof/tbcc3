"""
My.JDownloader API bridge (optional). Uses myjdapi when TBCC_MYJD_* env is set.

Does not replace TBCC-only flows (OnlyFans harvest, Perchance data: URLs, Telegram send).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_SESSION: Any | None = None
_DEVICE: Any | None = None


@dataclass
class MyJdResolvedItem:
    url: str
    name: str | None = None
    availability: str | None = None
    bytes_total: int | None = None


def myjd_enabled() -> bool:
    if (os.environ.get("TBCC_MYJD_ENABLED") or "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool((os.environ.get("TBCC_MYJD_EMAIL") or "").strip() and (os.environ.get("TBCC_MYJD_PASSWORD") or "").strip())


def myjd_device_name() -> str:
    return (os.environ.get("TBCC_MYJD_DEVICE_NAME") or "").strip()


def myjd_poll_timeout_s() -> float:
    try:
        return max(10.0, float(os.environ.get("TBCC_MYJD_POLL_TIMEOUT_S") or "120"))
    except ValueError:
        return 120.0


def myjd_request_timeout_s() -> float:
    """Hard cap for any single MyJD API round-trip (connect + add_links / resolve)."""
    try:
        return max(5.0, float(os.environ.get("TBCC_MYJD_REQUEST_TIMEOUT_S") or "45"))
    except ValueError:
        return 45.0


def myjd_max_links_per_batch() -> int:
    try:
        return max(1, min(200, int(os.environ.get("TBCC_MYJD_MAX_LINKS_PER_BATCH") or "40")))
    except ValueError:
        return 40


def myjd_async_min_links() -> int:
    try:
        return max(1, int(os.environ.get("TBCC_MYJD_ASYNC_MIN_LINKS") or "12"))
    except ValueError:
        return 12


def myjd_prefer_async() -> bool:
    return (os.environ.get("TBCC_MYJD_ASYNC") or "").strip().lower() in ("1", "true", "yes", "on")


def count_link_lines(links: str) -> int:
    return len(_split_link_lines(links))


def _split_link_lines(links: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in (links or "").splitlines():
        u = raw.strip()
        if not u or not u.startswith(("http://", "https://")):
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _format_myjd_device_list(devices: list[dict[str, Any]]) -> str:
    names = [str(d.get("name") or "").strip() for d in devices if d.get("name")]
    return ", ".join(repr(n) for n in names) if names else "(none)"


def _pick_jd_device(jd: Any, preferred_name: str | None) -> Any:
    """Resolve a Jddevice handle; preferred_name must match My.JDownloader device list (or leave empty)."""
    devices: list[dict[str, Any]] = list(jd.list_devices() or [])
    if not devices:
        raise RuntimeError(
            "No JDownloader devices linked to this My.JDownloader account. "
            "Open JDownloader on your PC, enable My.JDownloader, and wait until it shows online."
        )
    if preferred_name:
        pref = preferred_name.strip()
        for d in devices:
            dn = str(d.get("name") or "")
            if dn == pref or dn.lower() == pref.lower():
                dev = jd.get_device(device_name=dn)
                if dev is not None:
                    return dev
        raise RuntimeError(
            f"TBCC_MYJD_DEVICE_NAME={pref!r} not found. Available devices: {_format_myjd_device_list(devices)}. "
            "Copy the exact name into tbcc/.env or clear TBCC_MYJD_DEVICE_NAME to use the first device."
        )
    dev = jd.get_device()
    if dev is not None:
        return dev
    first = str(devices[0].get("name") or "").strip()
    if first:
        dev = jd.get_device(device_name=first)
        if dev is not None:
            return dev
    raise RuntimeError(f"Could not open a JDownloader device. Listed: {_format_myjd_device_list(devices)}")


def _connect_sync() -> tuple[Any, Any]:
    global _SESSION, _DEVICE
    if _SESSION is not None and _DEVICE is not None:
        return _SESSION, _DEVICE
    try:
        import myjdapi
    except ImportError as e:
        raise RuntimeError("myjdapi is not installed (pip install myjdapi)") from e

    email = (os.environ.get("TBCC_MYJD_EMAIL") or "").strip().lower()
    password = (os.environ.get("TBCC_MYJD_PASSWORD") or "").strip()
    if not email or not password:
        raise RuntimeError("Set TBCC_MYJD_EMAIL and TBCC_MYJD_PASSWORD in tbcc/.env")

    jd = myjdapi.Myjdapi()
    jd.connect(email, password)
    jd.update_devices()
    _SESSION = jd
    _DEVICE = _pick_jd_device(jd, myjd_device_name() or None)
    logger.info("My.JDownloader connected device=%s", getattr(_DEVICE, "name", "?"))
    return _SESSION, _DEVICE


def _disconnect_sync() -> None:
    global _SESSION, _DEVICE
    try:
        if _SESSION is not None:
            _SESSION.disconnect()
    except Exception:
        pass
    _SESSION = None
    _DEVICE = None


def reset_myjd_session() -> None:
    """Force reconnect on next call (e.g. after auth failure)."""
    _disconnect_sync()


def status_sync() -> dict[str, Any]:
    if not myjd_enabled():
        return {"configured": False, "connected": False, "hint": "Set TBCC_MYJD_EMAIL and TBCC_MYJD_PASSWORD"}
    try:
        _, device = _connect_sync()
        collecting = bool(device.linkgrabber.is_collecting())
        return {
            "configured": True,
            "connected": True,
            "device": getattr(device, "name", None),
            "linkgrabber_collecting": collecting,
        }
    except Exception as e:
        out: dict[str, Any] = {"configured": True, "connected": False, "error": str(e).strip()}
        try:
            import myjdapi

            email = (os.environ.get("TBCC_MYJD_EMAIL") or "").strip().lower()
            password = (os.environ.get("TBCC_MYJD_PASSWORD") or "").strip()
            if email and password:
                jd = myjdapi.Myjdapi()
                jd.connect(email, password)
                jd.update_devices()
                devices = jd.list_devices() or []
                out["available_devices"] = [d.get("name") for d in devices if d.get("name")]
                out["configured_device_name"] = myjd_device_name() or None
        except Exception:
            pass
        return out


def _http_url_from_link_row(row: dict[str, Any]) -> str | None:
    u = row.get("url")
    if not u:
        return None
    s = str(u).strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return None


def _resolve_page_sync(
    page_url: str,
    *,
    package_name: str | None = None,
    autostart: bool = False,
) -> list[MyJdResolvedItem]:
    _, device = _connect_sync()
    lg = device.linkgrabber
    pkg = package_name or f"TBCC {int(time.time())}"
    lg.add_links(
        [
            {
                "autostart": autostart,
                "links": page_url.strip(),
                "packageName": pkg,
                "priority": "DEFAULT",
                "overwritePackagizerRules": False,
            }
        ]
    )
    deadline = time.monotonic() + myjd_poll_timeout_s()
    while time.monotonic() < deadline:
        if not lg.is_collecting():
            break
        time.sleep(0.75)
    rows = lg.query_links(
        [
            {
                "bytesTotal": True,
                "url": True,
                "availability": True,
                "maxResults": -1,
                "startAt": 0,
            }
        ]
    )
    out: list[MyJdResolvedItem] = []
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        http = _http_url_from_link_row(row)
        if not http or http in seen:
            continue
        avail = str(row.get("availability") or "").upper()
        if avail in ("OFFLINE", "DEAD"):
            continue
        seen.add(http)
        out.append(
            MyJdResolvedItem(
                url=http,
                name=(str(row.get("name") or "").strip() or None),
                availability=avail or None,
                bytes_total=row.get("bytesTotal") if isinstance(row.get("bytesTotal"), int) else None,
            )
        )
    return out


def _add_links_sync(links: str, *, package_name: str | None = None, autostart: bool = False) -> dict[str, Any]:
    _, device = _connect_sync()
    pkg = package_name or f"TBCC {int(time.time())}"
    urls = _split_link_lines(links)
    if not urls:
        raise ValueError("No http(s) links in payload")
    batch_size = myjd_max_links_per_batch()
    jobs: list[Any] = []
    for i in range(0, len(urls), batch_size):
        chunk = urls[i : i + batch_size]
        suffix = f" ({i // batch_size + 1})" if len(urls) > batch_size else ""
        job = device.linkgrabber.add_links(
            [
                {
                    "autostart": autostart,
                    "links": "\n".join(chunk),
                    "packageName": pkg + suffix,
                    "priority": "DEFAULT",
                }
            ]
        )
        jobs.append(job)
    return {
        "ok": True,
        "package_name": pkg,
        "link_count": len(urls),
        "batches": len(jobs),
        "job": jobs[-1] if jobs else None,
    }


def _plugin_handles_url_sync(url: str) -> bool | None:
    """Return True/False if JD reports a decrypter plugin; None if unknown."""
    try:
        _, device = _connect_sync()
        patterns = device.action("/plugins/getPluginRegex", [url])
        return bool(patterns)
    except Exception:
        return None


async def myjd_status() -> dict[str, Any]:
    return await asyncio.wait_for(asyncio.to_thread(status_sync), timeout=myjd_request_timeout_s())


async def myjd_add_links(links: str, *, package_name: str | None = None, autostart: bool = False) -> dict[str, Any]:
    return await asyncio.wait_for(
        asyncio.to_thread(_add_links_sync, links, package_name=package_name, autostart=autostart),
        timeout=myjd_request_timeout_s(),
    )


async def myjd_resolve_page(
    page_url: str,
    *,
    package_name: str | None = None,
    autostart: bool = False,
) -> list[MyJdResolvedItem]:
    # Resolve polls linkgrabber up to poll timeout; allow extra headroom for connect.
    timeout = myjd_poll_timeout_s() + myjd_request_timeout_s()
    return await asyncio.wait_for(
        asyncio.to_thread(
            _resolve_page_sync,
            page_url,
            package_name=package_name,
            autostart=autostart,
        ),
        timeout=timeout,
    )


async def myjd_can_handle_url(url: str) -> bool | None:
    return await asyncio.wait_for(asyncio.to_thread(_plugin_handles_url_sync, url), timeout=myjd_request_timeout_s())


def should_use_myjd_for_url(url: str, *, local_adapter: str, local_count: int) -> bool:
    mode = (os.environ.get("TBCC_CRAWLER_MYJD_MODE") or "auto").strip().lower()
    if mode in ("never", "off", "0", "false"):
        return False
    if mode in ("always", "force", "1", "true"):
        return True
    if local_count > 0 and local_adapter not in ("generic",):
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host in ("erome.com",) or host.endswith(".erome.com"):
        return False
    if local_adapter == "onlyfans":
        return False
    return True
