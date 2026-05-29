# TBCC Emoji Factory

Local pipeline for **split-grid Telegram custom emoji packs** (VP9 WebM tiles). Separate from TBCC caption `<tg-emoji>` presets in `telegram_custom_emoji.py`.

## Prerequisites

- **ffmpeg** and **ffprobe** on `PATH` (same as TBCC HLS import).
- For upload spike: logged-in **admin.session** (`cd tbcc/backend && python scripts/login_telethon_sessions.py`).

## Quick start

```powershell
cd tbcc\services\emoji-factory
$env:PYTHONPATH = (Get-Location)
python -m emoji_factory -i C:\path\master.mp4 -o C:\path\pack-out --cols 4 --rows 4
```

Output:

- `pack-out/tiles/tile_00_00.webm` …
- `pack-out/manifest.json` — tile paths, suggested emoji, byte sizes

**Learning / design rules:** [DESIGN-WORKFLOW.md](./DESIGN-WORKFLOW.md) — dimensions, export timing, design techniques, staged workflow with gates.  
**Hard numbers:** [EMOJI-SPEC.md](./EMOJI-SPEC.md).

## CLI flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--cols` / `--rows` | 4 / 4 | Grid size |
| `--tile-px` | 512 | Per-tile encode resolution |
| `--margin-pct` | 8 | Inset inside each cell (seam safety) |
| `--loop-sec` | 3 | Trim length per animated tile |
| `--crf` | 38 | VP9 quality (higher = smaller) |
| `--static` | off | One frame per tile |
| `--no-normalize` | off | Skip scaling input to `cols×tile_px` canvas |

## Upload (Telethon spike)

Dry-run (no Telegram I/O):

```powershell
cd tbcc\backend
python scripts/upload_emoji_pack_telethon.py --manifest C:\path\pack-out\manifest.json --dry-run
```

Create pack on your account (uses admin session):

```powershell
python scripts/upload_emoji_pack_telethon.py --manifest C:\path\pack-out\manifest.json `
  --title "My wall" --short-name my_wall_pack_abc123
```

`--short-name` must be unique globally (lowercase, digits, underscores). Script appends `_by_<your_user_id>` if missing.

## Roadmap

- Bot command `/pack_from_zip` (private bot, your user id)
- Dashboard panel + Celery for long encodes
- Auto `crf` sweep to hit byte budget
