"""Instagram carousel posts via Buffer — rotating AOF logos from local library."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from app.services.aof_pack_logos import all_logo_files, is_logo_file
from app.services.promo_image_convert import normalize_promo_image_bytes
from app.services.promo_storage import ensure_promo_dir

logger = logging.getLogger(__name__)

_CAROUSEL_SUBDIR = "aof-logos"
_INDEX_FILE = "buffer_ig_carousel_index.json"


def ig_carousel_enabled() -> bool:
    return (os.getenv("TBCC_BUFFER_IG_CAROUSEL") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def carousel_slide_count() -> int:
    raw = (os.getenv("TBCC_BUFFER_IG_CAROUSEL_SLIDES") or "5").strip()
    try:
        return max(2, min(10, int(raw)))
    except ValueError:
        return 5


def sync_max_logos() -> int:
    raw = (os.getenv("TBCC_BUFFER_IG_CAROUSEL_SYNC_MAX") or "60").strip()
    try:
        return max(5, min(200, int(raw)))
    except ValueError:
        return 60


def promo_public_base() -> str:
    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
    ).rstrip("/")


def carousel_promo_dir() -> Path:
    d = ensure_promo_dir() / _CAROUSEL_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stable_basename(source: Path) -> str:
    h = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"aof-logo-{h}"


def public_url_for_carousel_file(name: str) -> str | None:
    base = promo_public_base()
    if not base.startswith("https://"):
        return None
    safe = Path(name).name
    if not safe or safe != name:
        return None
    path = carousel_promo_dir() / safe
    if not path.is_file():
        return None
    return f"{base}/static/promo/{_CAROUSEL_SUBDIR}/{safe}"


def sync_logos_to_promo(*, limit: int | None = None) -> list[str]:
    """
    Copy/normalize logos from TBCC_AOF_LOGOS_DIR into uploads/promo/aof-logos/.
    Returns sorted public https URLs for synced files.
    """
    cap = limit or sync_max_logos()
    dest = carousel_promo_dir()
    synced: list[str] = []
    for src in all_logo_files()[:cap]:
        if not is_logo_file(src):
            continue
        stem = _stable_basename(src)
        try:
            raw = src.read_bytes()
            data, ext = normalize_promo_image_bytes(raw)
            fname = f"{stem}{ext}"
        except Exception:
            fname = f"{stem}{src.suffix.lower()}"
            data = src.read_bytes()
        out = dest / fname
        if not out.is_file() or out.stat().st_size != len(data):
            out.write_bytes(data)
        url = public_url_for_carousel_file(fname)
        if url:
            synced.append(url)
    synced.sort()
    return synced


def _index_path() -> Path:
    from app.services.import_pipeline import tbcc_run_dir

    return tbcc_run_dir() / _INDEX_FILE


def _read_carousel_index() -> int:
    p = _index_path()
    if not p.is_file():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return int(data.get("index") or 0)
    except Exception:
        return 0


def _write_carousel_index(idx: int) -> None:
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"index": int(idx)}, indent=2) + "\n", encoding="utf-8")


def path_for_carousel_url(url: str) -> Path | None:
    u = (url or "").strip()
    if f"/static/promo/{_CAROUSEL_SUBDIR}/" not in u:
        return None
    name = u.split(f"/static/promo/{_CAROUSEL_SUBDIR}/", 1)[-1].split("?")[0]
    if not name or "/" in name or ".." in name:
        return None
    p = carousel_promo_dir() / name
    return p if p.is_file() else None


def slide1_cta_enabled() -> bool:
    return (os.getenv("TBCC_BUFFER_IG_SLIDE1_CTA") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def slide1_cta_text() -> str:
    from app.services.buffer_surface_caption import aof_mainhub_display

    custom = (os.getenv("TBCC_BUFFER_IG_SLIDE1_CTA_TEXT") or "").strip()
    if custom:
        return custom[:120]
    hub = aof_mainhub_display()
    return f"link in bio · {hub} · allmylinks.com/aof69"


def apply_slide1_cta_watermark(image_path: Path) -> Path:
    """Burn CTA on first carousel slide (cached as *-cta.ext)."""
    if not slide1_cta_enabled() or not image_path.is_file():
        return image_path
    out = image_path.with_name(f"{image_path.stem}-cta{image_path.suffix}")
    if out.is_file() and out.stat().st_mtime >= image_path.stat().st_mtime:
        return out
    try:
        from app.services.media_watermark import WatermarkApplyConfig, maybe_apply_media_watermark

        cfg = WatermarkApplyConfig(
            enabled=True,
            texts=(slide1_cta_text(),),
            mode="fixed",
            position="bottom_right",
            opacity=float(os.getenv("TBCC_BUFFER_IG_SLIDE1_CTA_OPACITY") or "0.72"),
        )
        out.write_bytes(maybe_apply_media_watermark(image_path.read_bytes(), "photo", config=cfg))
        return out
    except Exception as e:
        logger.warning("carousel slide1 CTA watermark failed: %s", e)
        return image_path


def _apply_slide1_cta_to_url(url: str) -> str:
    path = path_for_carousel_url(url)
    if not path:
        return url
    cta_path = apply_slide1_cta_watermark(path)
    pub = public_url_for_carousel_file(cta_path.name)
    return pub or url


def ig_story_enabled() -> bool:
    return (os.getenv("TBCC_BUFFER_IG_STORY_ENABLED") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def instagram_story_metadata(*, link_url: str | None = None) -> dict:
    from app.services.utm_links import allmylinks_tracked_url

    link = (link_url or "").strip() or allmylinks_tracked_url(
        source="buffer",
        medium="instagram_story",
        campaign="hub",
    )
    meta: dict = {
        "instagram": {
            "type": "story",
            "shouldShareToFeed": False,
        }
    }
    if link.startswith("https://"):
        meta["instagram"]["link"] = link
    return meta


def ig_story_create_post_kwargs(*, image_url: str | None = None) -> dict:
    from app.services.aof_social_links import buffer_ig_default_image_url

    url = (image_url or "").strip() or (next_carousel_image_urls(slides=1) or [None])[0]
    if not url:
        url = buffer_ig_default_image_url() or ""
    out: dict = {"metadata": instagram_story_metadata()}
    if url.startswith("https://"):
        out["assets"] = build_image_assets([url], alt_text="AOF Network story")
    return out


def post_instagram_story(
    channel_id: str,
    text: str,
    *,
    mode: str = "shareNow",
    image_url: str | None = None,
) -> dict:
    from app.services.buffer_graphql import create_post

    return create_post(
        channel_id,
        text,
        mode=mode,  # type: ignore[arg-type]
        scheduling_type="automatic",
        **ig_story_create_post_kwargs(image_url=image_url),
    )


def next_carousel_image_urls(*, slides: int | None = None) -> list[str]:
    """Rotate a window of public logo URLs for the next IG carousel."""
    n = slides or carousel_slide_count()
    pool = sync_logos_to_promo()
    if len(pool) < 2:
        from app.services.aof_social_links import buffer_ig_default_image_url

        one = buffer_ig_default_image_url()
        return [one] if one else []
    if len(pool) <= n:
        picked = pool[:n]
    else:
        start = _read_carousel_index() % len(pool)
        picked = [pool[(start + i) % len(pool)] for i in range(n)]
        _write_carousel_index(start + 1)

    if picked and slide1_cta_enabled():
        picked[0] = _apply_slide1_cta_to_url(picked[0])
    return picked


def build_image_assets(urls: list[str], *, alt_text: str = "AOF Network") -> list[dict]:
    assets: list[dict] = []
    for url in urls:
        u = (url or "").strip()
        if not u.startswith("https://"):
            continue
        assets.append(
            {
                "image": {
                    "url": u,
                    "metadata": {"altText": alt_text[:500]},
                }
            }
        )
    return assets


def instagram_post_metadata() -> dict:
    return {
        "instagram": {
            "type": "post",
            "shouldShareToFeed": True,
        }
    }


def ig_create_post_kwargs() -> dict:
    """Keyword args for create_post targeting Instagram (carousel when possible)."""
    from app.services.aof_social_links import buffer_ig_default_image_url

    if ig_carousel_enabled():
        urls = next_carousel_image_urls()
        if len(urls) >= 2:
            return {
                "assets": build_image_assets(urls),
                "metadata": instagram_post_metadata(),
            }
    one = buffer_ig_default_image_url()
    out: dict = {"metadata": instagram_post_metadata()}
    if one:
        out["image_url"] = one
    return out
