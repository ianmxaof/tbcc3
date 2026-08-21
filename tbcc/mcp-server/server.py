#!/usr/bin/env python3
"""
TBCC MCP server — exposes local FastAPI (Telegram Bot Command Center) to Cursor / Claude.

Requires TBCC API on http://127.0.0.1:8000 (see tbcc/start.ps1 or uvicorn).
Celery worker needed for trigger_scheduled_post / import side effects.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# tbcc/.env (API keys optional for most routes)
for _p in (
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parent / ".env",
):
    if _p.exists():
        load_dotenv(_p, override=False)
        break

TBCC_API_URL = (os.getenv("TBCC_API_URL") or os.getenv("TBCC_MCP_API_URL") or "http://127.0.0.1:8000").rstrip(
    "/"
)
TBCC_INTERNAL_KEY = (os.getenv("TBCC_INTERNAL_API_KEY") or os.getenv("TBCC_MCP_INTERNAL_KEY") or "").strip()

mcp = FastMCP(
    "tbcc",
    instructions=(
        "Tools for Telegram Bot Command Center (TBCC): schedule Telegram channel posts, "
        "browse media pools, import URLs, caption snippets, and operational analytics. "
        "Posting requires Celery + Redis (tbcc start -Full). Buffer cross-post uses TBCC's "
        "buffer_mirror_enabled on scheduled jobs or the separate Buffer MCP."
    ),
)


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if TBCC_INTERNAL_KEY:
        h["X-TBCC-Internal-Key"] = TBCC_INTERNAL_KEY
    return h


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> Any:
    url = f"{TBCC_API_URL}{path}"
    with httpx.Client(timeout=timeout) as client:
        r = client.request(method, url, params=params, json=json_body, headers=_headers())
    if r.status_code >= 400:
        detail = r.text[:2000]
        try:
            detail = json.dumps(r.json(), indent=2)
        except Exception:
            pass
        raise RuntimeError(f"TBCC API {method} {path} → HTTP {r.status_code}: {detail}")
    if not r.content:
        return {}
    return r.json()


def _pretty(data: Any, *, max_chars: int = 24_000) -> str:
    text = json.dumps(data, indent=2, default=str)
    if len(text) > max_chars:
        return text[: max_chars - 80] + "\n… (truncated)"
    return text


@mcp.tool()
def tbcc_health() -> str:
    """Check that the TBCC API is reachable and return OpenAPI title/version hint."""
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get(f"{TBCC_API_URL}/openapi.json", headers=_headers())
        if r.status_code >= 400:
            return f"API unreachable at {TBCC_API_URL} (HTTP {r.status_code})"
        spec = r.json()
        title = spec.get("info", {}).get("title", "TBCC")
        version = spec.get("info", {}).get("version", "?")
        return f"OK — {title} v{version} at {TBCC_API_URL}"
    except Exception as e:
        return f"Cannot reach TBCC API at {TBCC_API_URL}: {e}\nStart with: cd tbcc && .\\start.ps1"


@mcp.tool()
def list_channels() -> str:
    """List Telegram channels configured in TBCC (id, name, identifier)."""
    return _pretty(_request("GET", "/channels/"))


@mcp.tool()
def list_pools() -> str:
    """List content pools with approved media counts."""
    return _pretty(_request("GET", "/pools/"))


@mcp.tool()
def list_scheduled_posts() -> str:
    """List all scheduled / recurring post jobs (captions, timing, pool, buffer flags)."""
    return _pretty(_request("GET", "/scheduled-posts/"))


@mcp.tool()
def create_scheduled_post(
    channel_id: int,
    content: str = "",
    *,
    name: str | None = None,
    channel_ids: list[int] | None = None,
    message_thread_id: int | None = None,
    scheduled_at_iso: str | None = None,
    interval_minutes: int | None = None,
    media_ids: list[int] | None = None,
    pool_id: int | None = None,
    pool_only_mode: bool = False,
    album_size: int | None = None,
    pool_randomize: bool | None = None,
    content_variations: list[str] | None = None,
    attachment_urls: list[str] | None = None,
    album_order_mode: str | None = None,
    send_silent: bool = False,
    pin_after_send: bool = False,
    buffer_mirror_enabled: bool = False,
    buffer_publish_now: bool = False,
    caption_llm_rewrite_enabled: bool = False,
    caption_llm_rewrite_mode: str | None = None,
) -> str:
    """
    Create a one-time or recurring scheduled Telegram post.

    Provide either scheduled_at_iso (one-time, UTC ISO e.g. 2026-05-20T18:00:00)
    or interval_minutes (recurring). Use content_variations (2+ strings) for rotating captions.
    Use pool_id (+ optional media_ids) for album posts from approved pool media.
    Set buffer_mirror_enabled to mirror to Buffer (X/IG/Threads) after Telegram send.
    """
    body: dict[str, Any] = {
        "channel_id": channel_id,
        "content": content,
        "send_silent": send_silent,
        "pin_after_send": pin_after_send,
        "buffer_mirror_enabled": buffer_mirror_enabled,
        "buffer_publish_now": buffer_publish_now,
        "caption_llm_rewrite_enabled": caption_llm_rewrite_enabled,
        "pool_only_mode": pool_only_mode,
    }
    if name:
        body["name"] = name
    if channel_ids:
        body["channel_ids"] = channel_ids
    if message_thread_id is not None:
        body["message_thread_id"] = message_thread_id
    if scheduled_at_iso:
        body["scheduled_at"] = scheduled_at_iso
    if interval_minutes is not None:
        body["interval_minutes"] = interval_minutes
    if media_ids:
        body["media_ids"] = media_ids
    if pool_id is not None:
        body["pool_id"] = pool_id
    if album_size is not None:
        body["album_size"] = album_size
    if pool_randomize is not None:
        body["pool_randomize"] = pool_randomize
    if content_variations:
        body["content_variations"] = content_variations
    if attachment_urls:
        body["attachment_urls"] = attachment_urls
    if album_order_mode:
        body["album_order_mode"] = album_order_mode
    if caption_llm_rewrite_mode:
        body["caption_llm_rewrite_mode"] = caption_llm_rewrite_mode

    result = _request("POST", "/scheduled-posts/", json_body=body)
    return _pretty(result)


@mcp.tool()
def trigger_scheduled_post(post_id: int, reshuffle: bool = False) -> str:
    """
    Enqueue an immediate send for a scheduled post (Celery). Use reshuffle=true to
    randomize album/promo order and allow re-sending one-time jobs that already ran.
    """
    params = {"reshuffle": "true" if reshuffle else "false"}
    return _pretty(_request("POST", f"/scheduled-posts/{post_id}/trigger", params=params))


@mcp.tool()
def deploy_campaign_post(
    post_id: int,
    sync: bool = False,
    telegram: bool = True,
    buffer: bool | None = None,
    discord: bool | None = None,
    reshuffle: bool = False,
) -> str:
    """
    Multi-surface deploy: Telegram (+ optional Buffer/Discord mirrors). sync=true blocks until done.
    buffer/discord None = use each post's buffer_mirror_enabled / discord_mirror_enabled flags.
    """
    body: dict[str, Any] = {
        "telegram": telegram,
        "sync": sync,
        "reshuffle": reshuffle,
    }
    if buffer is not None:
        body["buffer"] = buffer
    if discord is not None:
        body["discord"] = discord
    return _pretty(_request("POST", f"/campaigns/deploy/post/{post_id}", json_body=body))


@mcp.tool()
def audit_campaign_schedules() -> str:
    """List all scheduled posts + recent multi-surface deploy ledger entries."""
    return _pretty(_request("GET", "/campaigns/audit/schedules"))


@mcp.tool()
def list_media(
    status: str | None = "approved",
    pool_id: int | None = None,
    tag: str | None = None,
    tag_slug: str | None = None,
    sort: str | None = None,
    limit_hint: int = 25,
) -> str:
    """
    List media in the library (max 200 from API). status: approved|pending|rejected.
    tag: substring on legacy tags field; tag_slug: exact catalog slug.
    sort=recommended with pool_id uses pool preference scoring.
    limit_hint only affects display truncation in the response message.
    """
    params: dict[str, Any] = {}
    if status:
        params["status"] = status
    if pool_id is not None:
        params["pool_id"] = pool_id
    if tag:
        params["tag"] = tag
    if tag_slug:
        params["tag_slug"] = tag_slug
    if sort:
        params["sort"] = sort
    rows = _request("GET", "/media/", params=params)
    if isinstance(rows, list) and len(rows) > limit_hint:
        slim = []
        for m in rows[:limit_hint]:
            if isinstance(m, dict):
                slim.append(
                    {
                        "id": m.get("id"),
                        "pool_id": m.get("pool_id"),
                        "status": m.get("status"),
                        "media_type": m.get("media_type"),
                        "tags": m.get("tags"),
                        "nsfw_tier": m.get("nsfw_tier"),
                        "recommendation_score": m.get("recommendation_score"),
                    }
                )
            else:
                slim.append(m)
        return _pretty(
            {
                "shown": len(slim),
                "total_returned": len(rows),
                "items": slim,
                "note": f"API returned {len(rows)} rows; showing first {limit_hint}. Narrow with pool_id or tag.",
            }
        )
    return _pretty(rows)


@mcp.tool()
def suggest_pool_album(
    pool_id: int,
    seed_media_id: int | None = None,
    limit: int = 10,
    status: str = "approved",
) -> str:
    """Suggest up to 10 media IDs in a pool grouped by facet overlap (for album scheduling)."""
    params: dict[str, Any] = {"limit": min(10, max(1, limit)), "status": status}
    if seed_media_id is not None:
        params["seed_media_id"] = seed_media_id
    return _pretty(_request("GET", f"/pools/{pool_id}/suggest-album", params=params))


@mcp.tool()
def list_caption_snippets() -> str:
    """List reusable caption snippets from the TBCC caption library."""
    return _pretty(_request("GET", "/caption-snippets/"))


@mcp.tool()
def bulk_create_caption_snippets(items: list[dict[str, str]]) -> str:
    """
    Add caption snippets in bulk. Each item: {"title": "optional", "body": "caption text"}.
    """
    body = {"items": items}
    return _pretty(_request("POST", "/caption-snippets/bulk", json_body=body))


@mcp.tool()
def import_media_url(
    url: str,
    pool_id: int = 1,
    saved_only: bool = False,
    caption: str = "",
) -> str:
    """
    Import media from a public http(s) URL into a pool (or Saved Messages only if saved_only=true).
    Requires Telegram API credentials on the TBCC backend.
    """
    body: dict[str, Any] = {"url": url, "pool_id": pool_id, "saved_only": saved_only}
    if caption.strip():
        body["caption"] = caption.strip()
    return _pretty(_request("POST", "/import/url", json_body=body, timeout=300.0))


@mcp.tool()
def analytics_post_events_summary(days: int = 30) -> str:
    """Operational analytics: outbound Telegram sends by day/channel (not engagement/views)."""
    days = max(1, min(366, days))
    return _pretty(_request("GET", "/analytics/post-events/summary", params={"days": days}))


@mcp.tool()
def analytics_subscriptions() -> str:
    """Subscription counts and Telegram Stars revenue."""
    return _pretty(_request("GET", "/analytics/subscriptions"))


@mcp.tool()
def analytics_income_summary(days: int | None = None) -> str:
    """Unified income rollup (USD + Stars) across internal and external sources."""
    params: dict = {}
    if days is not None:
        params["days"] = max(1, min(3660, int(days)))
    return _pretty(_request("GET", "/analytics/income/summary", params=params or None))


@mcp.tool()
def analytics_income_sync(sources: str = "") -> str:
    """Sync external income (linkvertise, admaven, workink, bmc). Comma-separated sources or empty for all."""
    src_list = [s.strip() for s in sources.split(",") if s.strip()] or None
    body: dict = {}
    if src_list:
        body["sources"] = src_list
    return _pretty(_request("POST", "/analytics/income/sync", json_body=body))


@mcp.tool()
def analytics_weekly_summary(days: int = 7) -> str:
    """
    Human-readable weekly ops report: subscriptions + outbound posts + recent failures.
    Suitable to paste into Slack/Discord after light editing.
    """
    days = max(1, min(30, days))
    subs = _request("GET", "/analytics/subscriptions")
    summary = _request("GET", "/analytics/post-events/summary", params={"days": days})
    events = _request("GET", "/analytics/post-events", params={"limit": 15, "offset": 0})

    totals = summary.get("totals") or {}
    by_day = summary.get("by_day") or []
    failed_recent = [e for e in (events.get("items") or []) if not e.get("ok")]

    lines = [
        f"# TBCC weekly summary (last {days} days)",
        "",
        "## Subscriptions",
        f"- Total: {subs.get('total_subscriptions', 0)} | Active: {subs.get('active', 0)} | Revenue: {subs.get('revenue_stars', 0)} Stars",
        "",
        "## Outbound Telegram posts",
        f"- Scheduled sends: {totals.get('scheduled_post_sent', 0)}",
        f"- Pool albums: {totals.get('pool_album_posted', 0)}",
        f"- Succeeded: {totals.get('ok', 0)} | Failed: {totals.get('failed', 0)}",
        "",
        "### By day",
    ]
    for row in by_day[-days:]:
        lines.append(
            f"- {row.get('date')}: {row.get('count', 0)} total "
            f"({row.get('scheduled_post_sent', 0)} scheduled, {row.get('pool_album_posted', 0)} pool)"
        )
    if failed_recent:
        lines.extend(["", "## Recent failures"])
        for e in failed_recent[:5]:
            lines.append(
                f"- {e.get('created_at')} post #{e.get('scheduled_post_id')} "
                f"channel {e.get('channel_name')}: {e.get('error_message', '')[:120]}"
            )
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from {TBCC_API_URL}_")
    return "\n".join(lines)


@mcp.tool()
def analytics_direction(days: int = 30, use_llm: bool = False, format: str = "markdown") -> str:
    """
    On-demand analytics direction — deterministic Top 5 investment ranking from TBCC evidence.
    Composes income, pools, growth signals, blockers, and funnel data. Observe-only (no auto-post).
    format: markdown (default) or json.
    """
    days = max(1, min(366, int(days)))
    report = _request(
        "GET",
        "/analytics/direction",
        params={"days": days, "use_llm": use_llm},
    )
    if format == "markdown":
        return str(report.get("markdown") or _pretty(report))
    return _pretty(report)


@mcp.tool()
def analytics_content_performance(days: int = 14, run_tick: bool = True) -> str:
    """
    Strongest content/growth signals for OpenClaw — ranked peak hours, caption winners, lane leaders.
    Runs growth tick (view refresh + signal ranking) when run_tick=True.
    """
    days = max(1, min(90, days))
    if run_tick:
        elig = _request("GET", "/analytics/signals/eligibility")
        if not elig.get("eligible"):
            reason = elig.get("reason") or "insufficient_data"
            return f"_Growth tick skipped — {reason} (no Telethon/OpenClaw work)._"
        tick = _request("POST", "/analytics/signals/tick", params={"refresh_views": "true", "push_inbox": "false"})
        if tick.get("skipped"):
            return tick.get("markdown") or f"_Growth tick skipped — {tick.get('skip_reason', 'no data')}._"
        report = tick.get("report") or {}
        md = tick.get("markdown")
        if md:
            return md
    else:
        report = _request("GET", "/analytics/signals", params={"days": days})

    lines = [
        f"# TBCC growth signals (last {report.get('lookback_days', days)} days)",
        f"tz={report.get('timezone')} · network avg views={report.get('network_avg_views')}",
        "",
    ]
    for i, s in enumerate(report.get("signals") or [], 1):
        lines.append(
            f"{i}. [{s.get('confidence')}] {s.get('signal_type')} (strength={s.get('strength')})"
        )
        lines.append(f"   {s.get('recommendation')}")
    if not report.get("signals"):
        lines.append("_Insufficient data — need more posted deliveries with view refresh._")
    lines.append("")
    return "\n".join(lines)


@mcp.tool()
def growth_signals_eligibility() -> str:
    """Check whether growth tick / view refresh is worth running (no Telethon cost if false)."""
    out = _request("GET", "/analytics/signals/eligibility")
    return _pretty(out)


@mcp.tool()
def growth_signal_proposals(days: int = 14) -> str:
    """
    Pending growth reaction proposals — draft actions derived from top signals.
    Observe-only: each proposal has an action_kind + params for the operator to
    approve. NEVER execute a proposal without explicit operator OK; report only.
    """
    days = max(3, min(90, days))
    out = _request("GET", "/analytics/signals/proposals", params={"days": days})
    proposals = out.get("proposals") or []
    if not proposals:
        return "No pending growth proposals (no strong signals, or all dismissed)."
    lines = [f"# Growth reaction proposals ({len(proposals)} pending)", ""]
    for p in proposals:
        lines.append(
            f"- `{p.get('id')}` [{p.get('confidence')}] {p.get('signal_type')} "
            f"-> {p.get('action_kind')}"
        )
        lines.append(f"  {p.get('recommendation')}")
        note = (p.get("action_params") or {}).get("suggested_note")
        if note:
            lines.append(f"  action: {note}")
    lines.append("")
    lines.append("Approval required before acting. To drop one: POST /analytics/signals/proposals/{id}/dismiss")
    return "\n".join(lines)


@mcp.tool()
def tbcc_flywheel_tick(ops_limit: int = 1) -> str:
    """TBCC flywheel tick: route critical ops + refresh growth signals. Returns JSON."""
    out = _request("POST", "/analytics/tbcc-flywheel/tick", params={"ops_limit": ops_limit})
    return _pretty(out)


@mcp.tool()
def openclaw_tick(ops_limit: int = 1) -> str:
    """Deprecated alias for tbcc_flywheel_tick (internal event bus, not the OpenClaw gateway)."""
    return tbcc_flywheel_tick(ops_limit=ops_limit)


@mcp.tool()
def flywheel_approval_bundle() -> str:
    """Pending Secretary flywheel approvals — use before executing destructive fixes."""
    return _pretty(_request("GET", "/ops/flywheel/approval-bundle"))


@mcp.tool()
def flywheel_approve(action_id: str, operator: str = "openclaw") -> str:
    """Approve a pending flywheel action. OpenClaw role is denied — use @aof_secretary_bot."""
    return _pretty(
        _request(
            "POST",
            f"/ops/flywheel/approve/{action_id.strip()}",
            params={"operator": operator},
        )
    )


@mcp.tool()
def flywheel_reject(action_id: str, operator: str = "openclaw") -> str:
    """Reject/dismiss a stale flywheel approval. OpenClaw role is denied — use Secretary."""
    return _pretty(
        _request(
            "POST",
            f"/ops/flywheel/reject/{action_id.strip()}",
            params={"operator": operator},
        )
    )


@mcp.tool()
def run_ops_workflow(ops_limit: int = 1, operator: str = "openclaw", include_handoff: bool = True) -> str:
    """Run tbcc_ops_turn workflow: health → scheduling → flywheel → approval gate → handoff."""
    return _pretty(
        _request(
            "POST",
            "/ops/workflow/run",
            json_body={
                "ops_limit": ops_limit,
                "operator": operator,
                "include_handoff": include_handoff,
            },
        )
    )


@mcp.tool()
def schedule_recurring_campaign(
    channel_id: int,
    captions: list[str],
    interval_minutes: int,
    *,
    name: str | None = None,
    pool_id: int | None = None,
    album_size: int = 5,
    pool_randomize: bool = True,
    pool_only_mode: bool = True,
    buffer_mirror_enabled: bool = False,
    buffer_publish_now: bool = False,
    caption_llm_rewrite_enabled: bool = False,
) -> str:
    """
    Convenience: create one recurring job with rotating captions (content_variations).
    Defaults to pool-only album pulls when pool_id is set.
    """
    if len(captions) < 1:
        raise ValueError("captions must contain at least one non-empty string")
    cleaned = [c.strip() for c in captions if c and c.strip()]
    if not cleaned:
        raise ValueError("captions must contain at least one non-empty string")

    body: dict[str, Any] = {
        "channel_id": channel_id,
        "content": cleaned[0],
        "interval_minutes": interval_minutes,
        "content_variations": cleaned if len(cleaned) >= 2 else None,
        "pool_id": pool_id,
        "album_size": album_size,
        "pool_randomize": pool_randomize,
        "pool_only_mode": pool_only_mode if pool_id else False,
        "buffer_mirror_enabled": buffer_mirror_enabled,
        "buffer_publish_now": buffer_publish_now,
        "caption_llm_rewrite_enabled": caption_llm_rewrite_enabled,
    }
    if name:
        body["name"] = name
    if len(cleaned) < 2:
        body.pop("content_variations", None)

    return _pretty(_request("POST", "/scheduled-posts/", json_body=body))


@mcp.tool()
def llm_providers() -> str:
    """List which of TBCC's configured LLM providers (openai, openrouter, mistral,
    groq, cerebras, nvidia, etc.) currently resolve on the island — no API call,
    no cost. Use before ask_llm to see what's actually usable right now."""
    return _pretty(_request("GET", "/zeus/v1/ask/providers"))


@mcp.tool()
def ask_llm(
    prompt: str,
    *,
    system: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    max_tokens: int = 600,
    temperature: float = 0.7,
) -> str:
    """One-shot LLM completion via TBCC's own provider fallback chain, running on
    the island — not this session's own model. Use this as a fallback lane when
    your own usage is capped: it tries whichever of TBCC's 12 configured providers
    (openai/openrouter/mistral/groq/cerebras/nvidia/...) are actually keyed, in
    order, until one answers. Leave provider/model unset to walk the full chain."""
    body: dict[str, Any] = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        body["system"] = system
    if provider:
        body["provider"] = provider
    if model:
        body["model"] = model
    return _pretty(_request("POST", "/zeus/v1/ask", json_body=body, timeout=100.0))


if __name__ == "__main__":
    mcp.run()
