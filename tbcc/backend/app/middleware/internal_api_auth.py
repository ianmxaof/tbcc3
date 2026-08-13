"""Optional global gate: require X-TBCC-Internal-Key when TBCC_API_REQUIRE_INTERNAL=1."""

from __future__ import annotations

import os
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Paths that stay public even when the global gate is on.
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/webhooks/",
    "/favicon.ico",
)

# Media GETs (thumbs / file serve) stay readable for gallery; mutations still need the key.
# /r/ = promo click beacon (iplogger-style redirect + notify).
_PUBLIC_GET_PREFIXES: tuple[str, ...] = (
    "/media/",
    "/r/",
)

# Authenticated export for aof-forum ingest — must NOT inherit the public /media/ GET allowlist.
_PROTECTED_GET_PREFIXES: tuple[str, ...] = (
    "/media/export",
)


def api_require_internal_enabled() -> bool:
    raw = (os.getenv("TBCC_API_REQUIRE_INTERNAL") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _expected_key() -> str:
    return (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()


def path_is_public(path: str, method: str) -> bool:
    p = path or "/"
    if p == "/" or p == "":
        return True
    for pref in _PUBLIC_PREFIXES:
        if p == pref.rstrip("/") or p.startswith(pref):
            return True
    if method.upper() == "GET":
        for pref in _PROTECTED_GET_PREFIXES:
            if p == pref or p.startswith(pref + "/"):
                return False
        for pref in _PUBLIC_GET_PREFIXES:
            if p.startswith(pref):
                return True
    if method.upper() == "OPTIONS":
        return True
    return False


class InternalApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not api_require_internal_enabled():
            return await call_next(request)
        expected = _expected_key()
        if not expected:
            logger.warning(
                "TBCC_API_REQUIRE_INTERNAL=1 but TBCC_INTERNAL_API_KEY empty — gate disabled"
            )
            return await call_next(request)
        if path_is_public(request.url.path, request.method):
            return await call_next(request)
        got = (request.headers.get("X-TBCC-Internal-Key") or "").strip()
        if got != expected:
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or missing X-TBCC-Internal-Key"},
            )
        return await call_next(request)
