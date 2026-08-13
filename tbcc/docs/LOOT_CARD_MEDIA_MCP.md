# Loot God Card Media MCP

First-class pipeline for **bulk border animations**, **magenta marquee** chroma, and **badge-ready** `borders/open/*.mp4` imports — callable from Cursor without copy-pasting prompts.

## Enable in Cursor

Add to `~/.cursor/mcp.json` (merge with existing servers):

```json
"tbcc-loot-media": {
  "command": "py",
  "args": ["-3.13", "C:/Powercore-repo-main/telegram_bot2/tbcc/mcp-server/loot_media_server.py"],
  "env": {
    "TBCC_LOOT_TIER_CARD_DIR": "C:/Powercore-repo-main/telegram_bot2/tbcc/backend/app/data/loot_tier_cards"
  }
}
```

**Prerequisites**

- `tbcc/.env`: `TBCC_GEMINI_API_KEY` or `GEMINI_API_KEY`
- `py -3.13 -m pip install -r tbcc/mcp-server/requirements.txt`
- Backend deps for Gemini: `google-genai` (from `tbcc/backend` venv)
- **ffmpeg** on PATH (border import)

Restart Cursor → confirm tool `loot_pipeline_spec` works.

## Workflow (fast-track a full border set)

### 1. Greenlight staging + prompt pack

> Run `loot_bulk_greenlight` with write_prompts=true, import_incoming=false

Creates:

```
loot_tier_cards/_staging/
  prompts/borders/{stem}.txt     ← paste into Gemini for 4s video
  borders/incoming/              ← drop Gemini exports here
  frames/incoming/               ← optional static frame sheets
  manifest.json
```

### 2. Generate videos in Gemini

For each `{stem}.txt`: Gemini → **4.0s 1024²** clip, magenta `#FF00FF` matte, chrome only.

Save as: `_staging/borders/incoming/{stem}.mp4`

*(Gemini video is still manual/UI — API is image-only today. MCP automates prompts + import.)*

### 3. Bulk import → production

> Run `loot_import_border_staging`

- Auto-crops magenta gutters
- Scales to **512×512** H.264
- Writes `borders/open/{stem}.mp4`
- Ready for `TBCC_LOOT_BORDER_REVEAL=1` roll mux (center + chroma border + stamp)

### 4. Optional QA stills via API

> `loot_generate_border_preview` variant=`holographic_godroll`

Generates 1024² still preview before you commit to video export.

## MCP tools

| Tool | Purpose |
|------|---------|
| `loot_pipeline_spec` | Specs + staging paths |
| `loot_list_border_variants` | 25 variants + prod file exists? |
| `loot_build_border_prompt` | One full animation prompt |
| `loot_bulk_write_border_prompts` | All prompts → `_staging/prompts/borders/` |
| `loot_generate_gemini_image` | Generic Gemini still |
| `loot_generate_border_preview` | Variant QA still |
| `loot_generate_tier_center` | Tier center still for `centers/` bands |
| `loot_import_border_file` | Single clip → `borders/open/` |
| `loot_import_border_staging` | Bulk from `incoming/` |
| `loot_import_frame_staging` | Magenta chroma frames → `_rembg/` |
| `loot_bulk_greenlight` | One-shot operator flow |

## Example Cursor prompts

**New variant batch**

> List border variants missing production mp4. Bulk-write prompts for stems 01–05. Tell me where to drop Gemini exports.

**After Gemini session**

> Import everything in border staging incoming at 512px trim 4s. List which production clips are now live.

**Tier centers**

> Generate tier 7 and tier 10 center stills via loot_generate_tier_center execute=true.

## Code map

| Layer | Path |
|-------|------|
| MCP server | `mcp-server/loot_media_server.py` |
| Prompt builder | `backend/app/services/loot_border_prompt_builder.py` |
| Bulk pipeline | `backend/app/services/loot_card_mcp_pipeline.py` |
| Variant catalog | `app/data/loot_tier_cards/border-prompts/GEMINI_BORDER_25_VARIANTS.md` |
| Template | `.../GEMINI_BORDER_ANIMATION_TEMPLATE.md` |
| Roll-time mux | `loot_border_reveal.py`, `loot_preview_delivery.py` |

## Tests

```powershell
cd tbcc\backend
python -m pytest tests/test_loot_card_mcp_pipeline.py -q
```
