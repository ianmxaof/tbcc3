"""User-selected undress API body parameters (Telegram user_data).

Enum values must match undresstool.fun OpenAPI:
https://public-api.undresstool.fun/openapi.json
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BODY_PREFS_KEY = "body_prefs"

BODY_PRESET_IDS: tuple[str, ...] = ("natural", "curvy", "bimbo")

BODY_PRESETS: dict[str, dict[str, str]] = {
    "natural": {
        "age": "30",
        "body_type": "normal",
        "breast_size": "normal",
        "butt_size": "normal",
    },
    "curvy": {
        "age": "20",
        "body_type": "curvy",
        "breast_size": "normal",
        "butt_size": "big",
    },
    "bimbo": {
        "age": "20",
        "body_type": "curvy",
        "breast_size": "big",
        "butt_size": "big",
    },
}

# API-native values (BreastSizeEnum / ButtSizeEnum / BodyTypeEnum / AgeEnum)
OPTION_GROUPS: dict[str, tuple[str, ...]] = {
    "age": ("18", "20", "30", "40", "50"),
    "body_type": ("skinny", "normal", "curvy", "muscular"),
    "breast_size": ("small", "normal", "big"),
    "butt_size": ("small", "normal", "big"),
}

# ClothEnum — outfit override on /api/v1/photos/undress (optional).
CLOTH_OPTIONS: tuple[str, ...] = (
    "Naked",
    "Bikini",
    "Lingerie",
    "Sport wear",
    "BDSM",
    "Latex",
    "Teacher",
    "Schoolgirl",
    "Bikini leopard",
    "Naked cum",
    "Naked tatoo",
    "Witch",
    "Sexy Witch",
    "Maid",
    "Christmas underwear",
    "Pregnant",
    "Cheerleader",
    "Police",
    "Secretary",
    "Blooming Bouquet",
    "Leather dress",
    "Corset",
    "Mini bikini",
)

POST_GEN_OPTIONS: tuple[str, ...] = ("upscale", "anime")

GROUP_LABELS: dict[str, str] = {
    "age": "Age look",
    "body_type": "Body shape",
    "breast_size": "Chest size",
    "butt_size": "Butt size",
    "cloth": "Outfit",
    "post_gen": "Enhance",
}

GROUP_SHORT: dict[str, str] = {
    "age": "Age",
    "body_type": "Body",
    "breast_size": "Chest",
    "butt_size": "Butt",
    "cloth": "Outfit",
    "post_gen": "FX",
}

# Human-readable button labels (API value → display).
OPTION_DISPLAY: dict[str, dict[str, str]] = {
    "age": {v: v for v in OPTION_GROUPS["age"]},
    "body_type": {
        "skinny": "Slim",
        "normal": "Average",
        "curvy": "Curvy",
        "muscular": "Muscular",
    },
    "breast_size": {
        "small": "Small",
        "normal": "Medium",
        "big": "Bimbo max",
    },
    "butt_size": {
        "small": "Small",
        "normal": "Medium",
        "big": "Large",
    },
    "cloth": {v: v for v in CLOTH_OPTIONS},
    "post_gen": {"upscale": "Upscale", "anime": "Anime"},
}

# Legacy UI values from an earlier pass — map before API submit.
_LEGACY_MAP: dict[str, dict[str, str]] = {
    "age": {"25": "20", "35": "30", "45": "40"},
    "body_type": {"slim": "skinny", "athletic": "muscular", "bbw": "curvy"},
    "breast_size": {"medium": "normal", "large": "big"},
    "butt_size": {"medium": "normal", "large": "big"},
}


@dataclass
class BodyPrefs:
    age: str | None = None
    body_type: str | None = None
    breast_size: str | None = None
    butt_size: str | None = None
    cloth: str | None = None
    post_gen: str | None = None

    def to_api_kwargs(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in ("age", "body_type", "breast_size", "butt_size", "cloth", "post_gen"):
            val = _api_value(key, getattr(self, key, None))
            if val:
                out[key] = val
        # undresstool only has small|normal|big — stack curvy body with big chest for max volume.
        if out.get("breast_size") == "big" and not out.get("body_type"):
            out["body_type"] = "curvy"
        return out

    def summary(self) -> str:
        parts = []
        for key in ("age", "body_type", "breast_size", "butt_size", "cloth", "post_gen"):
            val = getattr(self, key, None)
            label = GROUP_LABELS.get(key, key)
            shown = display_value(key, val) if val else "default"
            parts.append(f"{label}: {shown}")
        return " · ".join(parts)


def display_value(group: str, api_value: str | None) -> str:
    if not api_value:
        return "default"
    return OPTION_DISPLAY.get(group, {}).get(api_value, api_value)


def option_button_label(group: str, api_value: str, *, selected: bool = False) -> str:
    prefix = GROUP_SHORT.get(group, group)
    label = display_value(group, api_value)
    text = f"{prefix}: {label}"
    if len(text) > 28:
        text = f"{prefix[:4]} {label}"[:28]
    return f"✓ {text}" if selected else text


def styles_help_text() -> str:
    return (
        "<b>Body preset</b> — best-effort shaping on <i>your</i> photo.\n\n"
        "• <b>Natural</b> — subtle, close to source\n"
        "• <b>Curvy</b> — fuller hips + shape\n"
        "• <b>Bimbo max</b> — strongest volume (works best with a pose)\n\n"
        "<i>Tip: pick a pose + Bimbo for the biggest visual change.</i>"
    )


def preset_label(preset_id: str, *, selected: bool = False) -> str:
    labels = {"natural": "Natural", "curvy": "Curvy", "bimbo": "Bimbo max"}
    text = labels.get(preset_id, preset_id)
    return f"✓ {text}" if selected else text


def active_preset_id(prefs: BodyPrefs) -> str | None:
    api = prefs.to_api_kwargs()
    if not api:
        return None
    for preset_id, values in BODY_PRESETS.items():
        if all(api.get(k) == v for k, v in values.items()):
            return preset_id
    return None


def apply_body_preset(user_data: dict[str, Any], preset_id: str) -> BodyPrefs:
    preset_id = (preset_id or "").strip().lower()
    raw = BODY_PRESETS.get(preset_id)
    if not raw:
        return load_body_prefs(user_data)
    user_data[BODY_PREFS_KEY] = dict(raw)
    return load_body_prefs(user_data)


def apply_bimbo_preset(user_data: dict[str, Any]) -> BodyPrefs:
    """Maximize API breast/butt — big + curvy + young look."""
    return apply_body_preset(user_data, "bimbo")


def _api_value(group: str, raw: str | None) -> str | None:
    s = str(raw or "").strip()
    if not s:
        return None
    if group == "cloth":
        if s in CLOTH_OPTIONS:
            return s
        return None
    if group == "post_gen":
        s = s.lower()
        if s in POST_GEN_OPTIONS:
            return s
        return None
    s = s.lower()
    allowed = OPTION_GROUPS.get(group, ())
    if s in allowed:
        return s
    mapped = _LEGACY_MAP.get(group, {}).get(s)
    if mapped and mapped in allowed:
        return mapped
    return None


def load_body_prefs(user_data: dict[str, Any]) -> BodyPrefs:
    raw = user_data.get(BODY_PREFS_KEY)
    if not isinstance(raw, dict):
        return BodyPrefs()
    return BodyPrefs(
        age=_api_value("age", _clean(raw.get("age"))),
        body_type=_api_value("body_type", _clean(raw.get("body_type"))),
        breast_size=_api_value("breast_size", _clean(raw.get("breast_size"))),
        butt_size=_api_value("butt_size", _clean(raw.get("butt_size"))),
        cloth=_api_value("cloth", raw.get("cloth") if raw.get("cloth") is not None else None),
        post_gen=_api_value("post_gen", _clean(raw.get("post_gen"))),
    )


def save_body_pref(user_data: dict[str, Any], group: str, value: str | None) -> BodyPrefs:
    group = (group or "").strip().lower()
    if group not in OPTION_GROUPS and group not in ("cloth", "post_gen"):
        return load_body_prefs(user_data)
    raw = user_data.get(BODY_PREFS_KEY)
    if not isinstance(raw, dict):
        raw = {}
    if value is None:
        raw.pop(group, None)
    else:
        api_val = _api_value(group, value)
        if api_val:
            raw[group] = api_val
        else:
            raw.pop(group, None)
    user_data[BODY_PREFS_KEY] = raw
    return load_body_prefs(user_data)


def clear_body_prefs(user_data: dict[str, Any]) -> None:
    user_data.pop(BODY_PREFS_KEY, None)


def _clean(val: Any) -> str | None:
    s = str(val or "").strip()
    return s or None
