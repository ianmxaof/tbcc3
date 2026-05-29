# Telegram custom emoji pack spec (TBCC emoji factory)

This documents **hard targets** for split-grid custom emoji packs (not caption `<tg-emoji>` presets).

For dimensions, export timing, design techniques, and a staged learning workflow, see **[DESIGN-WORKFLOW.md](./DESIGN-WORKFLOW.md)**.

## Display vs upload size

| Stage | Size | Notes |
|-------|------|--------|
| Chat display | ~100×100 logical | Telegram scales and pads tiles |
| Authoring tile | **512×512** | Common pro standard before upload |
| Master canvas | `512 × cols` × `512 × rows` | e.g. 4×4 → 2048×2048 |

## Safe margins

- Keep focal art **5–10%** away from each tile edge.
- Factory default: `--margin-pct 8` shrinks the crop inside each cell.
- For seamless walls: upscale master, split with overlap, keep seams in low-detail zones.

## Animated tiles (recommended)

| Property | Target |
|----------|--------|
| Container | `.webm` |
| Codec | **VP9** (`libvpx-vp9`) |
| Pixel format | `yuva420p` when transparency matters |
| FPS | 24–30 (30 default) |
| Loop length | **2–4 s** |
| Per-tile size | **≤ 256 KB** goal; tighten `crf` / duration if upload fails |
| Motion | Simple loops; avoid fast pan and fine grain |

## Static tiles

- PNG or WebP with alpha; encode pass can still output WebM for a unified pack.
- Or upload PNG via the same pipeline with `--static`.

## Grid layouts

| Layout | Tiles |
|--------|-------|
| 2×2 | 4 |
| 3×3 | 9 |
| 4×4 | 16 |
| 5×5 | 25 |

Telegram allows up to **200** stickers per set; custom emoji sets follow sticker-set limits.

## Upload (Telethon spike)

- Uses **admin.session** (same as TBCC imports).
- `CreateStickerSetRequest(..., emojis=True)` creates a **custom emoji** set owned by your account.
- Short name: lowercase, digits, underscores; must end with `_by_<bot_or_user>` when created via bot — for user-owned sets use a unique suffix (see script).
- After creation, open **Settings → My Profile → Emoji** or search the pack short name in **@Stickers**.

## Iteration loop

```text
MP4 master → stylize (AE/Resolve) → split (factory) → encode VP9 → upload → test in chat → adjust margin/crf/grid
```

Prefer external quality control; use Telegram bots only for upload when possible.
