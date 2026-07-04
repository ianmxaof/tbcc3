"""Buffer GraphQL: posts, ideas, channels (https://developers.buffer.com/)."""

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

_GET_ORGANIZATIONS_QUERY = """
query GetOrganizations {
  account {
    organizations {
      id
      name
      ownerEmail
    }
  }
}
"""

_GET_CHANNELS_QUERY = """
query GetChannels($organizationId: OrganizationId!) {
  channels(input: { organizationId: $organizationId }) {
    id
    name
    displayName
    service
    avatar
    isQueuePaused
  }
}
"""

_LIST_POSTS_QUERY = """
query ListPosts($input: PostsInput!, $first: Int, $after: String) {
  posts(input: $input, first: $first, after: $after) {
    edges {
      node {
        id
        text
        status
        dueAt
        sentAt
        channelId
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""

_CREATE_IDEA_MUTATION = """
mutation CreateIdea($input: CreateIdeaInput!) {
  createIdea(input: $input) {
    ... on Idea {
      id
      content {
        title
        text
      }
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


def buffer_organization_id() -> str | None:
    return (os.environ.get("TBCC_BUFFER_ORGANIZATION_ID") or "").strip() or None


def graphql_request(
    query: str,
    *,
    variables: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    key = buffer_api_key()
    if not key:
        raise RuntimeError("TBCC_BUFFER_API_KEY is not set")
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    with httpx.Client(timeout=timeout) as client:
        r = client.post(
            buffer_graphql_url(),
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
    return data


def get_organizations() -> list[dict[str, Any]]:
    data = graphql_request(_GET_ORGANIZATIONS_QUERY)
    account = (data.get("data") or {}).get("account") if isinstance(data.get("data"), dict) else None
    if not isinstance(account, dict):
        return []
    orgs = account.get("organizations")
    return [o for o in orgs if isinstance(o, dict)] if isinstance(orgs, list) else []


def resolve_organization_id() -> str:
    oid = buffer_organization_id()
    if oid:
        return oid
    orgs = get_organizations()
    if not orgs:
        raise RuntimeError(
            "No Buffer organizations — check TBCC_BUFFER_API_KEY or set TBCC_BUFFER_ORGANIZATION_ID"
        )
    if len(orgs) > 1:
        logger.warning(
            "Multiple Buffer orgs; using first (%s). Set TBCC_BUFFER_ORGANIZATION_ID to pin one.",
            orgs[0].get("name"),
        )
    return str(orgs[0].get("id") or "").strip()


def get_channels(*, organization_id: str | None = None) -> list[dict[str, Any]]:
    oid = (organization_id or resolve_organization_id()).strip()
    data = graphql_request(_GET_CHANNELS_QUERY, variables={"organizationId": oid})
    chans = (data.get("data") or {}).get("channels") if isinstance(data.get("data"), dict) else None
    return [c for c in chans if isinstance(c, dict)] if isinstance(chans, list) else []


def list_posts(
    *,
    organization_id: str | None = None,
    channel_ids: list[str] | None = None,
    status: list[str] | None = None,
    first: int = 50,
    after: str | None = None,
    sort_field: str = "dueAt",
    sort_direction: str = "asc",
) -> list[dict[str, Any]]:
    """Return post nodes from Buffer posts query (paginates once via after)."""
    oid = (organization_id or resolve_organization_id()).strip()
    filt: dict[str, Any] = {}
    if channel_ids:
        filt["channelIds"] = [c.strip() for c in channel_ids if c.strip()]
    if status:
        filt["status"] = status
    inp: dict[str, Any] = {
        "organizationId": oid,
        "sort": [{"field": sort_field, "direction": sort_direction}],
    }
    if filt:
        inp["filter"] = filt
    variables: dict[str, Any] = {"input": inp, "first": max(1, min(100, int(first)))}
    if after:
        variables["after"] = after
    data = graphql_request(_LIST_POSTS_QUERY, variables=variables)
    posts = (data.get("data") or {}).get("posts") if isinstance(data.get("data"), dict) else None
    if not isinstance(posts, dict):
        return []
    edges = posts.get("edges")
    out: list[dict[str, Any]] = []
    if isinstance(edges, list):
        for edge in edges:
            if isinstance(edge, dict) and isinstance(edge.get("node"), dict):
                out.append(edge["node"])
    page = posts.get("pageInfo")
    if isinstance(page, dict) and page.get("hasNextPage") and page.get("endCursor"):
        out.extend(
            list_posts(
                organization_id=oid,
                channel_ids=channel_ids,
                status=status,
                first=first,
                after=str(page["endCursor"]),
                sort_field=sort_field,
                sort_direction=sort_direction,
            )
        )
    return out


def find_channel_id_by_service(service: str, *, organization_id: str | None = None) -> str | None:
    want = (service or "").strip().lower()
    for ch in get_channels(organization_id=organization_id):
        if str(ch.get("service") or "").strip().lower() == want:
            cid = str(ch.get("id") or "").strip()
            if cid:
                return cid
    return None


def create_idea(
    title: str,
    text: str,
    *,
    organization_id: str | None = None,
) -> dict[str, Any]:
    oid = (organization_id or resolve_organization_id()).strip()
    variables = {
        "input": {
            "organizationId": oid,
            "content": {
                "title": (title or "TBCC ship log").strip()[:200],
                "text": (text or "").strip(),
            },
        }
    }
    return graphql_request(_CREATE_IDEA_MUTATION, variables=variables)


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
    image_urls: list[str] | None = None,
    assets: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Mutation createPost.
    mode addToQueue — Buffer queue (publishes on Buffer schedule).
    mode shareNow — publish immediately when Telegram mirror runs.
    image_url / image_urls must be public https URLs Buffer can fetch.
    Multiple image_urls → Instagram carousel when channel service is instagram.
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
    if assets:
        inp["assets"] = assets
    else:
        urls: list[str] = []
        if image_urls:
            urls.extend(u.strip() for u in image_urls if (u or "").strip().startswith("http"))
        iu = (image_url or "").strip()
        if iu.startswith("http") and iu not in urls:
            urls.insert(0, iu)
        if urls:
            inp["assets"] = [{"image": {"url": u}} for u in urls]
    if metadata:
        inp["metadata"] = metadata
    data = graphql_request(_CREATE_POST_MUTATION, variables={"input": inp})
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


_GET_POST_ANALYTICS_QUERY = """
query GetPostAnalytics($id: PostId!) {
  post(input: { id: $id }) {
    id
    status
    metrics {
      impressions
      engagement
      clicks
    }
  }
}
"""


def fetch_post_impressions(post_id: str) -> int | None:
    """Best-effort Buffer post impressions/views for delivery ledger sync."""
    pid = (post_id or "").strip()
    if not pid:
        return None
    if not buffer_api_key():
        return None
    try:
        data = graphql_request(_GET_POST_ANALYTICS_QUERY, variables={"id": pid})
    except Exception as e:
        logger.debug("Buffer post analytics query failed: %s", e)
        return None
    post = (data.get("data") or {}).get("post") if isinstance(data.get("data"), dict) else None
    if not isinstance(post, dict):
        return None
    metrics = post.get("metrics")
    if not isinstance(metrics, dict):
        return None
    for key in ("impressions", "engagement", "clicks"):
        val = metrics.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None
