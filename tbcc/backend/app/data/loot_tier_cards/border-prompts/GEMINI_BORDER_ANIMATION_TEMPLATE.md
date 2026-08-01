# AOF LOOT GOD — Gemini Border Animation Master Prompt

Copy everything inside the fenced block below into Gemini. Fill in the `[VARIANT]` sections at the bottom.

---

```
PROJECT: AOF LOOT GOD — animated card BORDER overlay for Telegram loot reveals
ROLE: Generate a SINGLE animated card frame/border. This is chrome ONLY.

═══════════════════════════════════════════════════════════════════════════════
COMPOSITION LOCK — READ BEFORE ANYTHING ELSE
═══════════════════════════════════════════════════════════════════════════════

The card border chrome must be FULL-BLEED: it touches all four edges of the canvas.
There is NO margin, NO gutter, NO padding, NO floating card in empty space.

The video contains EXACTLY two types of pixels:
  A) Card border chrome (metal frame + three blank plates)
  B) Flat solid chroma magenta #FF00FF (RGB 255,0,255)

ZONE B RULE — ABSOLUTE ZERO TOLERANCE:
Any pixel OUTSIDE the outermost edge of the card chrome must be ONLY flat #FF00FF.
There cannot be ANYTHING visible outside the border frame. Not even one pixel of:
  • sparks, particles, dust, embers, shards, debris, smoke, mist, frost
  • glow, bloom, halos, light spill, lens flare, god rays
  • shadows, vignette, gradients, texture, noise, grain, film dirt
  • stars, icons, symbols, watermarks, UI elements, decorations
  • floor, pedestal, environment, depth, bokeh, background scenery
  • partial border fragments, second cards, corner ornaments in the matte

If an effect originates on the frame, it must be CLIPPED at the outer chrome silhouette.
Effects must NEVER extend into Zone B. Debris must dissolve BEFORE reaching the canvas edge.

The outer matte must look like a flat Photoshop fill: 100% uniform #FF00FF,
no variation, no animation, no movement, no shimmer — for EVERY frame of the video.

CENTER WINDOW RULE:
After the opening animation completes, the center window must be ONLY flat #FF00FF.
No metal, no texture, no gradient, no reflection, no art — empty chroma hole only.

═══════════════════════════════════════════════════════════════════════════════
CRITICAL — CONTENT RULES
═══════════════════════════════════════════════════════════════════════════════

- Output ONE card only. NOT a grid. NOT a filmstrip. NOT multiple panels. NOT a collage.
- The CENTER WINDOW must stay completely empty — flat solid magenta #FF00FF only.
- DO NOT draw any person, body, face, room, object, or artwork inside the center window.
- DO NOT draw readable text, tier numbers, names, logos, or watermarks anywhere.
- Code will stamp "AOF LOOT", "TIER N", and card name at runtime — leave blank plates only.

═══════════════════════════════════════════════════════════════════════════════
CARD LAYOUT (fixed every time)
═══════════════════════════════════════════════════════════════════════════════

- Canvas: 1024×1024 square (NOT 16:9, NOT 1280×720, NOT widescreen)
- OUTPUT MUST BE 1024×1024 SQUARE. Reject widescreen. Card fills the square edge-to-edge.
- Card chrome: edge-to-edge full bleed — outer metal rim touches canvas border on all sides
- Center window: large square hole, ~68% of canvas width, filled ONLY with #FF00FF after open
- There is NO "background scene" — only chrome + flat magenta matte
- Top-left: [VARIANT: top-left plate description] — blank, no text
- Top-right: [VARIANT: top-right plate description] — blank, no text
- Bottom band: [VARIANT: bottom nameplate description] — blank, no text
- Border chrome: [VARIANT: frame material + accent colors + aesthetic keywords]

═══════════════════════════════════════════════════════════════════════════════
STYLE — [VARIANT NAME]
═══════════════════════════════════════════════════════════════════════════════

[VARIANT: style paragraph — materials, mood, lighting, TCG energy]

- Dark cyberpunk / wet vinyl / industrial vault aesthetic (adjust per variant)
- Hyper-detailed 3D game UI asset, 8k UHD product shot, sharp focus
- Premium adult TCG pack-opening energy
- NOT cartoon. NOT anime. NOT childish.

═══════════════════════════════════════════════════════════════════════════════
ANIMATION — ONE CLIP, TWO SECTIONS (single file, 4.0 seconds @ 24fps)
═══════════════════════════════════════════════════════════════════════════════

SECTION A — OPENING (frames 0–36, 1.5s):
- Start: [VARIANT: opening mechanic — what blocks the center at frame 0]
- Animate: [VARIANT: how the center opens — smooth ease-out, vault precision]
- All opening VFX (shards, embers, foil, gates) must stay inside center window
  or inside border chrome volume — NEVER in Zone B
- End: fully open frame with flat #FF00FF center, blank plates visible
- Camera: locked off, no zoom, no shake

SECTION B — STASIS LOOP (frames 37–96, 2.5s, seamless):
- Frame stays open — center stays flat #FF00FF, never fills with content
- Border-only motion:
  • [VARIANT: primary pulse/glow — ~1.5s period, on chrome only]
  • [VARIANT: sparkle behavior — 2–3 blinks per loop, ON rivets/corners only]
  • [VARIANT: optional subtle sweep — metal surface only, low amplitude]
- NO gate re-closing, NO frame drift, NO center content
- Last stasis frame must match first stasis frame for seamless loop

OUTER MATTE FROZEN FOR ENTIRE CLIP:
- Zone B (#FF00FF outside chrome) must be pixel-identical in every frame.
- Opening VFX may ONLY occur inside the center window or inside border chrome.
- Stasis sparkles/pulses must occur ON metal frame surfaces only,
  never floating in the magenta surround.

═══════════════════════════════════════════════════════════════════════════════
TECHNICAL OUTPUT
═══════════════════════════════════════════════════════════════════════════════

- Resolution: 1024×1024 square
- Framerate: 24 fps
- Duration: 4.0 seconds exactly (1.5s open + 2.5s stasis loop)
- Center + outer matte: pure #FF00FF throughout after open completes
- No anti-aliased colored fringe on outer silhouette
- No letterboxing, pillarbox, or cinematic bars
- No audio
- Prefer MP4 with magenta fill OR WebM VP9 with alpha

═══════════════════════════════════════════════════════════════════════════════
NEGATIVE PROMPT
═══════════════════════════════════════════════════════════════════════════════

floating card in empty space, small card centered in void, margins around card,
padding around frame, gutter between card and canvas edge, letterbox, pillarbox,
16:9 widescreen, 1280x720, cinematic aspect ratio,
ANYTHING outside the frame border, particles outside chrome, sparks in magenta area,
debris in background, shard outside frame, sparkle in corner of background,
star icon in matte, decoration outside border, ornament in chroma key area,
glow outside frame, bloom spill past silhouette, halo around card,
shadow under card, drop shadow on matte, vignette, gradient background,
textured magenta, animated magenta, shimmering magenta background,
metal filling center window, textured center, grey center, dark center hole,
gradient in center, reflection in center window, lunar texture in center,
environment, scene, floor, pedestal, studio background, depth behind card,
grid, collage, filmstrip, multiple cards, 2×2, 3×4, sheet layout, overlapping borders,
text, letters, words, numbers, glyphs, symbols, logos, watermark, signature, QR code,
"AOF LOOT", "TIER", readable UI,
person, human, woman, man, face, skin, body, nudity, NSFW, anatomy, creatures,
room, furniture, objects, art, photo, pattern inside center window,
checkerboard pattern, transparency grid,
cartoon, anime, 2D flat, sketch, painting, low resolution, pixelated, blurry,
distorted frame, asymmetric layout, camera zoom, camera shake, scene cut,
white flash, full-frame strobe, gate re-closing after open, center filling after open
```

---

## One-line fallback (character-limited tools)

```
Full-bleed card chrome touching all canvas edges; EVERY pixel outside the outer metal border must be flat uniform #FF00FF with ZERO visible content — no sparks, glow, shadows, particles, icons, or texture in the matte, ever, in any frame. 1024×1024 square. One card only. Empty magenta center after open. No text.
```

---

## Variant fill-in cheat sheet

Copy a row into the `[VARIANT]` slots above.

| Name | Frame chrome | Accents | Opening | Stasis |
|------|-------------|---------|---------|--------|
| **Brushed vault steel** | Brushed dark chrome, riveted gunmetal, cyan edge rails | `#00e5ff` | Twin vault doors slide apart | Cyan rails pulse; rivet sparkles |
| **Holographic godroll** | Iridescent oil-slick chrome, prism bevels | Full spectrum | Prismatic membrane shatters outward | Holographic color cycle on edges |
| **Bio-mechanical xeno** | Obsidian + synthetic sinew, crystalline shards | Crimson + UV | Bio iris petals unfurl | Vein-gold pulse in channels |
| **Gothic sacrificial iron** | Rusted iron, gothic filigree, scorched titanium | Amber `#ffb020` | Iron cathedral gates grind apart | Amber channel glow breathes |
| **Corroded amber forge** | Corroded industrial iron, slag-filled grooves | Amber `#ffb020` | Forge slab retracts upward | Amber pulse; embers in recesses only |
| **Obsidian violet neon** | Polished obsidian glass, void-black chrome | Violet `#8b5cf6` | Glass fractures, shards dissolve at rails | Violet channels pulse |
| **Gunmetal acid-green** | Riveted gunmetal vault panels | Acid green `#28ff7a` | 4-quadrant iris retracts | LED nodes pulse in sequence |
| **Frosted quartz ice** | Frosted quartz over void-steel | Ice-blue `#7dd3fc` | Crystal panels fold into housing | Fracture lines breathe |
| **Bone-ivory reliquary** | Bone-ivory + demonic obsidian filigree | Crimson `#dc2626` | Reliquary shutters grind apart | Crimson channel pulse |
| **Wet vinyl ultraviolet** | Dark wet-vinyl chrome | UV `#7c3aed` + green rivets | Molten foil peels to edges | UV underglow pulses |
| **Carbon fiber cyan** | Matte carbon weave, gunmetal bezels | Electric blue `#00b4ff` | Carbon shutter panels retract | LED channels breathe |
| **Luxe gold ethereal** | Polished gold, obsidian core rails | White glow `#f8fafc` | Gold iris blades open | Ethereal edge glow breathes |

---

## Correct vs wrong (reference)

```
CORRECT — full bleed, chrome touches canvas edges:
┌─────────────────────────────┐  ← canvas edge
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│  ← chrome touches top
│▓▓┌─────────────────┐▓▓▓▓▓▓▓│
│▓▓│    #FF00FF      │▓▓▓▓▓▓▓│  ← empty chroma center
│▓▓└─────────────────┘▓▓▓▓▓▓▓│
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│  ← chrome touches bottom
└─────────────────────────────┘
     Zone B = flat #FF00FF only. Nothing visible outside ▓.

WRONG: small card floating in magenta void with wide gutters
WRONG: sparks/debris/icons in the magenta outside the chrome
WRONG: metal/texture/grey fill in center window after open
WRONG: 1280×720 widescreen with letterboxing
```

---

## Post-import (TBCC)

After Gemini export, split for two-file pipeline:
- `0.0–1.5s` → `borders/open/{variant}_open.mp4`
- `1.5–4.0s` (loop) → `borders/stasis/{variant}_stasis.mp4`

Or use single 4.0s clip if pipeline updated to accept one file.
