# Telegram split-emoji design workflow

A structured guide for **learning** to design split-grid custom emoji packs. Use this while authoring; use [EMOJI-SPEC.md](./EMOJI-SPEC.md) for hard numbers the factory enforces.

---

## Core idea (read this first)

Telegram does not show your artwork at full resolution. It shows **small tiles** with **padding, scaling, and heavy compression**. A pack looks “pro” when you design for that end state—not for a 1080p monitor.

```text
Design for:     small size + compression + seams + loop sync
Not for:        cinematic detail, soft gradients, edge-to-edge splits
```

---

## Part 1 — Dimension rules

### 1.1 The three sizes you must track

| Layer | Size rule | Why it exists |
|-------|-----------|---------------|
| **Chat display** | ~100×100 logical per emoji | What users perceive in messages |
| **Upload tile** | **512×512 px** per cell (default) | Sweet spot: sharp enough, still compresses |
| **Master canvas** | `512 × cols` by `512 × rows` | One comp for the whole wall before split |

**Examples**

| Grid | Tiles | Master canvas |
|------|-------|---------------|
| 2×2 | 4 | 1024×1024 |
| 3×3 | 9 | 1536×1536 |
| 4×4 | 16 | 2048×2048 |
| 5×5 | 25 | 2560×2560 |

Factory default: `--tile-px 512`, `--cols` / `--rows` as chosen. Input is normalized to this canvas unless you pass `--no-normalize`.

### 1.2 Safe zone (non-negotiable for split walls)

Inside **each** 512×512 tile, treat the outer **8–10%** as a danger zone (factory default `--margin-pct 8`).

```text
┌──────────────────────── 512 ────────────────────────┐
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │  ← margin band
│ ░░  ┌─────────────────────────────────────┐  ░░ │
│ ░░  │                                     │  ░░ │
│ ░░  │     SAFE: faces, logos, key lines   │  ░░ │
│ ░░  │                                     │  ░░ │
│ ░░  └─────────────────────────────────────┘  ░░ │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└────────────────────────────────────────────────────┘
```

**Rules**

- No eyes, mouths, or hard outlines in the margin band.
- Seams between tiles should fall in **low-detail** areas (sky, flat color, blur), not across features.
- If the wall must look seamless in chat, **overlap content in the master** then crop with margin—never split flush edge-to-edge on important lines.

### 1.3 Master composition rules

- **Square master** for square grids (avoid mixing 16:9 source with 1:1 grid without planning letterboxing).
- Place the subject **slightly smaller than the full grid** so every tile keeps safe padding after split.
- For animated walls: compose on a **fixed frame size** from frame 0—do not reframe mid-loop.

### 1.4 When to change dimensions

| Symptom | Adjustment |
|---------|------------|
| Soft / mushy in chat | Author at 512, not 256; avoid upscaling tiny sources |
| Upload rejected / huge files | Shorter loop, higher `--crf`, simpler motion (not smaller canvas) |
| Clipping at tile edges | Increase `--margin-pct` or shrink subject in master |
| Misaligned wall in chat | Re-export master with locked dimensions; check grid cols/rows |

---

## Part 2 — Format and export timing

Think in **roles**, not one “best format” for everything.

### 2.1 Role of each format

| Format | Role in pipeline | Use when |
|--------|------------------|----------|
| **MP4 (H.264)** | Master edit + factory **input** | Default working master; widely supported |
| **GIF** | Avoid as master | No alpha quality, bad compression, poor color; only as rough reference |
| **WebM (VP9)** | Factory **output** + Telegram upload | Final per-tile asset |
| **WebP / PNG** | Static tiles or plates | Static packs; PNG for lossless plates, WebP for smaller static |
| **ProRes / high-bitrate intermediate** | Optional AE/Resolve export | Heavy stylize pass, then transcode to MP4 for factory |

**Rule:** Edit in **one master MP4** (or image sequence → MP4). Let the factory emit **VP9 WebM** per tile. Do not hand-upload raw GIFs for split animated walls.

### 2.2 Master MP4 export settings (before factory)

| Setting | Target | Notes |
|---------|--------|-------|
| Resolution | Exact master canvas (e.g. 2048×2048 for 4×4) | Matches grid math |
| Frame rate | **30 fps** (or 24 if stylistic) | Same fps for entire project |
| Duration | **2–4 s** per loop cycle | Longer = bigger files + mushier compression |
| Loop | Seamless loop in NLE **or** trim to clean loop in export | Loop point = frame 0 = last frame continuity |
| Color | Rec.709; high contrast grade | Survives VP9 better |
| Audio | None | Strip audio before factory |

**Export checklist (master MP4)**

- [ ] Width/height = `512 × cols` and `512 × rows`
- [ ] fps constant (30 recommended)
- [ ] Duration 2–4 s (one loop)
- [ ] Loop preview looks continuous
- [ ] No letterboxing surprises (or intentional bars baked in)
- [ ] Filename records grid: e.g. `wall_4x4_v03.mp4`

### 2.3 Animated tile timing (after split, at encode)

Factory flags: `--loop-sec` (default 3), `--fps` (default 30).

| Parameter | Target | Design implication |
|-----------|--------|-------------------|
| Loop length | **2–4 s** | One readable motion cycle |
| FPS | **24–30** | 60 fps rarely worth cost at emoji size |
| Sync across tiles | **Identical timecode** | Same master → split preserves sync; never re-time individual tiles by hand |
| Loop phase | All tiles start at t=0 | Master must loop as a whole |

**Animated wall rule:** If tile (0,0) blinks on frame 15, tile (1,0) must use the **same** frame 15 from the **same** master—not a separately exported clip.

### 2.4 Final WebM (factory output / Telegram)

| Property | Target |
|----------|--------|
| Codec | VP9 (`libvpx-vp9`) |
| Pixel format | `yuva420p` if you need transparency |
| Per-tile size | Aim **≤ 256 KB**; tighten if upload fails |
| Duration | Same as master trim (`--loop-sec`) |

**If upload fails:** increase `--crf`, reduce `--loop-sec`, simplify motion in master, re-export—do not only shrink resolution below 512 if clarity suffers.

### 2.5 Static split packs

| Stage | Format |
|-------|--------|
| Master | PNG or high-quality WebP, full canvas size |
| Factory | `python -m emoji_factory ... --static` → WebM or use PNG tiles per your upload path |
| Design | Even more margin discipline; no motion to hide seam errors |

---

## Part 3 — Design techniques that survive Telegram

### 3.1 Visual style (what reads well)

| Do | Avoid |
|----|--------|
| Thick outlines, cel shading, hard shadows | Film grain, fog, soft beauty blur |
| Limited palette, posterized gradients | Subtle skin texture, micro-detail |
| One clear silhouette per tile | Busy backgrounds in every cell |
| Neon / high contrast accents | Low-contrast gray-on-gray |
| Exaggerated edges (slightly oversharpened master) | Relying on fine highlight detail |

**Oversharpen trick:** Grade slightly **too sharp** in the master; Telegram’s encoder softens it back toward “normal.”

### 3.2 Motion (animated packs)

| Do | Avoid |
|----|--------|
| Slow, looping motion (blink, pulse, float) | Fast pans, shake, zoom |
| One moving focal element | Many small moving parts |
| Motion centered in safe zone | Motion crossing tile borders |
| Ease in/out on loop point | Hard cuts unless intentional |

### 3.3 Split / seam strategy

1. **Plan the grid** on paper: which cells carry faces vs background.
2. **Hide seams** in hair, sky, or motion blur—not on noses or panel borders.
3. **Test in chat early** with a 2×2 before committing to 5×5.
4. Send tiles **in order** when previewing the wall (row-major matches factory `tile_00_00` …).

### 3.4 Grid size choice (creative, not only technical)

| Grid | Best for |
|------|----------|
| 2×2 | Bold, simple, fast iteration |
| 3×3 | Icons, logos, compact scenes |
| 4×4 | Most “emoji walls”; good chat width |
| 5×5 | Dense art; unforgiving seams and file budget |

---

## Part 4 — Formal workflow (learning path)

Use these stages in order. Each ends with a **gate**—do not skip gates on a pack you care about.

```text
Stage 0  Concept & grid plan
Stage 1  Master composition (dimensions + safe zones)
Stage 2  Stylize for compression (grade / effects)
Stage 3  Motion & loop proof
Stage 4  Export master MP4
Stage 5  Factory split + VP9 encode
Stage 6  Upload + in-chat test
Stage 7  Iterate (one variable at a time)
```

### Stage 0 — Concept and grid plan

**Goal:** Know what the wall says in chat before opening After Effects.

- Pick grid (start **4×4** unless you have a reason).
- Sketch which cells are “hero” vs “glue.”
- Mark seam lines on the sketch; move seams off features.

**Gate:** Written grid size + seam map approved by you.

---

### Stage 1 — Master composition

**Design sketchbook (TBCC dashboard):** On stage 1, the **Design sketchbook** panel stores paginated drafts in the database (not browser localStorage). Import from Telegram Saved Messages, edit, then **→ Emoji library** (telethon `<tg-emoji>` HTML) or **→ Caption library** for Scheduler.

**Goal:** One square comp at exact pixel dimensions.

- Create comp: `512×cols` × `512×rows` @ 30 fps.
- Scale subject to ~**80–85%** of full grid height/width.
- Enable guides at 8–10% inset **per cell** (or per-tile guide overlay).

**Gate:** Static frame screenshot looks good at **25% zoom** (simulates chat scale).

---

### Stage 2 — Stylize for compression

**Goal:** Art that still reads after VP9 and small display.

- Crush blacks / lift mids slightly for punch.
- Reduce fine texture (skin pores, fabric weave).
- Add outline or halftone if style allows.
- Optional: test **one** tile exported small before animating whole grid.

**Gate:** Single-tile test at 100×100 px still recognizable.

---

### Stage 3 — Motion and loop proof

**Goal:** Seamless 2–4 s loop, readable motion.

- Animate only what matters; keep rest static.
- Preview loop 10× in the NLE.
- Scrub grid seams while playing—features should not “crawl” across borders awkwardly.

**Gate:** Loop has no visible pop; motion readable at 25% zoom.

---

### Stage 4 — Export master MP4

**Goal:** Factory-ready input.

- Export per **§2.2** checklist.
- Name with version: `project_wall_4x4_v01.mp4`.

**Gate:** ffprobe shows correct resolution, ~30 fps, 2–4 s duration.

```powershell
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,duration -of csv=p=0 your_master.mp4
```

---

### Stage 5 — Factory split + encode

**Goal:** One WebM per tile + manifest.

```powershell
cd tbcc\services\emoji-factory
$env:PYTHONPATH = (Get-Location).Path
python -m emoji_factory -i C:\path\your_master.mp4 -o C:\path\pack-out --cols 4 --rows 4 --margin-pct 8 --loop-sec 3 --crf 38
```

Review `manifest.json`:

- [ ] Tile count = cols × rows
- [ ] `over_soft_limit` false (or you accept re-encode with higher `--crf`)

**Gate:** All tiles play locally; sizes within budget.

---

### Stage 6 — Upload and in-chat test

**Goal:** Real Telegram rendering, not just local files.

```powershell
cd tbcc\backend
python scripts/upload_emoji_pack_telethon.py --manifest C:\path\pack-out\manifest.json --short-name mypack_v01 --dry-run
# then real upload when ready
```

In a private chat:

- Send full wall in **grid order** (row by row).
- View on **phone and desktop** (scaling differs slightly).
- Check seams, clipping, timing sync.

**Gate:** Wall reads as one piece; no tile clips subject; animation in sync.

---

### Stage 7 — Iterate (controlled)

Change **one** knob per revision:

| Problem | Try first |
|---------|-----------|
| Seams visible | More margin in master; move seams; `--margin-pct` up |
| Too soft | Stronger outlines/contrast in master; slight oversharpen |
| Too large files | Shorter loop; higher `--crf`; simpler motion |
| Clipping | Smaller subject in master |
| Out of sync | Re-export single master MP4; never retime tiles individually |

Version files: `v01`, `v02`, … and note which knob changed.

**Gate:** v+1 fixes the issue without regressing previous gates.

---

## Part 5 — Quick reference card

### Dimensions

- Master: **512 × cols** by **512 × rows**
- Safe zone: **~8–10%** inset per tile
- Display assumption: design for **~100 px** perceived size

### Timing

- Master loop: **2–4 s**
- FPS: **30** (24 OK)
- One master → all tiles stay synced

### Formats

- Edit: **MP4** master
- Deliver: **WebM VP9** per tile (factory)
- Avoid: **GIF** as source of truth

### Design

- Chunky, contrast, simple motion
- Seams in low-detail areas
- Test at 25% zoom before upload

### TBCC commands

| Step | Command |
|------|---------|
| Encode tiles | `python -m emoji_factory -i master.mp4 -o out --cols 4 --rows 4` |
| Upload | `python scripts/upload_emoji_pack_telethon.py --manifest out/manifest.json ...` |

---

## Part 6 — Practice exercises (skill building)

1. **2×2 static face** — Learn margins only (no motion).
2. **2×2 blink loop** — Learn loop + sync (2 s).
3. **4×4 static landscape** — Learn seams across many cells.
4. **4×4 animated wall** — Full pipeline once.
5. **Revision drill** — Take a failed pack; fix only seams, re-run Stage 5–6.

---

## Related docs

- [EMOJI-SPEC.md](./EMOJI-SPEC.md) — numeric spec + upload notes
- [README.md](./README.md) — CLI and install
- **TBCC dashboard** — nav **Emoji packs** (`/emoji-factory`): staged checklist, gates, canvas calculator, factory CLI copy, upload dry-run
