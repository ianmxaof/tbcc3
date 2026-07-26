from app.data.scrape_lane_priority import (
    PHOTO_STARVED_LANE_KEYS,
    scrape_media_type_bias,
    scrape_priority_rank,
)


def test_photo_starved_bias() -> None:
    for k in PHOTO_STARVED_LANE_KEYS:
        assert scrape_media_type_bias(k) == "photos"
    assert scrape_media_type_bias("ai") == "videos"
    assert scrape_media_type_bias("ass") == "both"


def test_priority_order() -> None:
    assert scrape_priority_rank("taboo") < scrape_priority_rank("ass")
    assert scrape_priority_rank("unknown_lane") == 999
