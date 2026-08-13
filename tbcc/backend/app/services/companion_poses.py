"""Photo pose catalog — filter broken/unsupported API poses for the bot UI."""

from __future__ import annotations

# Poses that fail on undresstool.fun or have no operator art — never show in picker.
BLOCKED_PHOTO_POSES: frozenset[str] = frozenset({"Lingerie"})

# Operator composite filename → API pose label (undresstool.fun /photos/poses names).
POSE_SOURCE_FILES: dict[str, str] = {
    "Cumshot": "cumshot.jpg",
    "Missionary POV": "missionary.jpg",
    "Blowjob": "blowjob.jpg",
    "Doggy Style": "doggystyle.jpg",
    "Anal Fuck": "anal.jpg",
    "Cowgirl POV": "POVCOWGIRL.jpg",
    "Spreading legs": "spreadinglegs.jpg",
    "Tit Fuck": "titfuck.jpg",
    "Ahegao cum": "ahegaocum.jpg",
    "Cumshot POV": "cumshotjpg.jpg",
    "Estival solstice": "Festivalsolstice.jpg",
    "Shibari": "shibari.jpg",
    "Wet girl": "wetgirl.jpg",
}


def filter_photo_poses(poses: list[str], *, require_tile: bool = False) -> list[str]:
    from app.services.companion_assets import pose_tile_available

    out: list[str] = []
    for pose in poses:
        name = (pose or "").strip()
        if not name or name in BLOCKED_PHOTO_POSES:
            continue
        if require_tile and not pose_tile_available(name):
            continue
        out.append(name)
    return out


def filter_default_photo_poses(poses: tuple[str, ...] | list[str]) -> list[str]:
    return filter_photo_poses(list(poses))
