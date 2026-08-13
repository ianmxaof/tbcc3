# TBCC MCP server

Exposes your local [TBCC](https://github.com/) FastAPI (`http://127.0.0.1:8000`) to Cursor / Claude as MCP tools: schedule posts, list media, import URLs, caption snippets, and ops analytics.

## Prerequisites

1. TBCC API running: `cd tbcc && .\start.ps1` (or `-Full` for Celery).
2. Python 3.10+.

```powershell
cd tbcc\mcp-server
py -3.13 -m pip install -r requirements.txt
```

Use Python 3.11–3.13 (the `mcp` package). On Windows, if `pip` on 3.14 fails, prefer `py -3.13`.

## Cursor configuration

Add to **Cursor Settings → MCP** (or merge into your user `mcp.json`):

```json
{
  "mcpServers": {
    "tbcc": {
      "command": "py",
      "args": ["-3.13", "C:/Powercore-repo-main/telegram_bot2/tbcc/mcp-server/server.py"],
      "env": {
        "TBCC_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

Use your real repo path. Optional: set `TBCC_INTERNAL_API_KEY` in `env` if you rely on it for future authenticated routes (most TBCC dashboard APIs are open on localhost today).

Restart Cursor after saving. Run tool **`tbcc_health`** to confirm connectivity.

## Tools

| Tool | Purpose |
|------|---------|
| `tbcc_health` | Ping API |
| `list_channels` | Channel ids for scheduling |
| `list_pools` | Pools + approved counts |
| `list_scheduled_posts` | All jobs |
| `create_scheduled_post` | One-time or recurring job |
| `trigger_scheduled_post` | Post now (needs Celery) |
| `schedule_recurring_campaign` | Rotating captions + pool album |
| `list_media` | Library search |
| `suggest_pool_album` | Facet-based album ids |
| `list_caption_snippets` / `bulk_create_caption_snippets` | Caption library |
| `import_media_url` | `POST /import/url` |
| `analytics_*` | Subscriptions + outbound post log |
| `analytics_weekly_summary` | Markdown recap for Slack/Discord |

Pair with **Buffer MCP** (`https://mcp.buffer.com/mcp`) for X/IG/Threads queue outside TBCC’s Telegram-first mirror.

## Loot God card media MCP (`tbcc-loot-media`)

Separate server for **Gemini image gen + border animation bulk export** (no TBCC API required).

See **[docs/LOOT_CARD_MEDIA_MCP.md](../docs/LOOT_CARD_MEDIA_MCP.md)** for setup, staging workflow, and tool list.

```json
"tbcc-loot-media": {
  "command": "py",
  "args": ["-3.13", "C:/Powercore-repo-main/telegram_bot2/tbcc/mcp-server/loot_media_server.py"],
  "env": {
    "TBCC_LOOT_TIER_CARD_DIR": "C:/Powercore-repo-main/telegram_bot2/tbcc/backend/app/data/loot_tier_cards"
  }
}
```

Quick test in Cursor: **`loot_pipeline_spec`** then **`loot_bulk_greenlight`** with `import_incoming=false`.

## Example prompts

**Recurring pool campaign + Buffer mirror**

> List channels and pools. Create a recurring campaign on channel 1, pool 2, every 360 minutes, with these three captions: […]. Enable buffer_mirror. Then trigger once to test.

**Week plan from snippets**

> List caption snippets. Bulk-add these new ones: […]. Schedule a recurring job with content_variations from snippet bodies 1–5.

**Ops report**

> Run analytics_weekly_summary for 7 days and shorten it for Discord under 1900 characters.

## Environment

| Variable | Default |
|----------|---------|
| `TBCC_API_URL` | `http://127.0.0.1:8000` |
| `TBCC_INTERNAL_API_KEY` | optional `X-TBCC-Internal-Key` header |

Loaded from `tbcc/.env` when present.
