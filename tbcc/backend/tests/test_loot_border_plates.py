from pathlib import Path

from PIL import Image

from app.services.loot_border_plates import detect_border_geometry


def test_detect_border_geometry_finds_three_plates():
    im = Image.new("RGB", (512, 512), (20, 20, 24))
    px = im.load()
    # window
    for y in range(120, 360):
        for x in range(120, 392):
            px[x, y] = (255, 0, 255)
    # brand plate top-left
    for y in range(24, 96):
        for x in range(24, 200):
            px[x, y] = (150, 150, 155)
    # right-rail badge
    for y in range(140, 300):
        for x in range(420, 490):
            px[x, y] = (145, 148, 152)
    # bottom plate
    for y in range(410, 470):
        for x in range(90, 422):
            px[x, y] = (148, 150, 152)

    geom = detect_border_geometry(im)
    assert geom["brand_plate"][0] < 0.2
    assert geom["badge_plate"][0] > 0.65
    assert geom["bottom_plate"][1] > 0.7


def test_roll_reveal_rng_varies_with_media_id():
    from app.services.loot_tier_card_assets import roll_reveal_rng

    a = roll_reveal_rng({"seed": 1, "media": [{"id": 10}]})
    b = roll_reveal_rng({"seed": 1, "media": [{"id": 11}]})
    assert a.randint(0, 10**9) != b.randint(0, 10**9)


def test_card_crop_frac_trims_magenta_letterbox():
    from app.services.loot_border_plates import _card_crop_from_image, card_crop_bbox_px

    im = Image.new("RGB", (400, 400), (255, 0, 255))
    px = im.load()
    for y in range(60, 340):
        for x in range(50, 350):
            px[x, y] = (90, 95, 100)
    crop = _card_crop_from_image(im)
    assert crop[0] > 0.08
    assert crop[2] < 0.92
    x0, y0, x1, y1 = card_crop_bbox_px(im)
    assert x0 >= 45
    assert x1 <= 355


def test_ffmpeg_chrome_crop_scale_chain_includes_crop():
    from app.services.loot_border_plates import ffmpeg_chrome_crop_scale_chain

    chain = ffmpeg_chrome_crop_scale_chain((40, 30, 360, 370), size=512)
    assert "crop=320:340:40:30" in chain
    assert "scale=512:512" in chain


def test_is_key_detects_pink_gutter():
    from app.services.loot_border_plates import _is_key

    assert _is_key(255, 0, 255)
    assert _is_key(230, 40, 210)
    assert not _is_key(90, 95, 100)
