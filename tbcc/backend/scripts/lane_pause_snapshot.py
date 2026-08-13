"""One-off: lane pause + inventory snapshot for operator."""
from sqlalchemy import func

from app.database.session import SessionLocal
from app.data.aof_network import network_channel_by_key
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost

KEYS = ("goon", "bop", "abg", "ai")
MIN_IMG = 2500
MIN_VID = 2500


def main() -> None:
    db = SessionLocal()
    try:
        for k in KEYS:
            net = network_channel_by_key(k)
            ch = (
                db.query(Channel).filter(Channel.identifier == net.identifier).first()
                if net
                else None
            )
            pool = (
                db.query(ContentPool).filter(ContentPool.name == net.pool_name).first()
                if net
                else None
            )
            imgs = vids = 0
            if pool:
                imgs = (
                    db.query(func.count(Media.id))
                    .filter(
                        Media.pool_id == pool.id,
                        Media.status == "approved",
                        Media.media_type == "photo",
                    )
                    .scalar()
                    or 0
                )
                vids = (
                    db.query(func.count(Media.id))
                    .filter(
                        Media.pool_id == pool.id,
                        Media.status == "approved",
                        Media.media_type == "video",
                    )
                    .scalar()
                    or 0
                )
            ready = imgs >= MIN_IMG and vids >= MIN_VID
            print(f"=== {k} === ready_subtopic={ready} ({imgs} img / {vids} vid; need {MIN_IMG}/{MIN_VID})")
            if pool:
                print(
                    f"  pool auto_post={pool.auto_post_enabled} interval={pool.interval_minutes}min"
                )
            if not ch:
                print("  channel row missing")
                continue
            scheds = db.query(ScheduledTextPost).filter(ScheduledTextPost.channel_id == ch.id).all()
            if not scheds:
                print("  no schedulers")
            for s in scheds:
                paused = "AUTO-PAUSED" if s.posting_auto_paused_at else "active"
                print(f"  [{paused}] {s.name} fails={getattr(s, 'send_failure_streak', 0) or 0}")
                if s.posting_auto_pause_reason:
                    print(f"    reason: {s.posting_auto_pause_reason[:120]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
