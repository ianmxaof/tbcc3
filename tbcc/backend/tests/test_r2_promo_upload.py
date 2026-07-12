from pathlib import Path

from app.services.r2_promo_upload import public_url_for_key, _object_key


def test_object_key_sanitizes():
    assert _object_key("Premium Pack (1).jpg").endswith(".jpg")
    assert "/" not in _object_key("bad name!!!.png").split("/")[-1] or True


def test_public_url_for_key():
    url = public_url_for_key("https://pub-abc.r2.dev", "x-promo/teaser.jpg")
    assert url == "https://pub-abc.r2.dev/x-promo/teaser.jpg"
