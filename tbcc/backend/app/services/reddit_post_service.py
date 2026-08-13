"""Reddit submit via PRAW — dry-run by default."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_reddit_subreddit_registry import AOF_REDDIT_SUBREDDIT_REGISTRY
from app.models.reddit_subreddit_profile import RedditSubredditProfile
from app.services.reddit_global_state import (
    check_global_reddit_eligibility,
    record_global_reddit_post,
)
from app.services.reddit_post_ledger import append_reddit_post_ledger
from app.services.reddit_rules import (
    check_subreddit_eligibility,
    normalize_subreddit_name,
    pick_eligible_subreddits,
    record_subreddit_post_attempt,
    reddit_enabled,
    reddit_execute_enabled,
)
from app.services.reddit_surface_caption import build_reddit_body, build_reddit_title

logger = logging.getLogger(__name__)


@dataclass
class RedditPostPlan:
    subreddit: str
    title: str
    body: str
    comment_link: str | None
    post_kind: str
    nsfw: bool
    flair: str | None
    dry_run: bool
    image_urls: list[str] | None = None
    link_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subreddit": self.subreddit,
            "title": self.title,
            "body": self.body,
            "comment_link": self.comment_link,
            "post_kind": self.post_kind,
            "nsfw": self.nsfw,
            "flair": self.flair,
            "dry_run": self.dry_run,
            "image_urls": self.image_urls or [],
            "link_url": self.link_url,
        }


def _reddit_client():
    import praw

    return praw.Reddit(
        client_id=(os.getenv("TBCC_REDDIT_CLIENT_ID") or "").strip(),
        client_secret=(os.getenv("TBCC_REDDIT_CLIENT_SECRET") or "").strip(),
        username=(os.getenv("TBCC_REDDIT_USERNAME") or "").strip(),
        password=(os.getenv("TBCC_REDDIT_PASSWORD") or "").strip(),
        user_agent=(os.getenv("TBCC_REDDIT_USER_AGENT") or "TBCC:AOF:v1 (by /u/youruser)").strip(),
    )


def seed_registry_profiles(db: Session, *, replace: bool = False) -> int:
    n = 0
    for row in AOF_REDDIT_SUBREDDIT_REGISTRY:
        name = normalize_subreddit_name(str(row.get("name") or ""))
        if not name:
            continue
        prof = db.query(RedditSubredditProfile).filter(RedditSubredditProfile.name == name).first()
        if prof is None:
            prof = RedditSubredditProfile(name=name)
            db.add(prof)
        elif not replace:
            continue
        for key in (
            "status",
            "tier",
            "link_policy",
            "post_kind",
            "nsfw_required",
            "required_flair",
            "min_karma",
            "min_account_age_days",
            "cooldown_hours",
            "max_posts_per_day",
            "max_posts_per_week",
            "notes",
        ):
            if key in row and row[key] is not None:
                setattr(prof, key, row[key])
        prof.updated_at = datetime.utcnow()
        n += 1
    db.commit()
    return n


def account_stats() -> tuple[int | None, int | None]:
    if not reddit_execute_enabled():
        return None, None
    try:
        me = _reddit_client().user.me()
        karma = int(getattr(me, "link_karma", 0) or 0) + int(getattr(me, "comment_karma", 0) or 0)
        created = float(getattr(me, "created_utc", 0) or 0)
        age_days = int((datetime.utcnow().timestamp() - created) / 86400) if created else None
        return karma, age_days
    except Exception as e:
        logger.warning("reddit account stats failed: %s", e)
        return None, None


def plan_post(
    db: Session,
    profile: RedditSubredditProfile,
    *,
    teaser: str | None = None,
    utm_campaign: str = "reddit",
    dry_run: bool | None = None,
    erome_url: str | None = None,
    image_urls: list[str] | None = None,
) -> RedditPostPlan | None:
    karma, age = account_stats()
    el = check_subreddit_eligibility(profile, account_karma=karma, account_age_days=age)
    if not el.ok:
        return None

    kind = str(profile.post_kind or "text")
    link_url = None
    imgs = [u for u in (image_urls or []) if (u or "").startswith("https://")][:4]

    if erome_url and profile.name.lower() == "erome":
        kind = "link"
        link_url = erome_url.strip()
        title = build_reddit_title(teaser=teaser or "AOF gallery")
        body = ""
        comment_link = None
    elif kind == "link" and erome_url:
        link_url = erome_url.strip()
        title = build_reddit_title(teaser=teaser)
        body = ""
        comment_link = None
    else:
        title = build_reddit_title(teaser=teaser)
        body, comment_link = build_reddit_body(profile, teaser=teaser, utm_campaign=utm_campaign)
        if kind in ("image", "gallery") and not imgs:
            kind = "text"

    return RedditPostPlan(
        subreddit=el.subreddit,
        title=title,
        body=body,
        comment_link=comment_link,
        post_kind=kind,
        nsfw=bool(profile.nsfw_required),
        flair=(profile.required_flair or None),
        dry_run=dry_run if dry_run is not None else not reddit_execute_enabled(),
        image_urls=imgs or None,
        link_url=link_url,
    )


def _download_image_paths(urls: list[str]) -> list[str]:
    import tempfile

    import httpx

    paths: list[str] = []
    for url in urls[:4]:
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                r = client.get(url)
            if r.status_code >= 400 or len(r.content) < 256:
                continue
            suffix = ".jpg"
            if "png" in (r.headers.get("content-type") or "").lower():
                suffix = ".png"
            fd, path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(r.content)
            paths.append(path)
        except Exception as e:
            logger.warning("reddit image download failed %s: %s", url[:80], e)
    return paths


def _ledger_row(
    plan: RedditPostPlan,
    *,
    ok: bool,
    dry_run: bool,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    utm_campaign: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "ok": ok,
        "dry_run": dry_run,
        "subreddit": plan.subreddit,
        "post_kind": plan.post_kind,
        "title": plan.title[:200],
        "comment_link": plan.comment_link,
        "utm_campaign": utm_campaign,
    }
    if result:
        row.update(
            {
                "submission_id": result.get("submission_id"),
                "permalink": result.get("permalink"),
                "comment_url": result.get("comment_url"),
            }
        )
    if error:
        row["error"] = error[:500]
    return row


def submit_post(
    db: Session,
    plan: RedditPostPlan,
    *,
    utm_campaign: str | None = None,
) -> dict[str, Any]:
    if plan.dry_run or not reddit_execute_enabled():
        out = {"ok": True, "dry_run": True, "plan": plan.to_dict()}
        try:
            append_reddit_post_ledger(_ledger_row(plan, ok=True, dry_run=True, utm_campaign=utm_campaign))
        except Exception:
            logger.debug("reddit ledger append failed", exc_info=True)
        return out

    global_el = check_global_reddit_eligibility()
    if not global_el.ok:
        out = {"ok": False, "error": global_el.reason, "global": global_el.to_dict()}
        try:
            append_reddit_post_ledger(
                _ledger_row(
                    plan,
                    ok=False,
                    dry_run=False,
                    error=global_el.reason,
                    utm_campaign=utm_campaign,
                )
            )
        except Exception:
            logger.debug("reddit ledger append failed", exc_info=True)
        return out

    prof = (
        db.query(RedditSubredditProfile)
        .filter(RedditSubredditProfile.name == plan.subreddit)
        .first()
    )
    if not prof:
        return {"ok": False, "error": "profile_missing"}

    try:
        reddit = _reddit_client()
        sub = reddit.subreddit(plan.subreddit)
        flair_id = None
        if plan.flair:
            try:
                for f in sub.flair.link_templates.user_selectable():
                    if str(f.get("text") or "").lower() == plan.flair.lower():
                        flair_id = f.get("id")
                        break
            except Exception:
                pass

        if plan.post_kind == "link" and (plan.link_url or plan.comment_link):
            url = (plan.link_url or plan.comment_link or "").strip()
            submission = sub.submit(
                url=url,
                title=plan.title,
                nsfw=plan.nsfw,
                send_replies=False,
                flair_id=flair_id,
            )
        elif plan.post_kind == "gallery" and plan.image_urls:
            paths = _download_image_paths(plan.image_urls)
            if len(paths) >= 2:
                submission = sub.submit_gallery(
                    title=plan.title, images=paths, nsfw=plan.nsfw, flair_id=flair_id
                )
            elif len(paths) == 1:
                submission = sub.submit_image(
                    title=plan.title, image_path=paths[0], nsfw=plan.nsfw, flair_id=flair_id
                )
            else:
                submission = sub.submit(
                    title=plan.title,
                    selftext=plan.body or plan.title,
                    nsfw=plan.nsfw,
                    flair_id=flair_id,
                )
        elif plan.post_kind == "image" and plan.image_urls:
            paths = _download_image_paths(plan.image_urls[:1])
            if paths:
                submission = sub.submit_image(
                    title=plan.title, image_path=paths[0], nsfw=plan.nsfw, flair_id=flair_id
                )
            else:
                submission = sub.submit(
                    title=plan.title,
                    selftext=plan.body,
                    nsfw=plan.nsfw,
                    send_replies=False,
                    flair_id=flair_id,
                )
        else:
            submission = sub.submit(
                title=plan.title,
                selftext=plan.body,
                nsfw=plan.nsfw,
                send_replies=False,
                flair_id=flair_id,
            )

        comment_url = None
        if plan.comment_link and plan.post_kind not in ("link",):
            try:
                c = submission.reply(plan.comment_link)
                comment_url = getattr(c, "permalink", None)
            except Exception as e:
                logger.warning("reddit comment link failed: %s", e)

        record_subreddit_post_attempt(db, prof, ok=True)
        record_global_reddit_post()
        db.commit()
        out = {
            "ok": True,
            "dry_run": False,
            "submission_id": getattr(submission, "id", None),
            "permalink": getattr(submission, "permalink", None),
            "comment_url": comment_url,
        }
        try:
            append_reddit_post_ledger(
                _ledger_row(plan, ok=True, dry_run=False, result=out, utm_campaign=utm_campaign)
            )
        except Exception:
            logger.debug("reddit ledger append failed", exc_info=True)
        return out
    except Exception as e:
        record_subreddit_post_attempt(db, prof, ok=False, skip_reason=str(e)[:200])
        db.commit()
        err = str(e)[:500]
        try:
            append_reddit_post_ledger(
                _ledger_row(plan, ok=False, dry_run=False, error=err, utm_campaign=utm_campaign)
            )
        except Exception:
            logger.debug("reddit ledger append failed", exc_info=True)
        return {"ok": False, "error": err}


def fanout_reddit_teaser(
    db: Session,
    *,
    teaser: str | None = None,
    utm_campaign: str = "fanout",
    limit: int = 1,
    erome_url: str | None = None,
    image_urls: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not reddit_enabled():
        return [{"ok": False, "skipped": True, "reason": "TBCC_REDDIT_ENABLED=0"}]

    global_el = check_global_reddit_eligibility()
    if not global_el.ok:
        return [{"ok": False, "skipped": True, "reason": global_el.reason, "global": global_el.to_dict()}]

    karma, age = account_stats()
    picks = pick_eligible_subreddits(
        db,
        limit=limit,
        account_karma=karma,
        account_age_days=age,
        erome_url=erome_url,
        prefer_gallery=bool(image_urls and len(image_urls) >= 2),
    )
    if not picks:
        return [{"ok": False, "skipped": True, "reason": "no_eligible_subreddit"}]

    results: list[dict[str, Any]] = []
    for prof, _el in picks:
        plan = plan_post(
            db,
            prof,
            teaser=teaser,
            utm_campaign=utm_campaign,
            erome_url=erome_url,
            image_urls=image_urls,
        )
        if not plan:
            results.append({"ok": False, "subreddit": prof.name, "error": "plan_failed"})
            continue
        results.append(submit_post(db, plan, utm_campaign=utm_campaign))
    return results
