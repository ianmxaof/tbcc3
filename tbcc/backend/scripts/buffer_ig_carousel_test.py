"""Sync AOF logos and test Buffer Instagram carousel post. Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.buffer_graphql import create_post, find_channel_id_by_service
from app.services.buffer_ig_carousel import (
    carousel_slide_count,
    ig_create_post_kwargs,
    ig_story_enabled,
    next_carousel_image_urls,
    post_instagram_story,
    promo_public_base,
    sync_logos_to_promo,
)
from app.services.buffer_post_result import buffer_create_post_error_message, buffer_create_post_succeeded


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Buffer IG logo carousel — sync + optional test post")
    p.add_argument("--sync", action="store_true", help="Sync logos from TBCC_AOF_LOGOS_DIR to promo host")
    p.add_argument("--preview", action="store_true", help="Show next carousel URLs")
    p.add_argument("--execute", action="store_true", help="shareNow test post to Instagram channel")
    p.add_argument("--story", action="store_true", help="Also post IG story with link sticker (shareNow)")
    p.add_argument("--slides", type=int, default=None, help="Carousel slide count (2-10)")
    args = p.parse_args()

    base = promo_public_base()
    if not base.startswith("https://"):
        print("ERROR: set TBCC_PROMO_PUBLIC_BASE_URL to a live https:// API (ngrok)", file=sys.stderr)
        return 2

    if args.sync or args.execute or args.preview:
        urls = sync_logos_to_promo()
        print(f"synced {len(urls)} logos under /static/promo/aof-logos/", file=sys.stderr)

    slides = args.slides or carousel_slide_count()
    next_urls = next_carousel_image_urls(slides=slides)
    print(json.dumps({"slides": len(next_urls), "urls": next_urls}, indent=2, ensure_ascii=False))

    if not args.execute:
        if not (args.sync or args.preview):
            p.print_help()
        return 0

    ig_id = find_channel_id_by_service("instagram")
    if not ig_id:
        print("ERROR: no Instagram channel in Buffer", file=sys.stderr)
        return 2

    from app.services.buffer_surface_caption import build_instagram_caption

    text = build_instagram_caption(
        teaser="Logo carousel — swipe the stack. Slide 1 has link-in-bio CTA burned in.",
        utm_campaign="logo_carousel_test",
    )

    kwargs = ig_create_post_kwargs()
    print("post kwargs:", json.dumps({k: v for k, v in kwargs.items() if k != "assets"}, indent=2), file=sys.stderr)
    print(f"assets: {len(kwargs.get('assets') or [])}", file=sys.stderr)

    res = create_post(
        ig_id,
        text,
        mode="shareNow",
        scheduling_type="automatic",
        **kwargs,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False)[:4000])
    if buffer_create_post_succeeded(res):
        print("OK — Instagram carousel queued/published via Buffer shareNow", file=sys.stderr)
        if args.story or ig_story_enabled():
            story_res = post_instagram_story(
                ig_id,
                build_instagram_caption(teaser="Story → tap link sticker.", utm_campaign="logo_carousel_story"),
                mode="shareNow",
                image_url=next_urls[0] if next_urls else None,
            )
            print(json.dumps(story_res, indent=2, ensure_ascii=False)[:2000])
            if buffer_create_post_succeeded(story_res):
                print("OK — Instagram story shareNow", file=sys.stderr)
            else:
                print(f"Story FAIL: {buffer_create_post_error_message(story_res)}", file=sys.stderr)
        return 0
    err = buffer_create_post_error_message(res) or "createPost failed"
    print(f"FAIL: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
