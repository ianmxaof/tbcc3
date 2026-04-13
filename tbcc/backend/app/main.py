from pathlib import Path
from dotenv import load_dotenv

# override=True: tbcc/.env wins over inherited shell env (avoids mismatched TBCC_INTERNAL_API_KEY vs payment bot).
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api import analytics, bots, channels, forum, media, jobs, import_, pools, referrals, sources, subscriptions, subscription_plans, scheduled_posts, external_payment_orders, growth_settings, internal_launch, tags, llm_shop, webhooks_payment
from app.database.session import engine
from app.models.base import Base
from app.services.promo_storage import ensure_promo_dir

_EXTERNAL_PAY_IMPL = getattr(
    external_payment_orders, "EXTERNAL_PAYMENT_ORDERS_IMPL", "unknown"
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram Bot Command Center")


@app.on_event("startup")
def on_startup():
    from app.services.bundle_storage import ensure_bundle_dir

    ensure_bundle_dir()
    url = str(engine.url)
    if "sqlite" in url:
        Base.metadata.create_all(bind=engine)
        # create_all() does not ALTER existing SQLite tables — add columns from newer models if missing.
        try:
            inspector = inspect(engine)
            if "content_pools" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("content_pools")}
                if "randomize_queue" not in cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE content_pools ADD COLUMN randomize_queue BOOLEAN NOT NULL DEFAULT 0"
                            )
                        )
                    logger.info("SQLite: added content_pools.randomize_queue (dev migration)")
                if "auto_post_enabled" not in cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE content_pools ADD COLUMN auto_post_enabled BOOLEAN NOT NULL DEFAULT 1"
                            )
                        )
                    logger.info("SQLite: added content_pools.auto_post_enabled (dev migration)")
            if "subscription_plans" in inspector.get_table_names():
                sp_cols = {c["name"] for c in inspector.get_columns("subscription_plans")}
                with engine.begin() as conn:
                    if "description" not in sp_cols:
                        conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN description TEXT"))
                        logger.info("SQLite: added subscription_plans.description (dev migration)")
                    if "is_active" not in sp_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE subscription_plans ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
                            )
                        )
                        logger.info("SQLite: added subscription_plans.is_active (dev migration)")
                    if "product_type" not in sp_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE subscription_plans ADD COLUMN product_type VARCHAR(32) NOT NULL DEFAULT 'subscription'"
                            )
                        )
                        logger.info("SQLite: added subscription_plans.product_type (dev migration)")
                    if "promo_image_url" not in sp_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE subscription_plans ADD COLUMN promo_image_url VARCHAR(1024)"
                            )
                        )
                        logger.info("SQLite: added subscription_plans.promo_image_url (dev migration)")
                    if "bundle_zip_original_name" not in sp_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE subscription_plans ADD COLUMN bundle_zip_original_name VARCHAR(512)"
                            )
                        )
                        logger.info("SQLite: added subscription_plans.bundle_zip_original_name (dev migration)")
                    if "promo_image_urls_json" not in sp_cols:
                        conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN promo_image_urls_json TEXT"))
                        logger.info("SQLite: added subscription_plans.promo_image_urls_json (dev migration)")
                    if "bundle_zip2_original_name" not in sp_cols:
                        conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN bundle_zip2_original_name VARCHAR(512)"))
                        logger.info("SQLite: added subscription_plans.bundle_zip2_original_name (dev migration)")
                    if "bundle_zip_parts_json" not in sp_cols:
                        conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN bundle_zip_parts_json TEXT"))
                        logger.info("SQLite: added subscription_plans.bundle_zip_parts_json (dev migration)")
                    if "description_variations_json" not in sp_cols:
                        conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN description_variations_json TEXT"))
                        logger.info("SQLite: added subscription_plans.description_variations_json (dev migration)")
                    if "plan_tag_ids_json" not in sp_cols:
                        conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN plan_tag_ids_json TEXT"))
                        logger.info("SQLite: added subscription_plans.plan_tag_ids_json (dev migration)")
            if "scheduled_text_posts" in inspector.get_table_names():
                st_cols = {c["name"] for c in inspector.get_columns("scheduled_text_posts")}
                with engine.begin() as conn:
                    if "album_size" not in st_cols:
                        conn.execute(text("ALTER TABLE scheduled_text_posts ADD COLUMN album_size INTEGER"))
                        logger.info("SQLite: added scheduled_text_posts.album_size (dev migration)")
                    if "pool_randomize" not in st_cols:
                        conn.execute(
                            text("ALTER TABLE scheduled_text_posts ADD COLUMN pool_randomize BOOLEAN")
                        )
                        logger.info("SQLite: added scheduled_text_posts.pool_randomize (dev migration)")
                    if "content_variations" not in st_cols:
                        conn.execute(text("ALTER TABLE scheduled_text_posts ADD COLUMN content_variations TEXT"))
                        logger.info("SQLite: added scheduled_text_posts.content_variations (dev migration)")
                    if "caption_rotation_index" not in st_cols:
                        conn.execute(text("ALTER TABLE scheduled_text_posts ADD COLUMN caption_rotation_index INTEGER"))
                        logger.info("SQLite: added scheduled_text_posts.caption_rotation_index (dev migration)")
                    if "message_thread_id" not in st_cols:
                        conn.execute(text("ALTER TABLE scheduled_text_posts ADD COLUMN message_thread_id INTEGER"))
                        logger.info("SQLite: added scheduled_text_posts.message_thread_id (forum topic, dev migration)")
                    if "attachment_urls_json" not in st_cols:
                        conn.execute(text("ALTER TABLE scheduled_text_posts ADD COLUMN attachment_urls_json TEXT"))
                        logger.info("SQLite: added scheduled_text_posts.attachment_urls_json (dev migration)")
                    if "album_variants_json" not in st_cols:
                        conn.execute(text("ALTER TABLE scheduled_text_posts ADD COLUMN album_variants_json TEXT"))
                        logger.info("SQLite: added scheduled_text_posts.album_variants_json (dev migration)")
                    if "album_order_mode" not in st_cols:
                        conn.execute(
                            text("ALTER TABLE scheduled_text_posts ADD COLUMN album_order_mode VARCHAR(16)")
                        )
                        logger.info("SQLite: added scheduled_text_posts.album_order_mode (dev migration)")
                    if "album_carousel_index" not in st_cols:
                        conn.execute(
                            text("ALTER TABLE scheduled_text_posts ADD COLUMN album_carousel_index INTEGER")
                        )
                        logger.info("SQLite: added scheduled_text_posts.album_carousel_index (dev migration)")
                    if "pool_only_mode" not in st_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN pool_only_mode BOOLEAN NOT NULL DEFAULT 0"
                            )
                        )
                        logger.info("SQLite: added scheduled_text_posts.pool_only_mode (dev migration)")
                    if "send_silent" not in st_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN send_silent BOOLEAN NOT NULL DEFAULT 0"
                            )
                        )
                        logger.info("SQLite: added scheduled_text_posts.send_silent (dev migration)")
                    if "pin_after_send" not in st_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN pin_after_send BOOLEAN NOT NULL DEFAULT 0"
                            )
                        )
                        logger.info("SQLite: added scheduled_text_posts.pin_after_send (dev migration)")
            if "subscriptions" in inspector.get_table_names():
                sub_cols = {c["name"] for c in inspector.get_columns("subscriptions")}
                if "telegram_payment_charge_id" not in sub_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE subscriptions ADD COLUMN telegram_payment_charge_id VARCHAR(128)"
                            )
                        )
                        conn.execute(
                            text(
                                "CREATE UNIQUE INDEX IF NOT EXISTS ix_subscriptions_telegram_payment_charge_id "
                                "ON subscriptions(telegram_payment_charge_id)"
                            )
                        )
                    logger.info("SQLite: added subscriptions.telegram_payment_charge_id (dev migration)")
        except Exception:
            logger.exception("SQLite column patch failed; run: cd backend && alembic upgrade head")
    else:
        logger.info(
            "Postgres (or non-SQLite): tables are not auto-created here. "
            "If API returns UndefinedTable, run: cd backend && python -m alembic upgrade head"
        )
        # Keep Postgres dev/prod resilient when model columns are added before alembic is applied.
        try:
            inspector = inspect(engine)
            if "content_pools" in inspector.get_table_names():
                cp_cols = {c["name"] for c in inspector.get_columns("content_pools")}
                if "auto_post_enabled" not in cp_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE content_pools ADD COLUMN auto_post_enabled BOOLEAN NOT NULL DEFAULT TRUE"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added content_pools.auto_post_enabled (startup migration)"
                    )
        except Exception:
            logger.exception(
                "PostgreSQL: could not add content_pools.auto_post_enabled — run: "
                "cd backend && alembic upgrade head"
            )
        # Same as Alembic 026: scheduled promo URLs (dashboard) — many deployments skip alembic upgrade.
        try:
            inspector = inspect(engine)
            if "scheduled_text_posts" in inspector.get_table_names():
                st_cols = {c["name"] for c in inspector.get_columns("scheduled_text_posts")}
                if "pool_only_mode" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN pool_only_mode BOOLEAN NOT NULL DEFAULT FALSE"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.pool_only_mode (startup migration)"
                    )
                if "attachment_urls_json" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN attachment_urls_json TEXT"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.attachment_urls_json (startup migration)"
                    )
                if "album_variants_json" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN album_variants_json TEXT"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.album_variants_json (startup migration)"
                    )
                if "album_order_mode" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN album_order_mode VARCHAR(16)"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.album_order_mode (startup migration)"
                    )
                if "album_carousel_index" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN album_carousel_index INTEGER"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.album_carousel_index (startup migration)"
                    )
                if "send_silent" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN send_silent BOOLEAN NOT NULL DEFAULT FALSE"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.send_silent (startup migration)"
                    )
                if "pin_after_send" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN pin_after_send BOOLEAN NOT NULL DEFAULT FALSE"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.pin_after_send (startup migration)"
                    )
        except Exception:
            logger.exception(
                "PostgreSQL: could not add scheduled_text_posts columns — run: "
                "cd backend && alembic upgrade head"
            )

    logger.info(
        "TBCC API ready: main_py=%s external_payment_orders_impl=%s",
        __file__,
        _EXTERNAL_PAY_IMPL,
    )


@app.on_event("shutdown")
async def on_shutdown():
    from app.services.telegram_admin import disconnect_admin

    await disconnect_admin()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bots.router, prefix="/bots", tags=["bots"])
app.include_router(channels.router, prefix="/channels", tags=["channels"])
app.include_router(forum.router, prefix="/forum", tags=["forum"])
app.include_router(media.router, prefix="/media", tags=["media"])
app.include_router(tags.router, prefix="/tags", tags=["tags"])
app.include_router(llm_shop.router, prefix="/llm", tags=["llm"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(import_.router, prefix="/import", tags=["import"])
app.include_router(pools.router, prefix="/pools", tags=["pools"])
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])
app.include_router(referrals.router, prefix="/referrals", tags=["referrals"])
app.include_router(growth_settings.router, prefix="/growth-settings", tags=["growth-settings"])
app.include_router(external_payment_orders.router, prefix="/external-payment-orders", tags=["external-payment-orders"])
app.include_router(webhooks_payment.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(subscription_plans.router, prefix="/subscription-plans", tags=["subscription-plans"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(scheduled_posts.router, prefix="/scheduled-posts", tags=["scheduled-posts"])
app.include_router(internal_launch.router, prefix="/internal", tags=["internal"])


@app.get("/")
def root():
    """Avoid bare 404 at / — FastAPI has no default index; use /docs or /health."""
    return {
        "service": "TBCC API",
        "health": "/health",
        "docs": "/docs",
        "openapi": "/openapi.json",
        # Proof of which files this process loaded (if missing, you are not on current main.py).
        "main_py": __file__,
        "external_payment_orders_impl": _EXTERNAL_PAY_IMPL,
    }


@app.get("/health")
def health():
    # no-store: browsers were caching {"status":"ok"} and hiding new fields during dev
    return JSONResponse(
        content={
            "status": "ok",
            "external_payment_orders_impl": _EXTERNAL_PAY_IMPL,
        },
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/health/db")
def health_db():
    """Quick DB connectivity check for dashboard / ops (does not require auth)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception as e:
        logger.exception("health_db check failed")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "database": "unreachable",
                "detail": str(e),
            },
        )


# Public promo images for /shop (Telegram send_photo URL must reach this from the internet in production)
_promo_dir = ensure_promo_dir()
app.mount(
    "/static/promo",
    StaticFiles(directory=str(_promo_dir)),
    name="promo_uploads",
)
