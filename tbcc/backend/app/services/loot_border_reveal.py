"""Animated border reveal — center still + chroma-keyed border clip → MP4.

Each border animation is a **single MP4** (open + sustain baked in). Legacy open/stasis
pair mux is deprecated; clips live under ``borders/open/`` only.
"""

from __future__ import annotations

import logging
import os
import random
import subprocess
import tempfile
from pathlib import Path

from app.services.loot_reveal_video import (
    ffmpeg_available,
    reveal_video_encode_timeout_s,
    reveal_video_size,
)

logger = logging.getLogger(__name__)

CHROMA_KEY = "0xFF00FF"


def _chroma_similarity() -> str:
    """Conservative — high values eat grey metal chrome (black pixel holes)."""
    raw = (os.getenv("TBCC_LOOT_BORDER_CHROMA_SIM") or "0.22").strip()
    try:
        return str(max(0.10, min(0.32, float(raw))))
    except ValueError:
        return "0.22"


def _chroma_blend() -> str:
    raw = (os.getenv("TBCC_LOOT_BORDER_CHROMA_BLEND") or "0.03").strip()
    try:
        return str(max(0.0, min(0.08, float(raw))))
    except ValueError:
        return "0.03"


def loot_border_reveal_enabled() -> bool:
    raw = (os.getenv("TBCC_LOOT_BORDER_REVEAL") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def borders_root() -> Path:
    from app.services.loot_tier_card_assets import loot_tier_card_dir

    override = (os.getenv("TBCC_LOOT_CARD_BORDERS_DIR") or "").strip()
    if override:
        return Path(override)
    return loot_tier_card_dir() / "borders"


def border_open_dir() -> Path:
    """Canonical clip folder — single animations (open + sustain in one file)."""
    return borders_root() / "open"


def border_clips_dir() -> Path:
    return border_open_dir()


def border_stasis_dir() -> Path:
    """Deprecated — stasis pairs no longer used; kept for import/migration paths."""
    return borders_root() / "stasis"


def _list_clips(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    out: list[Path] = []
    for ext in (".mp4", ".webm", ".mov"):
        out.extend(sorted(folder.glob(f"*{ext}")))
    return [p for p in out if p.is_file() and p.stat().st_size > 1024]


def list_border_clips() -> list[Path]:
    return _list_clips(border_clips_dir())


def list_border_open_clips() -> list[Path]:
    return list_border_clips()


def list_border_stasis_clips() -> list[Path]:
    return _list_clips(border_stasis_dir())


def _border_clip_base(stem: str) -> str:
    s = stem.lower()
    for suffix in ("_open", "-open", "_stasis", "-stasis", "_single", "-single"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def match_stasis_for_open(open_clip: Path, stasis_clips: list[Path]) -> Path | None:
    """Deprecated — retained for tests/migration only."""
    base = _border_clip_base(open_clip.stem)
    exact = [
        p
        for p in stasis_clips
        if _border_clip_base(p.stem) == base
        or p.stem.lower() == f"{base}_stasis"
        or p.stem.lower() == f"{base}-stasis"
    ]
    if exact:
        exact.sort(key=lambda p: (0 if p.stem.endswith("_stasis") and not p.stem.endswith("2") else 1, len(p.stem)))
        return exact[0]
    partial = [p for p in stasis_clips if base and base in p.stem.lower()]
    return partial[0] if partial else None


def border_clip_filter() -> str:
    return (os.getenv("TBCC_LOOT_BORDER_PAIR") or os.getenv("TBCC_LOOT_BORDER_CLIP") or "").strip().lower()


def _border_deny_tokens() -> set[str]:
    raw = (os.getenv("TBCC_LOOT_BORDER_DENY") or "border-001,border-002,border-003,unix_commands").strip()
    return {t.strip().lower() for t in raw.split(",") if t.strip()}


def _border_clip_denied(path: Path) -> bool:
    stem = path.stem.lower()
    if stem.endswith("_stasis2") or stem.endswith("-stasis2"):
        return True
    for token in _border_deny_tokens():
        if token in stem:
            return True
    return False


def _border_clip_allowed(path: Path) -> bool:
    if _border_clip_denied(path):
        return False
    raw = (os.getenv("TBCC_LOOT_BORDER_ALLOW_UNPROFILED") or "1").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    from app.services.loot_border_profiles import profile_for_border

    return profile_for_border(path) is not None


def pick_border_clip(rng: random.Random | None = None) -> Path | None:
    """Pick one border animation (single MP4 with open + sustain)."""
    clips = [p for p in list_border_clips() if _border_clip_allowed(p)]
    if not clips:
        return None
    want = border_clip_filter()
    if want:
        clips = [p for p in clips if want in p.stem.lower()]
        if not clips:
            return None
    r = rng or random.Random()
    return r.choice(clips)


def pick_border_pair(rng: random.Random | None = None) -> tuple[Path, Path] | None:
    """Deprecated alias — returns the same clip twice for legacy call sites."""
    clip = pick_border_clip(rng)
    if clip is None:
        return None
    return clip, clip


def _probe_clip_duration_s(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=True,
        )
        return max(0.1, float((out.stdout or "").strip()))
    except Exception:
        return None


def border_play_seconds(clip: Path | None = None) -> float:
    """How long to play the composed reveal (defaults to full clip length)."""
    probed = _probe_clip_duration_s(clip) if clip else None
    raw = (os.getenv("TBCC_LOOT_BORDER_PLAY_SECONDS") or "").strip()
    if raw:
        try:
            cap = max(2.0, min(15.0, float(raw)))
            return min(cap, probed) if probed else cap
        except ValueError:
            pass
    if probed:
        return min(probed, 12.0)
    return 7.6


def border_open_seconds() -> float:
    """Deprecated — open timing is baked into single clips."""
    raw = (os.getenv("TBCC_LOOT_BORDER_OPEN_SECONDS") or "1.6").strip()
    try:
        return max(0.8, min(3.0, float(raw)))
    except ValueError:
        return 1.6


def border_stasis_play_seconds() -> float:
    """Deprecated — sustain timing is baked into single clips."""
    raw = (os.getenv("TBCC_LOOT_BORDER_STASIS_SECONDS") or os.getenv("TBCC_LOOT_REVEAL_VIDEO_SECONDS") or "6").strip()
    try:
        return max(2.0, min(12.0, float(raw)))
    except ValueError:
        return 6.0


def border_auto_crop_enabled() -> bool:
    raw = (os.getenv("TBCC_LOOT_BORDER_AUTO_CROP") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _border_chroma_filter(
    dim: int,
    label_in: str,
    label_out: str,
    *,
    crop: tuple[int, int, int, int] | None = None,
) -> str:
    from app.services.loot_border_plates import ffmpeg_chrome_crop_scale_chain

    sim = _chroma_similarity()
    blend = _chroma_blend()
    prep = ffmpeg_chrome_crop_scale_chain(crop, size=dim, fps=24, suffix=",format=rgba")
    return f"[{label_in}:v]{prep},chromakey={CHROMA_KEY}:{sim}:{blend}[{label_out}]"


def mux_border_reveal_mp4(
    center_jpeg: bytes,
    stamp_png: bytes,
    border_clip: Path,
    *,
    duration_s: float | None = None,
    size: int | None = None,
    stasis_clip: Path | None = None,
    open_clip: Path | None = None,
) -> bytes | None:
    """
    Layer stack (bottom → top):
      1. Center still (loot art in the border window)
      2. Single border clip (open + sustain baked in)
      3. Stamp overlay (tier / name text, RGBA)
    """
    clip = border_clip
    if open_clip is not None and open_clip.is_file():
        clip = open_clip
    if not center_jpeg or not stamp_png or not clip.is_file():
        return None
    if not ffmpeg_available():
        return None

    total = duration_s if duration_s is not None else border_play_seconds(clip)
    dim = size if size is not None else reveal_video_size()
    timeout = reveal_video_encode_timeout_s() + int(total) + 5

    crop_bbox: tuple[int, int, int, int] | None = None
    if border_auto_crop_enabled():
        from app.services.loot_border_plates import card_crop_bbox_for_clip

        crop_bbox = card_crop_bbox_for_clip(clip)

    with tempfile.TemporaryDirectory(prefix="tbcc_border_reveal_") as td:
        td_path = Path(td)
        center_path = td_path / "center.jpg"
        stamp_path = td_path / "stamp.png"
        out_path = td_path / "reveal.mp4"
        center_path.write_bytes(center_jpeg)
        stamp_path.write_bytes(stamp_png)

        filt = (
            f"[0:v]scale={dim}:{dim}:flags=lanczos,fps=24[base];"
            f"{_border_chroma_filter(dim, '1', 'border', crop=crop_bbox)};"
            f"[base][border]overlay=0:0:format=auto[card];"
            f"[2:v]scale={dim}:{dim},format=rgba[stamps];"
            f"[card][stamps]overlay=0:0:format=auto[v]"
        )
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(center_path),
            "-i",
            str(clip),
            "-i",
            str(stamp_path),
            "-filter_complex",
            filt,
            "-map",
            "[v]",
            "-t",
            str(total),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, timeout=timeout, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode("utf-8", errors="replace")[:800]
            logger.warning("border reveal ffmpeg failed: %s", stderr)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("border reveal ffmpeg timed out after %ss", timeout)
            return None
        if not out_path.is_file() or out_path.stat().st_size < 4096:
            return None
        return out_path.read_bytes()


def mux_border_reveal_still_jpeg(
    center_jpeg: bytes,
    stamp_png: bytes,
    border_clip: Path,
    *,
    size: int | None = None,
    stasis_clip: Path | None = None,
) -> bytes | None:
    clip = border_clip
    if stasis_clip is not None and stasis_clip.is_file():
        clip = stasis_clip
    if not center_jpeg or not stamp_png or not clip.is_file():
        return None
    if not ffmpeg_available():
        return None

    dim = size if size is not None else reveal_video_size()
    timeout = reveal_video_encode_timeout_s()
    still_t = max(0.5, border_play_seconds(clip) * 0.85)

    crop_bbox: tuple[int, int, int, int] | None = None
    if border_auto_crop_enabled():
        from app.services.loot_border_plates import card_crop_bbox_for_clip

        crop_bbox = card_crop_bbox_for_clip(clip)

    with tempfile.TemporaryDirectory(prefix="tbcc_border_still_") as td:
        td_path = Path(td)
        center_path = td_path / "center.jpg"
        stamp_path = td_path / "stamp.png"
        out_path = td_path / "reveal.jpg"
        center_path.write_bytes(center_jpeg)
        stamp_path.write_bytes(stamp_png)

        filt = (
            f"[0:v]scale={dim}:{dim}:flags=lanczos[base];"
            f"{_border_chroma_filter(dim, '1', 'border', crop=crop_bbox)};"
            f"[border]trim=duration={still_t},setpts=PTS-STARTPTS[bf];"
            f"[base][bf]overlay=0:0:format=auto[card];"
            f"[2:v]scale={dim}:{dim},format=rgba[stamps];"
            f"[card][stamps]overlay=0:0:format=auto[v]"
        )
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(center_path),
            "-i",
            str(clip),
            "-i",
            str(stamp_path),
            "-filter_complex",
            filt,
            "-map",
            "[v]",
            "-frames:v",
            "1",
            "-f",
            "image2",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, timeout=timeout, check=True, capture_output=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning("border reveal still jpeg failed: %s", e)
            return None
        if not out_path.is_file() or out_path.stat().st_size < 1024:
            return None
        return out_path.read_bytes()


def compose_border_reveal_mp4(
    center_jpeg: bytes,
    stamp_png: bytes,
    *,
    rng: random.Random | None = None,
    border_clip: Path | None = None,
    open_clip: Path | None = None,
    stasis_clip: Path | None = None,
    size: int | None = None,
) -> tuple[bytes | None, str]:
    if not loot_border_reveal_enabled():
        return None, "disabled"
    clip = border_clip or open_clip or stasis_clip
    if clip is None:
        clip = pick_border_clip(rng)
    if clip is None:
        return None, "no_border_clips"
    dim = size if size is not None else reveal_video_size()
    data = mux_border_reveal_mp4(center_jpeg, stamp_png, clip, size=dim)
    if not data:
        return None, f"encode_failed:clip={clip.name}"
    play_s = border_play_seconds(clip)
    return data, f"border clip={clip.name} play={play_s:.1f}s"


def compose_border_reveal_still_jpeg(
    center_jpeg: bytes,
    stamp_png: bytes,
    border_clip: Path,
    *,
    size: int | None = None,
    stasis_clip: Path | None = None,
) -> bytes | None:
    dim = size if size is not None else reveal_video_size()
    clip = border_clip if border_clip.is_file() else (stasis_clip or border_clip)
    return mux_border_reveal_still_jpeg(center_jpeg, stamp_png, clip, size=dim)
