"""MEGA pack folder branding tests."""

from app.services.mega_pack_naming import (
    build_branded_pack_folder_name,
    extract_pack_theme,
    is_new_brand_format,
    is_pack_already_branded,
    target_branded_pack_rename,
)


def test_is_pack_already_branded_legacy():
    assert is_pack_already_branded("Milf Pack-TME AOFMAINHUB") is False  # legacy → rebrand when enabled
    assert is_pack_already_branded("Mihanika · 60GB · AOFMAINHUB") is False


def test_is_new_brand_format():
    name = build_branded_pack_folder_name("Mihanika", 60.0, file_count=698)
    assert is_new_brand_format(name)
    assert is_pack_already_branded(name)


def test_is_pack_not_branded():
    assert not is_pack_already_branded("Irisadamsone")
    assert not is_pack_already_branded("Random Mega Dump")


def test_extract_pack_theme_strips_legacy_suffix():
    assert extract_pack_theme("GoldenFans18+-TME AOFMAINHUB") == "GoldenFans18+"


def test_extract_pack_theme_strips_new_format():
    branded = build_branded_pack_folder_name("Mihanika", 13.7, file_count=698)
    assert extract_pack_theme(branded) == "Mihanika"


def test_build_branded_name_includes_handle_size_files_tail():
    name = build_branded_pack_folder_name("Mihanika", 60.0, file_count=120)
    assert name.startswith("telegram.me/aofmainhub")
    assert "60GB" in name
    assert "120 Files" in name
    assert "Mihanika" in name
    assert "MEGA PACK" in name


def test_target_rename_skips_new_brand():
    branded = build_branded_pack_folder_name("Foo", 10)
    assert target_branded_pack_rename(branded, 10) is None


def test_target_rename_legacy_pack():
    out = target_branded_pack_rename("Foo-TME AOFMAINHUB", 17.5, file_count=50)
    assert out is not None
    assert out.startswith("telegram.me/aofmainhub")
    assert "Foo" in out


def test_target_rename_new_pack():
    out = target_branded_pack_rename("Irisadamsone", 17.5, file_count=22)
    assert out is not None
    assert "Irisadamsone" in out
    assert "17.5GB" in out
    assert "22 Files" in out
