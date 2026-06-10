"""Gallery-style percent crop + blur bands (watermark removal) for album composer sends."""
from __future__ import annotations

import io
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class NormRect(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class ImageCropSettings(BaseModel):
    """Matches extension gallery cropBottom* + blur regions (photos only)."""

    enabled: bool = False
    inset_percent: int = Field(default=0, ge=0, le=49)
    inset_mode: str = Field(default="all", description="all|top|right|bottom|left")
    blur_regions: list[NormRect] = Field(default_factory=list)

    @field_validator("inset_mode")
    @classmethod
    def _norm_mode(cls, v: str) -> str:
        m = (v or "all").strip().lower()
        if m in ("all", "sides", "everywhere", "every", "each"):
            return "all"
        if m in ("top", "right", "bottom", "left"):
            return m
        return "all"

    def applies(self) -> bool:
        if not self.enabled:
            return False
        if self.inset_percent > 0:
            return True
        return bool(self.blur_regions)


def inset_percents(percent: int, mode: str) -> dict[str, int]:
    p = max(0, min(49, int(percent)))
    m = (mode or "all").lower()
    if m == "top":
        return {"top": p, "right": 0, "bottom": 0, "left": 0}
    if m == "right":
        return {"top": 0, "right": p, "bottom": 0, "left": 0}
    if m == "bottom":
        return {"top": 0, "right": 0, "bottom": p, "left": 0}
    if m == "left":
        return {"top": 0, "right": 0, "bottom": 0, "left": p}
    return {"top": p, "right": p, "bottom": p, "left": p}


def blur_band_rect(side: str, percent: int) -> NormRect:
    """Blur strip on one edge (common watermark band)."""
    p = max(1, min(49, int(percent))) / 100.0
    side = side.lower()
    if side == "top":
        return NormRect(x=0, y=0, w=1, h=p)
    if side == "bottom":
        return NormRect(x=0, y=1 - p, w=1, h=p)
    if side == "left":
        return NormRect(x=0, y=0, w=p, h=1)
    if side == "right":
        return NormRect(x=1 - p, y=0, w=p, h=1)
    return NormRect(x=0, y=1 - p, w=1, h=p)


def parse_crop_phrase(text: str) -> ImageCropSettings | Literal["off"]:
    """
    Plain-language crop / watermark commands.

    Examples:
      8% bottom, crop 10% top, trim 8 percent all sides
      blur bottom 12%, blur 8% right
      off / clear / disable
    """
    raw = (text or "").strip()
    if not raw:
        return "off"
    t = raw.lower()
    if t in ("off", "none", "no", "disable", "clear", "reset", "no crop", "crop off"):
        return "off"

    cfg = ImageCropSettings(enabled=True)
    side_words = r"(?:top|bottom|left|right|all|sides|everywhere|each)"
    pct = r"(\d{1,2})\s*(?:%|percent|pct)?"

    crop_pat = re.compile(
        rf"(?:crop|trim|cut|inset|remove|strip)(?:\s+{pct})?\s*(?:from\s+)?({side_words})|"
        rf"(?:crop|trim|cut|inset|remove|strip)\s+({side_words})\s+{pct}|"
        rf"^{pct}\s*(?:from\s+)?({side_words})|"
        rf"^({side_words})\s+{pct}",
        re.I,
    )
    m = crop_pat.search(t)
    if m:
        groups = [g for g in m.groups() if g]
        nums = [g for g in groups if g.isdigit()]
        sides = [g for g in groups if not g.isdigit()]
        if nums:
            cfg.inset_percent = max(0, min(49, int(nums[0])))
        if sides:
            cfg.inset_mode = sides[0].replace("sides", "all").replace("everywhere", "all").replace("each", "all")

    blur_pat = re.compile(
        rf"blur\s+({side_words})\s+{pct}|blur\s+{pct}\s*(?:on\s+)?({side_words})",
        re.I,
    )
    for bm in blur_pat.finditer(t):
        g = [x for x in bm.groups() if x]
        if len(g) == 2:
            if g[0].isdigit():
                pct_v, side_v = int(g[0]), g[1]
            else:
                side_v, pct_v = g[0], int(g[1])
            cfg.blur_regions.append(blur_band_rect(side_v, pct_v))

    if cfg.inset_percent > 0 or cfg.blur_regions:
        return cfg

    if re.search(r"\bwatermark", t):
        cfg.inset_percent = 8
        cfg.inset_mode = "bottom"
        return cfg

    return "off"


def crop_status_label(cfg: ImageCropSettings | None) -> str:
    if not cfg or not cfg.applies():
        return "off"
    parts: list[str] = []
    if cfg.inset_percent > 0:
        mode = cfg.inset_mode if cfg.inset_mode != "all" else "all sides"
        parts.append(f"{cfg.inset_percent}% {mode}")
    if cfg.blur_regions:
        parts.append(f"blur×{len(cfg.blur_regions)}")
    return ", ".join(parts) if parts else "on"


def apply_image_crop_pipeline(data: bytes, cfg: ImageCropSettings | None) -> bytes:
    """Apply inset crop + blur regions; returns JPEG bytes for photos."""
    if not cfg or not cfg.applies():
        return data

    from PIL import Image, ImageFilter, ImageOps

    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    elif im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg

    w0, h0 = im.size
    if w0 < 2 or h0 < 2:
        return data

    if cfg.inset_percent > 0:
        inset = inset_percents(cfg.inset_percent, cfg.inset_mode)
        off_l = int(w0 * inset["left"] / 100)
        off_r = int(w0 * inset["right"] / 100)
        off_t = int(h0 * inset["top"] / 100)
        off_b = int(h0 * inset["bottom"] / 100)
        x1, y1 = off_l, off_t
        x2, y2 = max(x1 + 1, w0 - off_r), max(y1 + 1, h0 - off_b)
        im = im.crop((x1, y1, x2, y2))

    cw, ch = im.size
    for br in cfg.blur_regions:
        bx = int(br.x * cw)
        by = int(br.y * ch)
        bw = max(1, int(br.w * cw))
        bh = max(1, int(br.h * ch))
        bx = max(0, min(bx, cw - 1))
        by = max(0, min(by, ch - 1))
        bw = min(bw, cw - bx)
        bh = min(bh, ch - by)
        if bw < 2 or bh < 2:
            continue
        region = im.crop((bx, by, bx + bw, by + bh))
        region = region.filter(ImageFilter.GaussianBlur(radius=14))
        im.paste(region, (bx, by))

    out = io.BytesIO()
    im.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()
