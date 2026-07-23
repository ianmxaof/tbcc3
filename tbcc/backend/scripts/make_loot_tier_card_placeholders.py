"""Starter AOF loot tier cards (chrome-first; swap with Perchance art later).

  py -3.13 scripts/make_loot_tier_card_placeholders.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "loot_tier_cards"

TIERS = [
    (1, "CRUMB", "1-1", "Barely a taste. Still counts.", (90, 110, 95)),
    (2, "PEEK", "1-2", "Skirt lifts. Nothing promised.", (70, 120, 180)),
    (3, "LEAK", "1-3", "Someone left the door cracked.", (180, 120, 60)),
    (4, "THROB", "2-1", "The room starts breathing with you.", (160, 60, 90)),
    (5, "DRIP", "2-2", "Mid-heat. You're not leaving yet.", (220, 60, 140)),
    (6, "SOAK", "3-1", "Mixed media. Density climbing.", (40, 160, 140)),
    (7, "FILTH", "4-1", "Vault opens. Packs may follow.", (80, 200, 70)),
    (8, "RUIN", "5-1", "Density spikes. No soft landing.", (200, 40, 40)),
    (9, "BLACKOUT", "6-1", "Near-mythic. Modifiers stack mean.", (120, 40, 200)),
    (10, "GODROLL", "★", "MAX TIER — screenshot the mess.", (220, 170, 40)),
]


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _radial_glow(size: int, color: tuple[int, int, int], strength: float = 0.55) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    cx = cy = size / 2
    max_r = size * 0.48
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / max_r
            if d >= 1:
                continue
            a = int(255 * strength * (1 - d) ** 2)
            px[x, y] = (color[0], color[1], color[2], a)
    return img.filter(ImageFilter.GaussianBlur(radius=18))


def _draw_card(n: int, name: str, world: str, tag: str, neon: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (1024, 1024), (6, 6, 10))
    base = img.convert("RGBA")
    glow = _radial_glow(900, neon, 0.45 + n * 0.03)
    base.alpha_composite(glow, dest=(62, 62))
    d = ImageDraw.Draw(base)

    for i in range(36):
        c = tuple(max(0, min(255, v - i * 3)) for v in neon)
        d.rectangle([i, i, 1023 - i, 1023 - i], outline=c + (255,))

    d.rectangle([56, 56, 967, 967], outline=(40, 40, 48, 255), width=3)
    # Center window
    win = [140, 160, 884, 720]
    d.rounded_rectangle(win, radius=22, fill=(12, 12, 18, 255), outline=neon + (255,), width=5)
    # Fake sealed pack motif
    cx, cy = 512, 440
    d.rounded_rectangle(
        [cx - 150, cy - 190, cx + 150, cy + 190],
        radius=24,
        fill=(16, 16, 22, 255),
        outline=neon + (255,),
        width=4,
    )
    d.ellipse([cx - 78, cy - 40, cx + 78, cy + 100], fill=(neon[0] // 4, neon[1] // 4, neon[2] // 4, 255))
    d.ellipse([cx - 42, cy - 10, cx + 42, cy + 60], fill=neon + (255,))
    d.rectangle([cx - 110, cy + 8, cx + 110, cy + 36], fill=(8, 8, 12, 255))
    d.text((cx, cy + 22), "SEALED", font=_font(24), fill=neon + (255,), anchor="mm")

    # ASCII residue
    d.text((160, 180), "········", font=_font(18), fill=(neon[0] // 2, neon[1] // 2, neon[2] // 2, 180))
    d.text((780, 680), "ROLL OK", font=_font(16), fill=(neon[0] // 2, neon[1] // 2, neon[2] // 2, 180))

    d.text((72, 72), "AOF LOOT", font=_font(34), fill=(220, 220, 225, 255))
    d.text((952, 72), f"TIER {n} · {world}", font=_font(32), fill=neon + (255,), anchor="ra")
    d.text((512, 800), name, font=_font(70), fill=(245, 245, 248, 255), anchor="mm")
    d.text((512, 880), tag, font=_font(26), fill=(170, 170, 180, 255), anchor="mm")
    d.text((512, 940), "LOOT GOD · STARTER SET", font=_font(18), fill=(90, 90, 100, 255), anchor="mm")
    return base.convert("RGB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for n, name, world, tag, neon in TIERS:
        img = _draw_card(n, name, world, tag, neon)
        path = OUT / f"tier-{n}.png"
        img.save(path, "PNG", optimize=True)
        print(f"{path.name}\t{path.stat().st_size}")
    print(f"wrote {len(list(OUT.glob('tier-*.png')))} cards -> {OUT}")


if __name__ == "__main__":
    main()
