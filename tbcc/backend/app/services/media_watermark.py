"""Burn-in promo text watermark for images and videos (Pillow + ffmpeg)."""

from __future__ import annotations

import contextvars
import io
import logging
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.services.media_frame_sample import ffmpeg_available
from app.services.media_sniff import sniff_media_kind

logger = logging.getLogger(__name__)

WatermarkPosition = Literal[
    "bottom_right",
    "upper_right",
    "upper_left",
    "bottom_left",
    "center_diagonal",
]

POSITIONS: tuple[WatermarkPosition, ...] = (
    "bottom_right",
    "upper_right",
    "upper_left",
    "bottom_left",
    "center_diagonal",
)

_skip_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar("tbcc_skip_watermark", default=False)
_config_ctx: contextvars.ContextVar["WatermarkApplyConfig | None"] = contextvars.ContextVar(
    "tbcc_watermark_config", default=None
)
_rotate_lock = threading.Lock()
_rotate_index = 0

MULTI_TEXT_POSITIONS: tuple[WatermarkPosition, ...] = (
    "bottom_right",
    "bottom_left",
    "upper_right",
)


@dataclass(frozen=True)
class WatermarkApplyConfig:
    enabled: bool = True
    texts: tuple[str, ...] = ()
    opacity: float = 0.58
    color_hex: str = "#FFFFFF"
    mode: str = "rotate"
    position: WatermarkPosition = "bottom_right"
    strip_previous: bool = False
    skip: bool = False


class _SkipContext:
    def __init__(self, skip: bool):
        self._skip = skip
        self._token = None

    def __enter__(self):
        self._token = _skip_ctx.set(bool(self._skip))
        return self

    def __exit__(self, *_args):
        if self._token is not None:
            _skip_ctx.reset(self._token)


def skip_watermark_context(skip: bool = True) -> _SkipContext:
    return _SkipContext(skip)


class _ConfigContext:
    def __init__(self, config: WatermarkApplyConfig | None):
        self._config = config
        self._token = None

    def __enter__(self):
        self._token = _config_ctx.set(self._config)
        return self

    def __exit__(self, *_args):
        if self._token is not None:
            _config_ctx.reset(self._token)


def watermark_config_context(config: WatermarkApplyConfig | None) -> _ConfigContext:
    return _ConfigContext(config)


def parse_color_hex(raw: str | None, *, default: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    s = (raw or "").strip()
    if not s:
        return default
    if not s.startswith("#"):
        s = "#" + s
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", s)
    if not m:
        return default
    hexpart = m.group(1)
    if len(hexpart) == 3:
        hexpart = "".join(ch * 2 for ch in hexpart)
    return (int(hexpart[0:2], 16), int(hexpart[2:4], 16), int(hexpart[4:6], 16))


def _active_config(override: WatermarkApplyConfig | None = None) -> WatermarkApplyConfig | None:
    if override is not None:
        return override
    return _config_ctx.get()


def _default_env_config() -> WatermarkApplyConfig:
    text = watermark_text()
    texts = tuple(
        t
        for t in (
            text,
            _normalize_wm_brand((os.getenv("TBCC_WATERMARK_TEXT_SECONDARY") or "").strip()),
            _normalize_wm_brand((os.getenv("TBCC_WATERMARK_TEXT_TERTIARY") or "").strip()),
        )
        if t
    )
    strip = (os.getenv("TBCC_WATERMARK_STRIP_PREVIOUS") or "0").strip().lower() in ("1", "true", "yes", "on")
    return WatermarkApplyConfig(
        enabled=watermark_enabled(),
        texts=texts,
        opacity=watermark_opacity(),
        color_hex=(os.getenv("TBCC_WATERMARK_COLOR") or "#FFFFFF").strip(),
        mode=watermark_mode(),
        position=watermark_fixed_position(),
        strip_previous=strip,
    )


def watermark_enabled() -> bool:
    if (os.getenv("TBCC_WATERMARK_ENABLED") or "").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool((watermark_text() or "").strip())


def _normalize_wm_brand(text: str) -> str:
    try:
        from app.data.aof_telegram_links import normalize_telegram_me_brand

        return normalize_telegram_me_brand(text)[:120]
    except Exception:
        return (text or "").replace("t.me/", "telegram.me/")[:120]


def watermark_text() -> str:
    explicit = (os.getenv("TBCC_WATERMARK_TEXT") or "").strip()
    if explicit:
        return _normalize_wm_brand(explicit)
    base = (os.getenv("TBCC_PUBLIC_BASE_URL") or os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
    if base:
        return _normalize_wm_brand(base.replace("https://", "").replace("http://", "").split("/")[0])
    try:
        from app.data.aof_telegram_links import AOF_WATERMARK_DEFAULT

        return _normalize_wm_brand(AOF_WATERMARK_DEFAULT)
    except Exception:
        return "telegram.me/aofmainhub"


def watermark_mode() -> str:
    m = (os.getenv("TBCC_WATERMARK_MODE") or "rotate").strip().lower()
    return m if m in ("rotate", "fixed") else "rotate"


def watermark_fixed_position() -> WatermarkPosition:
    raw = (os.getenv("TBCC_WATERMARK_POSITION") or "bottom_right").strip().lower()
    if raw in POSITIONS:
        return raw  # type: ignore[return-value]
    return "bottom_right"


def watermark_opacity() -> float:
    raw = (os.getenv("TBCC_WATERMARK_OPACITY") or "0.58").strip()
    try:
        return max(0.15, min(1.0, float(raw)))
    except ValueError:
        return 0.58


def watermark_size_ratio() -> float:
    raw = (os.getenv("TBCC_WATERMARK_SIZE_RATIO") or "0.045").strip()
    try:
        return max(0.012, min(0.08, float(raw)))
    except ValueError:
        return 0.045


def watermark_margin_px() -> int:
    raw = (os.getenv("TBCC_WATERMARK_MARGIN_PX") or "10").strip()
    try:
        return max(4, min(80, int(raw)))
    except ValueError:
        return 10


def watermark_max_video_mb() -> int:
    raw = (os.getenv("TBCC_WATERMARK_MAX_VIDEO_MB") or "250").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 250


def watermark_config_public(db=None) -> dict:
    try:
        from app.services.watermark_settings_effective import get_effective_watermark_settings

        if db is not None:
            return get_effective_watermark_settings(db)
    except Exception:
        logger.debug("watermark_config_public: effective settings unavailable", exc_info=True)
    cfg = _default_env_config()
    return {
        "enabled": cfg.enabled,
        "text": cfg.texts[0] if cfg.texts else "",
        "text_secondary": cfg.texts[1] if len(cfg.texts) > 1 else "",
        "text_tertiary": cfg.texts[2] if len(cfg.texts) > 2 else "",
        "texts": list(cfg.texts),
        "mode": cfg.mode,
        "position": cfg.position,
        "opacity": cfg.opacity,
        "color": cfg.color_hex,
        "strip_previous": cfg.strip_previous,
        "apply_on_saved_import": False,
        "apply_on_album_composer": True,
    }


def _should_skip(*, force_skip: bool = False) -> bool:
    if force_skip or _skip_ctx.get():
        return True
    return not watermark_enabled()


def _pick_position() -> WatermarkPosition:
    global _rotate_index
    if watermark_mode() == "fixed":
        return watermark_fixed_position()
    with _rotate_lock:
        pos = POSITIONS[_rotate_index % len(POSITIONS)]
        _rotate_index += 1
    return pos


def _font_path() -> str | None:
    custom = (os.getenv("TBCC_WATERMARK_FONT_PATH") or "").strip()
    if custom and Path(custom).is_file():
        return custom
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for name in ("arial.ttf", "segoeui.ttf", "calibri.ttf"):
        p = Path(windir) / "Fonts" / name
        if p.is_file():
            return str(p)
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if Path(p).is_file():
            return p
    return None


def _font_size(w: int, h: int) -> int:
    base = int(min(w, h) * watermark_size_ratio())
    return max(9, min(28, base))


def _text_rgba(opacity: float, rgb: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int, int]:
    a = int(max(0, min(255, round(opacity * 255))))
    return (rgb[0], rgb[1], rgb[2], a)


def _blur_norm_rect(im, x: float, y: float, w: float, h: float):
    from PIL import Image, ImageFilter

    iw, ih = im.size
    left = max(0, int(x * iw))
    top = max(0, int(y * ih))
    right = min(iw, int((x + w) * iw))
    bottom = min(ih, int((y + h) * ih))
    if right <= left or bottom <= top:
        return
    box = (left, top, right, bottom)
    region = im.crop(box)
    blurred = region.filter(ImageFilter.GaussianBlur(radius=max(2, min(iw, ih) // 80)))
    im.paste(blurred, box)


def _strip_previous_watermark_bands(im) -> None:
    """Optional pre-pass: blur fixed edge bands (not content-aware). Off unless strip_previous is enabled."""
    _blur_norm_rect(im, 0, 0.90, 1, 0.10)
    _blur_norm_rect(im, 0, 0, 1, 0.06)
    _blur_norm_rect(im, 0, 0.82, 0.42, 0.12)
    _blur_norm_rect(im, 0.58, 0.82, 0.42, 0.12)


def _draw_text_with_shadow(
    draw,
    xy: tuple[float, float],
    text: str,
    *,
    font,
    fill: tuple[int, int, int, int],
) -> None:
    x, y = xy
    shadow = (0, 0, 0, min(220, fill[3]))
    for dx, dy in ((1, 1), (1, 0), (0, 1)):
        draw.text((x + dx, y + dy), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def _anchor_xy(
    position: WatermarkPosition,
    w: int,
    h: int,
    tw: int,
    th: int,
) -> tuple[float, float]:
    m = watermark_margin_px()
    if position == "upper_left":
        return (m, m)
    if position == "upper_right":
        return (w - tw - m, m)
    if position == "bottom_left":
        return (m, h - th - m)
    if position == "center_diagonal":
        return ((w - tw) / 2, (h - th) / 2)
    return (w - tw - m, h - th - m)


def _render_rotated_text_layer(
    text: str,
    font_size: int,
    opacity: float,
    *,
    rgb: tuple[int, int, int] = (255, 255, 255),
    angle: float = -32,
) -> "Image.Image":
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(_font_path(), font_size) if _font_path() else ImageFont.load_default()
    tmp = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(tmp)
    bbox = tdraw.textbbox((0, 0), text, font=font)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])
    pad = max(8, font_size // 2)
    layer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    _draw_text_with_shadow(draw, (pad, pad), text, font=font, fill=_text_rgba(opacity, rgb))
    return layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)


def _draw_watermark_on_rgba(
    im,
    text: str,
    position: WatermarkPosition,
    *,
    opacity: float,
    rgb: tuple[int, int, int],
):
    from PIL import Image, ImageDraw, ImageFont

    w, h = im.size
    if w < 8 or h < 8:
        return im
    fs = _font_size(w, h)
    if position == "center_diagonal":
        rotated = _render_rotated_text_layer(text, fs, opacity, rgb=rgb)
        rx, ry = (w - rotated.width) // 2, (h - rotated.height) // 2
        base = im.copy()
        base.alpha_composite(rotated, (int(rx), int(ry)))
        return base

    font = ImageFont.truetype(_font_path(), fs) if _font_path() else ImageFont.load_default()
    draw = ImageDraw.Draw(im)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x, y = _anchor_xy(position, w, h, tw, th)
    _draw_text_with_shadow(draw, (x, y), text, font=font, fill=_text_rgba(opacity, rgb))
    return im


def _positions_for_texts(cfg: WatermarkApplyConfig, count: int) -> list[WatermarkPosition]:
    if count <= 0:
        return []
    if cfg.mode == "fixed":
        slots = [cfg.position, "bottom_left", "upper_left", "upper_right", "bottom_right"]
        return [slots[i % len(slots)] for i in range(count)]
    out: list[WatermarkPosition] = []
    with _rotate_lock:
        global _rotate_index
        for i in range(count):
            out.append(POSITIONS[(_rotate_index + i) % len(POSITIONS)])
        _rotate_index += count
    return out


def _apply_image_watermark_config(data: bytes, cfg: WatermarkApplyConfig) -> bytes:
    if not cfg.texts:
        return data
    pos_list = _positions_for_texts(cfg, len(cfg.texts))
    rgb = parse_color_hex(cfg.color_hex)
    opacity = cfg.opacity
    for text, pos in zip(cfg.texts, pos_list):
        data = _apply_image_watermark(data, text, pos, opacity=opacity, rgb=rgb, strip_previous=cfg.strip_previous)
    return data


def _apply_image_watermark(
    data: bytes,
    text: str,
    position: WatermarkPosition,
    *,
    opacity: float | None = None,
    rgb: tuple[int, int, int] | None = None,
    strip_previous: bool = False,
) -> bytes:
    from PIL import Image, ImageSequence

    im = Image.open(io.BytesIO(data))
    fmt = (im.format or "JPEG").upper()

    op = watermark_opacity() if opacity is None else opacity
    color = rgb or (255, 255, 255)

    if getattr(im, "is_animated", False) and fmt == "GIF":
        frames = []
        durations = []
        loop = im.info.get("loop", 0)
        for frame in ImageSequence.Iterator(im):
            fr = frame.convert("RGBA")
            if strip_previous:
                _strip_previous_watermark_bands(fr)
            out = _draw_watermark_on_rgba(fr, text, position, opacity=op, rgb=color)
            frames.append(out.convert("P", palette=Image.ADAPTIVE, dither=Image.Dither.FLOYDSTEINBERG))
            durations.append(frame.info.get("duration", 100))
        buf = io.BytesIO()
        frames[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=loop,
            disposal=2,
        )
        return buf.getvalue()

    if fmt == "PNG" or (im.mode in ("RGBA", "LA") and fmt != "JPEG"):
        base = im.convert("RGBA")
        if strip_previous:
            _strip_previous_watermark_bands(base)
        out = _draw_watermark_on_rgba(base, text, position, opacity=op, rgb=color)
        buf = io.BytesIO()
        out.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    base = im.convert("RGB")
    rgba = base.convert("RGBA")
    if strip_previous:
        _strip_previous_watermark_bands(rgba)
    out = _draw_watermark_on_rgba(rgba, text, position, opacity=op, rgb=color)
    buf = io.BytesIO()
    out.convert("RGB").save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


def _ffmpeg_escape_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", r"\:")


def _ffmpeg_escape_text(text: str) -> str:
    t = text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")
    return t


def _ffmpeg_drawtext_position(position: WatermarkPosition, font_size: int) -> str:
    m = watermark_margin_px()
    if position == "upper_left":
        return f"x={m}:y={m}"
    if position == "upper_right":
        return f"x=w-tw-{m}:y={m}"
    if position == "bottom_left":
        return f"x={m}:y=h-th-{m}"
    if position == "center_diagonal":
        return f"x=(w-tw)/2:y=(h-th)/2"
    return f"x=w-tw-{m}:y=h-th-{m}"


def _apply_video_watermark_config(data: bytes, cfg: WatermarkApplyConfig) -> bytes:
    if not cfg.texts:
        return data
    pos_list = _positions_for_texts(cfg, len(cfg.texts))
    rgb = parse_color_hex(cfg.color_hex)
    out = data
    for text, pos in zip(cfg.texts, pos_list):
        out = _apply_video_watermark(
            out,
            text,
            pos,
            opacity=cfg.opacity,
            rgb=rgb,
            strip_previous=cfg.strip_previous and out is data,
        )
    return out


def _apply_video_watermark(
    data: bytes,
    text: str,
    position: WatermarkPosition,
    *,
    opacity: float | None = None,
    rgb: tuple[int, int, int] | None = None,
    strip_previous: bool = False,
) -> bytes:
    if not ffmpeg_available():
        logger.debug("watermark: ffmpeg unavailable, skipping video")
        return data
    max_bytes = watermark_max_video_mb() * 1024 * 1024
    if len(data) > max_bytes:
        logger.info("watermark: video too large (%s MB), skipping", len(data) // (1024 * 1024))
        return data

    font = _font_path()
    fs = max(10, min(24, int(watermark_size_ratio() * 720)))
    op = watermark_opacity() if opacity is None else opacity
    color = rgb or (255, 255, 255)
    pos = _ffmpeg_drawtext_position(position, fs)
    text_esc = _ffmpeg_escape_text(text)
    color_name = f"0x{color[0]:02x}{color[1]:02x}{color[2]:02x}"

    with tempfile.TemporaryDirectory(prefix="tbcc_wm_") as td:
        td_path = Path(td)
        inp = td_path / "in.bin"
        out = td_path / "out.mp4"
        inp.write_bytes(data)

        if position == "center_diagonal":
            from PIL import Image

            layer = _render_rotated_text_layer(text, fs, op, rgb=color, angle=-32)
            overlay_png = td_path / "overlay.png"
            layer.save(overlay_png, format="PNG")
            overlay_esc = _ffmpeg_escape_path(str(overlay_png))
            vf = f"overlay=(W-w)/2:(H-h)/2"
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(inp),
                "-i",
                str(overlay_png),
                "-filter_complex",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "copy",
                str(out),
            ]
        elif font:
            font_esc = _ffmpeg_escape_path(font)
            fontcolor = f"{color_name}@{op:.2f}"
            vf_parts = []
            if strip_previous:
                vf_parts.append("boxblur=luma_radius=8:luma_power=1:chroma_radius=8:chroma_power=1")
            vf_parts.append(
                f"drawtext=text='{text_esc}':fontfile='{font_esc}':fontsize={fs}:"
                f"fontcolor={fontcolor}:{pos}:shadowcolor=black@0.45:shadowx=1:shadowy=1"
            )
            vf = ",".join(vf_parts)
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(inp),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "copy",
                str(out),
            ]
        else:
            return data

        timeout = int(os.getenv("TBCC_WATERMARK_FFMPEG_TIMEOUT_S", "600"))
        try:
            subprocess.run(cmd, timeout=timeout, check=True, capture_output=True)
        except Exception as e:
            logger.warning("watermark: ffmpeg failed: %s", e)
            return data
        if not out.is_file() or out.stat().st_size < 256:
            return data
        return out.read_bytes()


def maybe_apply_media_watermark(
    data: bytes,
    media_type_hint: str = "photo",
    *,
    force_skip: bool = False,
    position: WatermarkPosition | None = None,
    config: WatermarkApplyConfig | None = None,
) -> bytes:
    """
    Apply promo text watermark when enabled.
    Skips unknown documents unless magic bytes look like photo/video/gif.
    """
    if not data:
        return data

    cfg = _active_config(config)
    if cfg is None:
        cfg = _default_env_config()
    if force_skip or _skip_ctx.get() or cfg.skip or not cfg.enabled or not cfg.texts:
        return data

    # Hard-rewrite any stale t.me brand still sitting on a caller's config.
    norm_texts = tuple(t for t in (_normalize_wm_brand(x) for x in cfg.texts) if t)
    if not norm_texts:
        return data
    if norm_texts != cfg.texts:
        cfg = WatermarkApplyConfig(
            enabled=cfg.enabled,
            texts=norm_texts,
            opacity=cfg.opacity,
            color_hex=cfg.color_hex,
            mode=cfg.mode,
            position=cfg.position,
            strip_previous=cfg.strip_previous,
            skip=cfg.skip,
        )
    kind, _ext = sniff_media_kind(data)
    hint = (media_type_hint or "photo").lower()
    if kind == "document":
        if hint in ("photo", "video", "gif"):
            kind = "gif" if hint == "gif" else ("video" if hint == "video" else "photo")
        else:
            return data

    try:
        if len(cfg.texts) == 1 and position is not None:
            rgb = parse_color_hex(cfg.color_hex)
            if kind == "video":
                return _apply_video_watermark(
                    data,
                    cfg.texts[0],
                    position,
                    opacity=cfg.opacity,
                    rgb=rgb,
                    strip_previous=cfg.strip_previous,
                )
            if kind in ("photo", "gif"):
                return _apply_image_watermark(
                    data,
                    cfg.texts[0],
                    position,
                    opacity=cfg.opacity,
                    rgb=rgb,
                    strip_previous=cfg.strip_previous,
                )
        if kind == "video":
            return _apply_video_watermark_config(data, cfg)
        if kind in ("photo", "gif"):
            return _apply_image_watermark_config(data, cfg)
    except Exception as e:
        logger.warning("watermark apply failed (%s): %s", kind, e)
        return data
    return data
