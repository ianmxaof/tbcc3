"""
Telegram's servers fetch promo/invoice image URLs directly — not the user's browser.
localhost, private IPs, and non-HTTPS URLs will not work for bots / invoices.
"""

from __future__ import annotations

from urllib.parse import urlparse


def is_public_https_for_telegram(url: str | None) -> bool:
    """True if Telegram's servers can plausibly fetch this URL for sendPhoto / sendInvoice photo_url."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    if not u.startswith("https://"):
        return False
    try:
        host = (urlparse(u).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        return False
    if host.endswith(".local"):
        return False
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        a, b = int(parts[0]), int(parts[1])
        if a == 10:
            return False
        if a == 192 and b == 168:
            return False
        if a == 172 and 16 <= b <= 31:
            return False
    return True


def promo_hint(url: str | None) -> str | None:
    """Short reason for dashboard when URL is not Telegram-fetchable."""
    if not url or not str(url).strip():
        return None
    s = str(url).strip()
    if not s.startswith("https://"):
        return "Use an https:// link. Telegram often rejects http:// for invoice photos."
    if not is_public_https_for_telegram(s):
        return (
            "Telegram cannot load localhost or private network URLs. "
            "Set TBCC_PROMO_PUBLIC_BASE_URL (or TBCC_PUBLIC_BASE_URL) to your public https:// API and re-upload, "
            "or paste a direct image link (e.g. i.ibb.co/…/file.jpg)."
        )
    return None
