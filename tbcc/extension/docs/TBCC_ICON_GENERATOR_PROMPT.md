# TBCC / Powercore icon — image generator prompt

Use this prompt in Midjourney, DALL·E, Ideogram, Flux, or similar. Export **1024×1024** (or vector), then downscale to **128 / 48 / 16 px** PNG with sharp edges (Lanczos). Place ailes in `tbcc/extension/icons/`.

---

## Primary prompt (recommended)

```
App icon for a developer media automation system named TBCC under the Powercore brand.
Square 1:1, rounded-corner app icon shape. Deep charcoal background #1e1e2e (Catppuccin Mocha base).
Center mark: a stylized power-core orb or lightning bolt fused with a minimal paper-plane / send glyph
(suggesting Telegram capture and export, not a literal Telegram logo).
Two-color palette only: electric blue #89b4fa and magenta pink #f5c2e7, high contrast.
Flat vector, minimal detail, bold silhouette readable at 16×16 pixels.
No text, no letters, no watermark, no photorealism, no busy gradients.
Professional dev-tool aesthetic, dark UI, subtle inner glow on the core only.
```

## Negative prompt

```
text, letters, words, watermark, blurry, noisy, photographic, 3d render, cluttered,
rainbow gradient, white background, rounded circle badge with photo,
copyright, realistic face, anime character
```

## Variant A — monogram-free mark

```
Minimal geometric icon: hexagonal power cell with a single diagonal lightning slash,
blue #89b4fa on dark #1e1e2e, pink #f5c2e7 accent dot at the bolt tip, flat design, 16px-safe.
```

## Variant B — capture pipeline metaphor

```
Abstract icon: three small media tiles funneling into one glowing core node,
colors #89b4fa and #f5c2e7 on #1e1e2e, flat vector, symmetric, no text.
```

## Export checklist

1. Edit the vector mark in `icons/tbcc-mark.svg` (flat blue hex + pink bolt, no gradients).
2. Run `python scripts/build-icons.py` from `tbcc/extension/` → writes **with-bg** PNGs to `icons/`, **transparent** PNGs to `icons/transparent/`, plus `favicon.ico`. Default `--mark-bleed 0.94` zooms the mark for Chrome toolbar legibility.
3. Reload extension in `chrome://extensions`.
4. Gallery favicon flyout uses `icons/` (with background); toolbar uses `icons/transparent/`.

## Brand lockup (UI text, not icon)

Extension nav uses **Powercore · TBCC** — Powercore in tertiary pink, TBCC in accent blue. Icon should feel like the same family without spelling either name.

---

A reference render may live at repo `assets/tbcc-icon-master.png`; production icons are in `tbcc/extension/icons/`.
