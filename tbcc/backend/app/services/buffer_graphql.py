"""Buffer GraphQL: createPost for X / Instagram / Threads (queue or publish now)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://api.buffer.com"

BufferShareMode = Literal["addToQueue", "shareNow", "shareNext", "customScheduled", "recommendedTime"]

_CREATE_POST_MUTATION = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess {
      post { id text }
    }
    ... on MutationError {
      message
    }
  }
}
"""


def buffer_graphql_url() -> str:
    return (os.environ.get("TBCC_BUFFER_GRAPHQL_URL") or DEFAULT_ENDPOINT).strip().rstrip("/")


def buffer_api_key() -> str | None:
    k = (os.environ.get("TBCC_BUFFER_API_KEY") or "").strip()
    return k or None


def buffer_target_channel_ids(*, x_primary_only: bool = False) -> list[str]:
    """
    Channel ids for createPost. primary + TBCC_BUFFER_CHANNEL_IDS unless x_primary_only
    or TBCC_BUFFER_X_ONLY=1 (X/twitter primary only — saves IG/Threads queue slots).
    """
    primary = (os.environ.get("TBCC_BUFFER_CHANNEL_ID_PRIMARY") or "").strip()
    x_only_env = (os.environ.get("TBCC_BUFFER_X_ONLY") or "").strip().lower() in ("1", "true", "yes")
    if x_primary_only or x_only_env:
        return [primary] if primary else []
    out: list[str] = []
    if primary:
        out.append(primary)
    rest = (os.environ.get("TBCC_BUFFER_CHANNEL_IDS") or "").strip()
    for part in rest.split(","):
        p = part.strip()
        if p and p not in out:
            out.append(p)
    return out


def scheduled_buffer_share_mode(*, buffer_publish_now: bool = False) -> BufferShareMode:
    """Resolve addToQueue vs shareNow for scheduled Telegram mirrors."""
    if buffer_publish_now:
        return "shareNow"
    if (os.environ.get("TBCC_BUFFER_SCHEDULED_SHARE_NOW") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return "shareNow"
    return "addToQueue"


def create_post(
    channel_id: str,
    text: str,
    *,
    mode: BufferShareMode = "addToQueue",
    scheduling_type: str = "automatic",
    image_url: str | None = None,
) -> dict[str, Any]:
    """
    Mutation createPost.
    mode addToQueue — Buffer queue (publishes on Buffer schedule).
    mode shareNow — publish immediately when Telegram mirror runs.
    image_url must be public https URL Buffer can fetch.
    """
    cid = (channel_id or "").strip()
    if not cid:
        raise ValueError("channel_id required")
    inp: dict[str, Any] = {
        "text": (text or "").strip(),
        "channelId": cid,
        "schedulingType": scheduling_type,
        "mode": mode,
    }
    iu = (image_url or "").strip()
    if iu.startswith("http"):
        inp["assets"] = [{"image": {"url": iu}}]
    payload = {"query": _CREATE_POST_MUTATION, "variables": {"input": inp}}
    key = buffer_api_key()
    if not key:
        raise RuntimeError("TBCC_BUFFER_API_KEY is not set")
    url = buffer_graphql_url()
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            json=payload,
        )
    try:
        data = r.json()
    except json.JSONDecodeError:
        logger.warning("Buffer GraphQL non-JSON %s: %s", r.status_code, r.text[:300])
        raise RuntimeError(f"Buffer GraphQL HTTP {r.status_code}") from None
    if r.status_code >= 400:
        logger.warning("Buffer GraphQL HTTP %s: %s", r.status_code, str(data)[:500])
    if data.get("errors"):
        logger.warning("Buffer GraphQL errors: %s", data.get("errors"))
    cp = (data.get("data") or {}).get("createPost") if isinstance(data.get("data"), dict) else None
    if isinstance(cp, dict) and cp.get("message"):
        logger.warning("Buffer createPost mode=%s: %s", mode, cp.get("message"))
    return data


def create_post_add_to_queue(
    channel_id: str,
    text: str,
    *,
    image_url: str | None = None,
) -> dict[str, Any]:
    return create_post(channel_id, text, mode="addToQueue", image_url=image_url)


def create_posts_multi_channel(
    text: str,
    *,
    image_url: str | None = None,
    channel_ids: list[str] | None = None,
    mode: BufferShareMode = "addToQueue",
) -> list[dict[str, Any]]:
    """One createPost per channel. Returns list of GraphQL response dicts."""
    ids = channel_ids if channel_ids is not None else buffer_target_channel_ids()
    results: list[dict[str, Any]] = []
    for cid in ids:
        try:
            results.append(create_post(cid, text, mode=mode, image_url=image_url))
        except Exception as e:
            logger.exception("Buffer createPost failed channel=%s mode=%s: %s", cid, mode, e)
            results.append({"error": str(e), "channelId": cid})
    return results
