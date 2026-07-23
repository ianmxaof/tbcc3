import pytest

from app.services.r2_promo_upload import (
    _object_key,
    object_key_for_destination,
    public_url_for_key,
    resolve_prefix,
    sanitize_object_filename,
)


def test_object_key_sanitizes():
    key = _object_key("Premium Pack (1).jpg")
    assert key.startswith("sfw-x-promo/")
    assert key.endswith(".jpg")
    assert " " not in key.split("/")[-1]


def test_public_url_for_key():
    url = public_url_for_key("https://pub-abc.r2.dev", "sfw-x-promo/teaser.jpg")
    assert url == "https://pub-abc.r2.dev/sfw-x-promo/teaser.jpg"


def test_resolve_prefix_destinations():
    assert resolve_prefix("library") == "library"
    assert resolve_prefix("sfw_x_promo") == "sfw-x-promo"
    assert resolve_prefix("sfw-x-promo") == "sfw-x-promo"
    assert resolve_prefix("x-promo") == "sfw-x-promo"
    assert resolve_prefix(prefix="x-promo") == "sfw-x-promo"
    with pytest.raises(ValueError):
        resolve_prefix("unknown_bucket_lane")


def test_object_key_for_destination():
    lib = object_key_for_destination("AOF_media_12345_telegram.me_aofmainhub.jpg", destination="library")
    assert lib.startswith("library/")
    assert "AOF_media_12345" in lib
    sfw = object_key_for_destination("teaser.png", destination="sfw_x_promo")
    assert sfw.startswith("sfw-x-promo/")


def test_sanitize_object_filename():
    assert sanitize_object_filename("bad name!!!.png") == "bad-name-.png"
    assert sanitize_object_filename("") == "image.jpg"
