from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.listening_relay_format import parse_lastfm_recent_track

logger = logging.getLogger(__name__)

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"


def fetch_recent_track_lastfm_sync(*, username: str, api_key: str) -> dict[str, Any] | None:
    params = {
        "method": "user.getrecenttracks",
        "user": username.strip(),
        "api_key": api_key.strip(),
        "format": "json",
        "limit": "1",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(LASTFM_API, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Last.fm request failed: %s", e)
        return None
    if data.get("error"):
        logger.warning("Last.fm API error: %s", data.get("message") or data)
        return None
    return parse_lastfm_recent_track(data)
