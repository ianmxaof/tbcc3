"""Reddit caption policy tests."""

from app.models.reddit_subreddit_profile import RedditSubredditProfile
from app.services.reddit_surface_caption import build_reddit_body, build_reddit_title


def test_build_reddit_title_strips_urls():
    t = build_reddit_title(teaser="Check this https://evil.com spam")
    assert "https://" not in t
    assert "spam" in t.lower() or "Check" in t


def test_bio_style_body_no_raw_gate():
    prof = RedditSubredditProfile(name="test", link_policy="bio_style", nsfw_required=False)
    body, comment = build_reddit_body(prof, teaser="Pack drop", utm_campaign="t")
    assert "linkvertise" not in body.lower()
    assert "allmylinks" in body
    assert comment is None


def test_comment_only_puts_link_aside():
    prof = RedditSubredditProfile(name="test", link_policy="comment_only")
    body, comment = build_reddit_body(prof, utm_campaign="t")
    assert "first comment" in body.lower()
    assert comment and comment.startswith("https://")
