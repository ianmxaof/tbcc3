# FYP — AOF champagne mosaic divider (v2 animated)

**Status:** **published** as `fyp_aof_divider_v2_by_7787282561` — open Saved Messages preview or https://t.me/addemoji/fyp_aof_divider_v2_by_7787282561 then Add emoji.

**Style:** champagne LED mosaic **letters** on pure black, with calm letter-specific twinkle loops. **No equals / dash tiles** (v1 experimental `=` retired).

## Layout

```
tile  01 02 03 04 05 06 07 08
glyph F  Y  P  ·  ·  A  O  F2
```

- Left triad: `F Y P`
- Center gap: 2× `spacer` (clear break between **P** and **A**)
- Right triad: `A O F2` (trailing F is phase-offset twin of F)
- Total sequence tiles: **8** × **100×100**
- Unique pack: **7** (`F`, `Y`, `P`, `A`, `O`, `F2`, `spacer`)

## Animation (Telegram custom emoji)

| Spec | Value |
|------|--------|
| Size | 100×100 |
| Format | WebM VP9 + alpha (`yuva420p`), no audio |
| Duration | ~2.75s loop @ 12 fps |
| Size budget | each `.webm` well under 256KB (typically ~8–12KB) |

Letter motion (therapeutic, not frantic):

- **F** — left-edge cascade  
- **Y** — forks converge toward stem  
- **P** — bowl pulse  
- **A** — apex spark falls  
- **O** — rotating ring phase  
- **F2** — same as F with phase offset  

## Paths

| File | Role |
|------|------|
| `master.png` | 800×100 stitch of paste order |
| `master_300px.png` | 3× hi-res preview |
| `master_preview.png` | padded black preview |
| `tile_01.png` … `tile_08.png` | paste-order static frames |
| `glyphs/*.png` | unique static glyphs |
| `pack_unique/pack_0N_*.png` | static Remixer set |
| `pack_unique/{F,Y,P,A,O,F2,spacer}.webm` | **animated** upload set |
| `anim_frames/` | frame PNG scratch (regenerated; optional keep) |
| `_compose_fyp_aof.py` | regenerate script |

Re-run:

```powershell
python tbcc\assets\emoji\fyp-aof-divider\_compose_fyp_aof.py
```

Requires `ffmpeg` with `libvpx-vp9` on PATH.

## Remixer upload (operator — tray-owned Telethon)

Do **not** agent-spawn a competing session.

### Unique pack upload order

| # | Static | Animated | Suggested name |
|---|--------|----------|----------------|
| 1 | `pack_01_F.png` | `F.webm` | `fyp_F` |
| 2 | `pack_02_Y.png` | `Y.webm` | `fyp_Y` |
| 3 | `pack_03_P.png` | `P.webm` | `fyp_P` |
| 4 | `pack_04_A.png` | `A.webm` | `fyp_A` |
| 5 | `pack_05_O.png` | `O.webm` | `fyp_O` |
| 6 | `pack_06_F2.png` | `F2.webm` | `fyp_F2` |
| 7 | `pack_07_spacer.png` | `spacer.webm` | `fyp_gap` |

Prefer uploading **WebM** for animated custom emoji when the Remixer / BotFather flow accepts video emoji. Keep PNGs as fallback / preview.

### Footer paste sequence (once pack is live)

```text
:fyp_F: :fyp_Y: :fyp_P: :fyp_gap: :fyp_gap: :fyp_A: :fyp_O: :fyp_F2:
```

## Do not

- Claim live publish to `@aofmainhub` from this staging pass
- Open a second `admin.session` while tray scrape/emoji upload is running
- Reintroduce dash/`=` tiles without a new design pass
