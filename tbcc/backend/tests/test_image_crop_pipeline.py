from app.services.image_crop_pipeline import (
    ImageCropSettings,
    apply_image_crop_pipeline,
    crop_status_label,
    parse_crop_phrase,
)


def test_parse_crop_off():
    assert parse_crop_phrase("off") == "off"
    assert parse_crop_phrase("clear crop") == "off"


def test_parse_crop_percent_side():
    cfg = parse_crop_phrase("8% bottom")
    assert isinstance(cfg, ImageCropSettings)
    assert cfg.inset_percent == 8
    assert cfg.inset_mode == "bottom"

    cfg2 = parse_crop_phrase("crop 10 percent from top")
    assert cfg2.inset_percent == 10
    assert cfg2.inset_mode == "top"

    cfg3 = parse_crop_phrase("trim 12% all sides")
    assert cfg3.inset_percent == 12
    assert cfg3.inset_mode == "all"


def test_parse_blur_watermark():
    cfg = parse_crop_phrase("blur bottom 12%")
    assert len(cfg.blur_regions) == 1
    assert cfg.blur_regions[0].y > 0.85

    cfg2 = parse_crop_phrase("crop 8% bottom blur bottom 12%")
    assert cfg2.inset_percent == 8
    assert len(cfg2.blur_regions) == 1


def test_parse_watermark_default():
    cfg = parse_crop_phrase("remove watermark")
    assert cfg.inset_percent == 8
    assert cfg.inset_mode == "bottom"


def test_apply_inset_shrinks_image():
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), (255, 0, 0)).save(buf, format="JPEG")
    raw = buf.getvalue()
    cfg = ImageCropSettings(enabled=True, inset_percent=10, inset_mode="all")
    out = apply_image_crop_pipeline(raw, cfg)
    im = Image.open(io.BytesIO(out))
    assert im.size[0] <= 82
    assert im.size[1] <= 82


def test_crop_status_label():
    cfg = ImageCropSettings(enabled=True, inset_percent=8, inset_mode="bottom")
    assert "8%" in crop_status_label(cfg)
    assert crop_status_label(ImageCropSettings()) == "off"
