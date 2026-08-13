"""Affiliate SFW vs NSFW lane classifier."""

from app.services.affiliate_content_lane import classify_affiliate_lane, placements_for_lane


def test_classify_sfw_hosts():
    assert classify_affiliate_lane("https://cursor.com/referral?code=x", "Cursor") == "sfw"
    assert classify_affiliate_lane("https://www.rakuten.com/r/IANMPO3", "Rakuten") == "sfw"
    assert classify_affiliate_lane("https://www.chime.com/r/x", "Chime") == "sfw"
    assert classify_affiliate_lane("https://pr.tn/ref/95GM632C", "Proton") == "sfw"


def test_classify_nsfw_hosts():
    assert classify_affiliate_lane("https://nodress.site/tg/bot?username=x", "") == "nsfw"
    assert classify_affiliate_lane("https://nudify.now/?code=x", "Nakedly") == "nsfw"


def test_grey_unknown():
    assert classify_affiliate_lane("https://example-unknown-brand.io/deal", "") == "grey"


def test_placements_sfw_silo():
    assert placements_for_lane("sfw") == ["links_hub_sfw"]


def test_placements_nsfw_excludes_checkout():
    nsfw = placements_for_lane("nsfw")
    assert "links_hub_sfw" not in nsfw
    assert "loot_roll" in nsfw


def test_placements_grey_excludes_checkout():
    grey = placements_for_lane("grey")
    assert "links_hub_sfw" not in grey
