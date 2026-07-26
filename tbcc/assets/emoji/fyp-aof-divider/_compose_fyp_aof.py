"""Compose FYP–AOF champagne-mosaic divider — static PNG + animated WebM emoji.

Letter-first pack (no equals/dash):
  F  Y  P  ·  ·  A  O  F

Telegram animated emoji: 100x100 WebM VP9, <=3s, no audio, target <=256KB.
Requires: Pillow; ffmpeg (libvpx-vp9) for .webm export.
"""
from __future__ import annotations

import math
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

TILE = 100
FPS = 12
DURATION_S = 2.75
N_FRAMES = max(8, int(round(FPS * DURATION_S)))
PALETTE = [
    (255, 252, 240),
    (252, 240, 210),
    (245, 228, 175),
    (232, 200, 120),
    (210, 170, 85),
    (180, 138, 62),
    (140, 105, 48),
]

GLYPHS: dict[str, list[str]] = {
    "F": [
        "###########",
        "###########",
        "##.........",
        "##.........",
        "##.........",
        "########...",
        "########...",
        "##.........",
        "##.........",
        "##.........",
        "##.........",
        "##.........",
        "##.........",
    ],
    "Y": [
        "##.......##",
        "##.......##",
        ".##.....##.",
        ".##.....##.",
        "..##...##..",
        "..##...##..",
        "...#####...",
        "....##.....",
        "....##.....",
        "....##.....",
        "....##.....",
        "....##.....",
        "....##.....",
    ],
    "P": [
        "##########.",
        "###########",
        "##.......##",
        "##.......##",
        "##.......##",
        "###########",
        "##########.",
        "##.........",
        "##.........",
        "##.........",
        "##.........",
        "##.........",
        "##.........",
    ],
    "A": [
        "...#####...",
        "..#######..",
        ".##.....##.",
        ".##.....##.",
        "##.......##",
        "##.......##",
        "###########",
        "###########",
        "##.......##",
        "##.......##",
        "##.......##",
        "##.......##",
        "##.......##",
    ],
    "O": [
        "..#######..",
        ".#########.",
        "##.......##",
        "##.......##",
        "##.......##",
        "##.......##",
        "##.......##",
        "##.......##",
        "##.......##",
        "##.......##",
        "##.......##",
        ".#########.",
        "..#######..",
    ],
}


def champagne_color(rng: random.Random, brightness: float = 1.0) -> tuple[int, int, int]:
    base = list(rng.choice(PALETTE))
    jitter = rng.uniform(-14, 20)
    rgb = [max(0, min(255, int(c + jitter))) for c in base]
    b = max(0.35, min(1.35, brightness))
    rgb = [max(0, min(255, int(c * b))) for c in rgb]
    return (rgb[0], rgb[1], rgb[2])


def glyph_cells(pattern: list[str]) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for r, line in enumerate(pattern):
        for c, ch in enumerate(line):
            if ch == "#":
                cells.append((r, c))
    return cells


def letter_motion(letter: str, r: int, c: int, rows: int, cols: int, t: float) -> float:
    """Return extra brightness offset for letter-specific therapeutic drift."""
    nr = r / max(1, rows - 1)
    nc = c / max(1, cols - 1)
    # Slow angular rates — calm by default.
    if letter == "F":
        # Left-edge cascade
        return 0.18 * math.sin(t * 1.1 + nr * 4.2 + nc * 0.4)
    if letter == "Y":
        # Forks converge toward stem
        dist = abs(nc - 0.5) + abs(nr - 0.55)
        return 0.16 * math.sin(t * 1.0 - dist * 5.0)
    if letter == "P":
        # Bowl pulse
        in_bowl = 1.0 if (nr < 0.55 and nc > 0.35) else 0.4
        return 0.17 * in_bowl * math.sin(t * 1.25 + nr * 3.0)
    if letter == "A":
        # Apex spark falls
        return 0.15 * math.sin(t * 0.95 + (1.0 - nr) * 5.5 + abs(nc - 0.5) * 2.0)
    if letter == "O":
        # Rotating ring phase
        ang = math.atan2(nr - 0.5, nc - 0.5)
        return 0.18 * math.sin(t * 1.15 + ang * 3.0)
    # F2 / default
    return 0.14 * math.sin(t * 1.05 + nr * 3.3 + nc * 2.1 + 1.7)


def render_glyph_frame(
    pattern: list[str],
    *,
    letter: str,
    seed: int,
    frame: int,
    n_frames: int,
    size: int = TILE,
    phase_offset: float = 0.0,
) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    rows = len(pattern)
    cols = max(len(r) for r in pattern)
    margin = size * 0.10
    usable = size - 2 * margin
    cell_w = usable / cols
    cell_h = usable / rows
    rad = min(cell_w, cell_h) * 0.42
    t = (frame / max(1, n_frames)) * math.pi * 2.0 + phase_offset

    for r, c in glyph_cells(pattern):
        cx = margin + (c + 0.5) * cell_w
        cy = margin + (r + 0.5) * cell_h
        cell_seed = seed + r * 97 + c * 31
        crng = random.Random(cell_seed)
        base_bright = 0.72 + 0.18 * crng.random()
        # Sparse darker spots (F-glyph negative space vibe)
        spot = 0.55 if ((cell_seed + frame // 3) % 11 == 0) else 1.0
        flutter = 0.12 * math.sin(t * 0.85 + crng.random() * 6.28)
        motion = letter_motion(letter, r, c, rows, cols, t)
        bright = max(0.32, min(1.28, base_bright * spot + flutter + motion))
        color = champagne_color(crng, bright)
        x0, y0 = cx - rad, cy - rad
        x1, y1 = cx + rad, cy + rad
        draw.ellipse([x0, y0, x1, y1], fill=color)
        if crng.random() < 0.75 + 0.15 * bright:
            gx = cx - rad * 0.35
            gy = cy - rad * 0.35
            gr = max(0.8, rad * 0.28)
            hi = (
                min(255, color[0] + 40),
                min(255, color[1] + 35),
                min(255, color[2] + 25),
            )
            draw.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=hi)

    bloom_r = max(1.0, size / 55.0)
    glow = img.filter(ImageFilter.GaussianBlur(radius=bloom_r))
    base = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    gr, gg, gb, ga = glow.split()
    ga = ga.point(lambda a: int(a * 0.40) if a > 30 else 0)
    glow = Image.merge("RGBA", (gr, gg, gb, ga))
    base = Image.alpha_composite(base, glow)
    base = Image.alpha_composite(base, img)
    return base


def render_spacer_frame(frame: int, n_frames: int, size: int = TILE) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    t = (frame / max(1, n_frames)) * math.pi * 2.0
    rng = random.Random(909 + frame // 4)
    for _ in range(5):
        x = rng.uniform(size * 0.2, size * 0.8)
        y = rng.uniform(size * 0.2, size * 0.8)
        a = int(18 + 14 * (0.5 + 0.5 * math.sin(t + x * 0.05)))
        r = 1.2
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(180, 150, 90, a))
    return img


def blank_tile(size: int = TILE) -> Image.Image:
    return Image.new("RGBA", (size, size), (0, 0, 0, 255))


def encode_webm(frame_dir: Path, out_webm: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("WARN: ffmpeg not found — skipping WebM for", out_webm.name)
        return False
    pattern = str(frame_dir / "f_%04d.png")
    # Try CRF ladder until under ~240KB
    for crf in (36, 40, 44, 48, 52):
        cmd = [
            ffmpeg,
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            pattern,
            "-c:v",
            "libvpx-vp9",
            "-pix_fmt",
            "yuva420p",
            "-an",
            "-b:v",
            "0",
            "-crf",
            str(crf),
            "-deadline",
            "good",
            "-cpu-used",
            "2",
            "-loop",
            "0",
            str(out_webm),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print("ffmpeg failed", out_webm.name, e.stderr[-400:] if e.stderr else e)
            return False
        if out_webm.stat().st_size <= 240_000:
            print(f"  webm {out_webm.name} crf={crf} {out_webm.stat().st_size}B")
            return True
    print(f"  webm {out_webm.name} oversized {out_webm.stat().st_size}B (kept)")
    return True


def write_letter_assets(letter_key: str, glyph_key: str, seed: int, phase: float = 0.0) -> Image.Image:
    """Write static PNG + animated frames/WebM. Returns mid-frame static for masters."""
    pattern = GLYPHS[glyph_key]
    mid = render_glyph_frame(
        pattern, letter=glyph_key, seed=seed, frame=N_FRAMES // 2, n_frames=N_FRAMES, phase_offset=phase
    )
    glyphs_dir = OUT / "glyphs"
    glyphs_dir.mkdir(exist_ok=True)
    mid.save(glyphs_dir / f"{letter_key}.png", "PNG")

    anim_root = OUT / "anim_frames" / letter_key
    if anim_root.exists():
        shutil.rmtree(anim_root)
    anim_root.mkdir(parents=True)
    for fi in range(N_FRAMES):
        fr = render_glyph_frame(
            pattern, letter=glyph_key, seed=seed, frame=fi, n_frames=N_FRAMES, phase_offset=phase
        )
        fr.save(anim_root / f"f_{fi:04d}.png", "PNG")
    webm_dir = OUT / "pack_unique"
    webm_dir.mkdir(exist_ok=True)
    encode_webm(anim_root, webm_dir / f"{letter_key}.webm")
    return mid


def main() -> None:
    # Unique letters — trailing F uses phase offset twin
    still = {
        "F": write_letter_assets("F", "F", 201, 0.0),
        "Y": write_letter_assets("Y", "Y", 301, 0.0),
        "P": write_letter_assets("P", "P", 401, 0.0),
        "A": write_letter_assets("A", "A", 501, 0.0),
        "O": write_letter_assets("O", "O", 601, 0.0),
        "F2": write_letter_assets("F2", "F", 701, 1.85),
    }

    # Spacer static + subtle anim
    spacer_still = blank_tile()
    (OUT / "glyphs").mkdir(exist_ok=True)
    spacer_still.save(OUT / "glyphs" / "spacer.png", "PNG")
    sp_frames = OUT / "anim_frames" / "spacer"
    if sp_frames.exists():
        shutil.rmtree(sp_frames)
    sp_frames.mkdir(parents=True)
    for fi in range(N_FRAMES):
        render_spacer_frame(fi, N_FRAMES).save(sp_frames / f"f_{fi:04d}.png", "PNG")
    encode_webm(sp_frames, OUT / "pack_unique" / "spacer.webm")
    still["spacer"] = spacer_still

    # Paste sequence: F Y P · · A O F  (no dash/equals)
    paste_keys = ["F", "Y", "P", "spacer", "spacer", "A", "O", "F2"]
    assert len(paste_keys) == 8

    for i, key in enumerate(paste_keys, start=1):
        still[key].save(OUT / f"tile_{i:02d}.png", "PNG")
    # Remove leftover tiles 09–14 from old 14-tile dash layout
    for orphan in OUT.glob("tile_*.png"):
        n = int(orphan.stem.split("_")[1])
        if n > len(paste_keys):
            orphan.unlink()

    master_w = TILE * len(paste_keys)
    master = Image.new("RGBA", (master_w, TILE), (0, 0, 0, 255))
    for i, key in enumerate(paste_keys):
        master.paste(still[key], (i * TILE, 0))
    master.save(OUT / "master.png", "PNG")

    preview = Image.new("RGBA", (master_w + 40, TILE + 40), (0, 0, 0, 255))
    preview.paste(master, (20, 20))
    preview.save(OUT / "master_preview.png", "PNG")

    scale = 3
    hi = {
        k: render_glyph_frame(
            GLYPHS[gk],
            letter=gk,
            seed=sd,
            frame=N_FRAMES // 2,
            n_frames=N_FRAMES,
            size=TILE * scale,
            phase_offset=ph,
        )
        for k, gk, sd, ph in [
            ("F", "F", 201, 0.0),
            ("Y", "Y", 301, 0.0),
            ("P", "P", 401, 0.0),
            ("A", "A", 501, 0.0),
            ("O", "O", 601, 0.0),
            ("F2", "F", 701, 1.85),
        ]
    }
    hi["spacer"] = blank_tile(TILE * scale)
    master_hi = Image.new("RGBA", (master_w * scale, TILE * scale), (0, 0, 0, 255))
    for i, key in enumerate(paste_keys):
        master_hi.paste(hi[key], (i * TILE * scale, 0))
    master_hi.save(OUT / "master_300px.png", "PNG")

    pack_dir = OUT / "pack_unique"
    pack_dir.mkdir(exist_ok=True)
    # Preferred Remixer upload order (static PNG + matching WebM)
    pack_order = ["F", "Y", "P", "A", "O", "F2", "spacer"]
    for i, key in enumerate(pack_order, start=1):
        still[key].save(pack_dir / f"pack_{i:02d}_{key}.png", "PNG")

    # Drop obsolete dash glyph if present
    dash_png = OUT / "glyphs" / "dash.png"
    if dash_png.exists():
        dash_png.unlink()
    for p in pack_dir.glob("*dash*"):
        p.unlink()

    print("OUT", OUT)
    print("sequence", paste_keys)
    print("frames", N_FRAMES, "fps", FPS)
    print("pack_unique", pack_order)
    for p in sorted(OUT.glob("tile_*.png")):
        im = Image.open(p)
        assert im.size == (100, 100), (p, im.size)
    print("all tiles 100x100 OK")


if __name__ == "__main__":
    main()
