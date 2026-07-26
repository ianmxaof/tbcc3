from pathlib import Path

from app.services.loot_border_profiles import profile_for_border
from app.services.loot_border_reveal import match_stasis_for_open, pick_border_clip


def test_profile_for_brushed_metal_clip():
    clip = Path("brushed_metal_stasis_sparkle_open.mp4")
    profile = profile_for_border(clip)
    assert profile is not None
    assert profile.profile_id == "brushed_metal_stasis_sparkle"


def test_profile_for_loot_god_single_clip():
    clip = Path("PROJECT_AOF_LOOT_GOD_-_single.mp4")
    profile = profile_for_border(clip)
    assert profile is not None
    assert profile.profile_id == "brushed_metal_stasis_sparkle"


def test_match_stasis_for_open_by_base_name():
    opens = [Path("brushed_metal_stasis_sparkle_open.mp4")]
    stasis = [
        Path("brushed_metal_stasis_sparkle_stasis.mp4"),
        Path("other_stasis.mp4"),
    ]
    matched = match_stasis_for_open(opens[0], stasis)
    assert matched == stasis[0]


def test_pick_border_clip_single_folder(tmp_path, monkeypatch):
    clips_dir = tmp_path / "open"
    clips_dir.mkdir()
    (clips_dir / "brushed_metal_stasis_sparkle_open.mp4").write_bytes(b"x" * 2048)
    (clips_dir / "PROJECT_AOF_LOOT_GOD_-_single.mp4").write_bytes(b"x" * 2048)
    (clips_dir / "border-002-open-project.mp4").write_bytes(b"x" * 2048)

    monkeypatch.setenv("TBCC_LOOT_CARD_BORDERS_DIR", str(tmp_path))
    monkeypatch.delenv("TBCC_LOOT_BORDER_PAIR", raising=False)

    clip = pick_border_clip()
    assert clip is not None
    assert "border-002" not in clip.stem


def test_pick_border_clip_denies_legacy_border_001(tmp_path, monkeypatch):
    clips_dir = tmp_path / "open"
    clips_dir.mkdir()
    (clips_dir / "border-001-open-phase-begin.mp4").write_bytes(b"x" * 2048)

    monkeypatch.setenv("TBCC_LOOT_CARD_BORDERS_DIR", str(tmp_path))
    monkeypatch.delenv("TBCC_LOOT_BORDER_PAIR", raising=False)

    assert pick_border_clip() is None


def test_pick_border_clip_denies_unix_commands_stray(tmp_path, monkeypatch):
    clips_dir = tmp_path / "open"
    clips_dir.mkdir()
    (clips_dir / "Unix_Commands_on_Windows_Explained.mp4").write_bytes(b"x" * 2048)

    monkeypatch.setenv("TBCC_LOOT_CARD_BORDERS_DIR", str(tmp_path))
    monkeypatch.delenv("TBCC_LOOT_BORDER_PAIR", raising=False)
    monkeypatch.delenv("TBCC_LOOT_BORDER_DENY", raising=False)

    assert pick_border_clip() is None
