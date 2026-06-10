from pathlib import Path
from dotenv import load_dotenv

# override=True: tbcc/.env wins over inherited shell env (avoids mismatched TBCC_INTERNAL_API_KEY vs payment bot).
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api import analytics, bots, channels, forum, media, jobs, import_, pools, referrals, sources, subscriptions, subscription_plans, scheduled_posts, external_payment_orders, growth_settings, internal_launch, tags, llm_shop, webhooks_payment, watch_folder, payment_bot_settings, loot_bot_settings, loot, link_resolver, crawler, jdownloader, caption_snippets, listening_relay_settings, promo_affiliate_links, telegram_custom_emoji, emoji_factory, zip_bundle_settings, gallery_send_promo, watermark_settings, archive, macro_search_submissions, secretary, automation, ops_focus, ops_alerts, extension_context_menu, album_composer_drafts
from app.database.session import engine
from app.models.base import Base
from app.models.payment_bot_settings import PaymentBotSettings  # noqa: F401
from app.models.link_resolver_request import LinkResolverRequest  # noqa: F401
from app.models.loot_bot_settings import LootBotSettings  # noqa: F401
from app.models.caption_snippet import CaptionSnippet  # noqa: F401
from app.models.emoji_factory_sketch import EmojiFactorySketchPage  # noqa: F401
from app.models.listening_relay_settings import ListeningRelaySettings  # noqa: F401
from app.models.zip_bundle_settings import ZipBundleSettings  # noqa: F401
from app.models.promo_affiliate_link import PromoAffiliateLink  # noqa: F401
from app.models.capture_archive_entry import CaptureArchiveEntry  # noqa: F401
from app.models.macro_search_source_submission import MacroSearchSourceSubmission  # noqa: F401
from app.models.import_job import ImportJob  # noqa: F401
from app.models.secretary_user_context import SecretaryMessageRecord, SecretaryUserContext  # noqa: F401
from app.models.secretary_settings import SecretarySettings  # noqa: F401
from app.models.secretary_knowledge import SecretaryKnowledgeEntry  # noqa: F401
from app.services.promo_storage import ensure_promo_dir
from app.services.zip_promo_storage import ensure_zip_promo_dir
from app.services.send_promo_storage import ensure_send_promo_dir
from app.services.bundle_storage import ensure_bundle_dir
from app.services.nowpayments_client import crypto_auto_checkout_ready

_EXTERNAL_PAY_IMPL = getattr(
    external_payment_orders, "EXTERNAL_PAYMENT_ORDERS_IMPL", "unknown"
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram Bot Command Center")


@app.on_event("startup")
def on_startup():
    from app.services.bundle_storage import ensure_bundle_dir
    from app.services.system_health import auto_remediate_on_startup
    from app.utils.telethon_session import (
        admin_session_stem,
        import_session_stem,
        import_sessions_share_admin_file,
        poster_session_stem,
        telethon_sessions_share_file,
    )

    auto_remediate_on_startup()
    ensure_bundle_dir()
    try:
        from app.services.focus_profile import (
            focus_auto_import_enabled,
            focus_auto_react_enabled,
            focus_watch_loop_enabled,
            evaluate_and_maybe_auto_apply,
        )
        import threading

        if focus_watch_loop_enabled():

            def _focus_watch_loop() -> None:
                import time

                while True:
                    time.sleep(25)
                    try:
                        evaluate_and_maybe_auto_apply()
                    except Exception:
                        logger.debug("focus watch loop tick failed", exc_info=True)

            threading.Thread(target=_focus_watch_loop, name="tbcc-focus-watch", daemon=True).start()
            parts = []
            if focus_auto_react_enabled():
                parts.append("auto-react")
            if focus_auto_import_enabled():
                parts.append("auto-import-burst")
            logger.info("TBCC focus watch loop: %s", ", ".join(parts) or "on")
    except Exception:
        logger.debug("focus watch loop not started", exc_info=True)
    if telethon_sessions_share_file():
        logger.warning(
            "Telethon admin and poster sessions share one file (%s.session). "
            "Set TBCC_POSTER_TELEGRAM_SESSION=admin_poster and TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1 "
            "in tbcc/.env to avoid 'database is locked' during sends.",
            Path(admin_session_stem()).name,
        )
    else:
        logger.info(
            "Telethon sessions: admin=%s.session poster=%s.session import=%s.session",
            Path(admin_session_stem()).name,
            Path(poster_session_stem()).name,
            Path(import_session_stem()).name,
        )
    if import_sessions_share_admin_file():
        logger.warning(
            "Telethon imports share admin.session — bulk channel imports will contend with "
            "dashboard thumbnails. Set TBCC_IMPORT_TELEGRAM_SESSION=admin_import and "
            "TBCC_IMPORT_AUTO_COPY_ADMIN_SESSION=1 in tbcc/.env, then restart API + Celery."
        )
    url = str(engine.url)
    if "sqlite" in url:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS payment_bot_settings ("
                    "id INTEGER PRIMARY KEY, "
                    "main_menu_json TEXT, "
                    "welcome_html TEXT, "
                    "loot_intro_html TEXT, "
                    "subscribe_title_main VARCHAR(128), "
                    "subscribe_title_loot VARCHAR(128), "
                    "subscription_catalog_columns INTEGER, "
                    "min_subscription_stars INTEGER, "
                    "runtime_adapter VARCHAR(32), "
                    "runtime_cmd_start TEXT, "
                    "runtime_cmd_stop TEXT, "
                    "runtime_cmd_restart TEXT, "
                    "runtime_cmd_reload TEXT, "
                    "runtime_cmd_status TEXT, "
                    "video_finder_enabled INTEGER, "
                    "video_finder_sources_json TEXT, "
                    "video_finder_max_links_per_source INTEGER)"
                )
            )
        try:
            inspector = inspect(engine)
            if "payment_bot_settings" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("payment_bot_settings")}
                with engine.begin() as conn:
                    if "runtime_adapter" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_adapter VARCHAR(32)"))
                    if "runtime_cmd_start" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_start TEXT"))
                    if "runtime_cmd_stop" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_stop TEXT"))
                    if "runtime_cmd_restart" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_restart TEXT"))
                    if "runtime_cmd_reload" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_reload TEXT"))
                    if "runtime_cmd_status" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_status TEXT"))
                    if "video_finder_enabled" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN video_finder_enabled INTEGER"))
                    if "video_finder_sources_json" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN video_finder_sources_json TEXT"))
                    if "video_finder_max_links_per_source" not in cols:
                        conn.execute(
                            text(
                                "ALTER TABLE payment_bot_settings ADD COLUMN video_finder_max_links_per_source INTEGER"
                            )
                        )
                    if "macro_search_custom_sources_json" not in cols:
                        conn.execute(
                            text("ALTER TABLE payment_bot_settings ADD COLUMN macro_search_custom_sources_json TEXT")
                        )
                    if "macro_search_disabled_json" not in cols:
                        conn.execute(
                            text("ALTER TABLE payment_bot_settings ADD COLUMN macro_search_disabled_json TEXT")
                        )
        except Exception:
            logger.exception("SQLite: failed to patch payment_bot_settings columns")
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
                if "route_match_tag_slugs" not in cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE content_pools ADD COLUMN route_match_tag_slugs VARCHAR(512)"
                            )
                        )
                    logger.info("SQLite: added content_pools.route_match_tag_slugs (dev migration)")
                if "route_priority" not in cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE content_pools ADD COLUMN route_priority INTEGER NOT NULL DEFAULT 100"
                            )
                        )
                    logger.info("SQLite: added content_pools.route_priority (dev migration)")
                if "route_nsfw_tiers" not in cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE content_pools ADD COLUMN route_nsfw_tiers VARCHAR(128)"
                            )
                        )
                    logger.info("SQLite: added content_pools.route_nsfw_tiers (dev migration)")
            if "media" in inspector.get_table_names():
                mcols = {c["name"] for c in inspector.get_columns("media")}
                with engine.begin() as conn:
                    if "nsfw_tier" not in mcols:
                        conn.execute(text("ALTER TABLE media ADD COLUMN nsfw_tier VARCHAR(16)"))
                        logger.info("SQLite: added media.nsfw_tier (dev migration)")
                    if "classification_json" not in mcols:
                        conn.execute(text("ALTER TABLE media ADD COLUMN classification_json TEXT"))
                        logger.info("SQLite: added media.classification_json (dev migration)")
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
                    if "bot_section" not in sp_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE subscription_plans ADD COLUMN bot_section VARCHAR(32) NOT NULL DEFAULT 'main'"
                            )
                        )
                        logger.info("SQLite: added subscription_plans.bot_section (dev migration)")
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
                    if "campaign_group_id" not in st_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN campaign_group_id VARCHAR(36)"
                            )
                        )
                        logger.info("SQLite: added scheduled_text_posts.campaign_group_id (dev migration)")
                    if "send_failure_streak" not in st_cols:
                        conn.execute(text("ALTER TABLE scheduled_text_posts ADD COLUMN send_failure_streak INTEGER"))
                        logger.info("SQLite: added scheduled_text_posts.send_failure_streak (dev migration)")
                    if "posting_auto_paused_at" not in st_cols:
                        conn.execute(text("ALTER TABLE scheduled_text_posts ADD COLUMN posting_auto_paused_at DATETIME"))
                        logger.info("SQLite: added scheduled_text_posts.posting_auto_paused_at (dev migration)")
                    if "posting_auto_pause_reason" not in st_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN posting_auto_pause_reason VARCHAR(512)"
                            )
                        )
                        logger.info("SQLite: added scheduled_text_posts.posting_auto_pause_reason (dev migration)")
                    if "campaign_random_channel" not in st_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN campaign_random_channel BOOLEAN NOT NULL DEFAULT 0"
                            )
                        )
                        logger.info(
                            "SQLite: added scheduled_text_posts.campaign_random_channel (dev migration)"
                        )
                    if "pool_collective_random" not in st_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN pool_collective_random BOOLEAN NOT NULL DEFAULT 0"
                            )
                        )
                        logger.info(
                            "SQLite: added scheduled_text_posts.pool_collective_random (dev migration)"
                        )
                    if "buffer_mirror_enabled" not in st_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN buffer_mirror_enabled BOOLEAN NOT NULL DEFAULT 0"
                            )
                        )
                        logger.info("SQLite: added scheduled_text_posts.buffer_mirror_enabled (dev migration)")
                    if "buffer_x_queue_json" not in st_cols:
                        conn.execute(
                            text("ALTER TABLE scheduled_text_posts ADD COLUMN buffer_x_queue_json TEXT")
                        )
                        logger.info("SQLite: added scheduled_text_posts.buffer_x_queue_json (dev migration)")
                    if "buffer_publish_now" not in st_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN buffer_publish_now BOOLEAN NOT NULL DEFAULT 0"
                            )
                        )
                        logger.info("SQLite: added scheduled_text_posts.buffer_publish_now (dev migration)")
                    for col, ddl in (
                        ("caption_llm_rewrite_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
                        ("caption_llm_rewrite_mode", "VARCHAR(16)"),
                        ("caption_llm_rewrite_interval", "INTEGER"),
                        ("caption_llm_rewrite_probability", "REAL"),
                        ("caption_llm_send_count", "INTEGER NOT NULL DEFAULT 0"),
                        ("last_sent_caption_html", "TEXT"),
                    ):
                        if col not in st_cols:
                            conn.execute(
                                text(f"ALTER TABLE scheduled_text_posts ADD COLUMN {col} {ddl}")
                            )
                            logger.info("SQLite: added scheduled_text_posts.%s (dev migration)", col)
            if "listening_relay_settings" in inspector.get_table_names():
                lr_cols = {c["name"] for c in inspector.get_columns("listening_relay_settings")}
                with engine.begin() as conn:
                    if "message_template_variations" not in lr_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN message_template_variations TEXT"
                            )
                        )
                        logger.info(
                            "SQLite: added listening_relay_settings.message_template_variations (dev migration)"
                        )
                    if "message_template_rotation_index" not in lr_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN message_template_rotation_index INTEGER"
                            )
                        )
                        logger.info(
                            "SQLite: added listening_relay_settings.message_template_rotation_index (dev migration)"
                        )
                    if "message_footer_html" not in lr_cols:
                        conn.execute(text("ALTER TABLE listening_relay_settings ADD COLUMN message_footer_html TEXT"))
                        logger.info("SQLite: added listening_relay_settings.message_footer_html (dev migration)")
                    if "message_footer_variations" not in lr_cols:
                        conn.execute(
                            text("ALTER TABLE listening_relay_settings ADD COLUMN message_footer_variations TEXT")
                        )
                        logger.info(
                            "SQLite: added listening_relay_settings.message_footer_variations (dev migration)"
                        )
                    if "message_copy_block_variations" not in lr_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN message_copy_block_variations TEXT"
                            )
                        )
                        logger.info(
                            "SQLite: added listening_relay_settings.message_copy_block_variations (dev migration)"
                        )
                    if "buffer_relay_enabled" not in lr_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_enabled BOOLEAN NOT NULL DEFAULT 0"
                            )
                        )
                        logger.info("SQLite: added listening_relay_settings.buffer_relay_enabled (dev migration)")
                    if "buffer_relay_min_interval_minutes" not in lr_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_min_interval_minutes INTEGER NOT NULL DEFAULT 360"
                            )
                        )
                        logger.info(
                            "SQLite: added listening_relay_settings.buffer_relay_min_interval_minutes (dev migration)"
                        )
                    if "buffer_relay_max_per_day_utc" not in lr_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_max_per_day_utc INTEGER NOT NULL DEFAULT 5"
                            )
                        )
                        logger.info(
                            "SQLite: added listening_relay_settings.buffer_relay_max_per_day_utc (dev migration)"
                        )
                    if "buffer_relay_utc_day" not in lr_cols:
                        conn.execute(
                            text("ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_utc_day VARCHAR(10)")
                        )
                        logger.info("SQLite: added listening_relay_settings.buffer_relay_utc_day (dev migration)")
                    if "buffer_relay_posts_today" not in lr_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_posts_today INTEGER NOT NULL DEFAULT 0"
                            )
                        )
                        logger.info(
                            "SQLite: added listening_relay_settings.buffer_relay_posts_today (dev migration)"
                        )
                    if "buffer_relay_last_post_at" not in lr_cols:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_last_post_at DATETIME"
                            )
                        )
                        logger.info(
                            "SQLite: added listening_relay_settings.buffer_relay_last_post_at (dev migration)"
                        )
                    for col, ddl in (
                        ("template_rotation_mode", "VARCHAR(16) NOT NULL DEFAULT 'sequential'"),
                        ("message_slot_extras_json", "TEXT"),
                        ("ascii_art_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
                        ("ascii_art_min_interval", "INTEGER NOT NULL DEFAULT 3"),
                        ("ascii_art_max_interval", "INTEGER NOT NULL DEFAULT 6"),
                        ("ascii_art_scrobble_counter", "INTEGER NOT NULL DEFAULT 0"),
                        ("ascii_art_next_threshold", "INTEGER"),
                        ("ascii_art_library_json", "TEXT"),
                        ("tryptych_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
                        ("tryptych_on_ascii_beat", "BOOLEAN NOT NULL DEFAULT 1"),
                    ):
                        if col not in lr_cols:
                            conn.execute(
                                text(f"ALTER TABLE listening_relay_settings ADD COLUMN {col} {ddl}")
                            )
                            logger.info(
                                "SQLite: added listening_relay_settings.%s (dev migration)", col
                            )
            if "promo_affiliate_links" in inspector.get_table_names():
                pa_cols = {c["name"] for c in inspector.get_columns("promo_affiliate_links")}
                if "short_url" not in pa_cols:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE promo_affiliate_links ADD COLUMN short_url TEXT"))
                    logger.info("SQLite: added promo_affiliate_links.short_url (dev migration)")
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
            if "loot_bot_settings" in inspector.get_table_names():
                lb_cols = {c["name"] for c in inspector.get_columns("loot_bot_settings")}
                with engine.begin() as conn:
                    for col, ddl in (
                        ("aof_group_chat_id", "BIGINT"),
                        ("aof_group_message_thread_id", "INTEGER"),
                        ("daily_promo_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
                        ("daily_promo_hour_utc", "INTEGER"),
                        ("daily_promo_intro_html", "TEXT"),
                        ("buffer_mirror_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
                        ("buffer_publish_now", "BOOLEAN NOT NULL DEFAULT 0"),
                        ("buffer_x_queue_json", "TEXT"),
                    ):
                        if col not in lb_cols:
                            conn.execute(text(f"ALTER TABLE loot_bot_settings ADD COLUMN {col} {ddl}"))
                            logger.info("SQLite: added loot_bot_settings.%s (dev migration)", col)
            if "loot_player_stats" in inspector.get_table_names():
                ps_cols = {c["name"] for c in inspector.get_columns("loot_player_stats")}
                if "free_pulls_used" not in ps_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE loot_player_stats ADD COLUMN free_pulls_used INTEGER NOT NULL DEFAULT 0"
                            )
                        )
                    logger.info("SQLite: added loot_player_stats.free_pulls_used (dev migration)")
        except Exception:
            logger.exception("SQLite column patch failed; run: cd backend && alembic upgrade head")
    else:
        logger.info(
            "Postgres (or non-SQLite): tables are not auto-created here. "
            "If API returns UndefinedTable, run: cd backend && python -m alembic upgrade head"
        )
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS payment_bot_settings ("
                        "id INTEGER PRIMARY KEY, "
                        "main_menu_json TEXT, "
                        "welcome_html TEXT, "
                        "loot_intro_html TEXT, "
                        "subscribe_title_main VARCHAR(128), "
                        "subscribe_title_loot VARCHAR(128), "
                        "subscription_catalog_columns INTEGER, "
                        "min_subscription_stars INTEGER, "
                        "runtime_adapter VARCHAR(32), "
                        "runtime_cmd_start TEXT, "
                        "runtime_cmd_stop TEXT, "
                        "runtime_cmd_restart TEXT, "
                        "runtime_cmd_reload TEXT, "
                        "runtime_cmd_status TEXT, "
                        "video_finder_enabled INTEGER, "
                        "video_finder_sources_json TEXT, "
                        "video_finder_max_links_per_source INTEGER)"
                    )
                )
            logger.info("Startup: ensured payment_bot_settings table exists")
            inspector = inspect(engine)
            if "payment_bot_settings" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("payment_bot_settings")}
                with engine.begin() as conn:
                    if "runtime_adapter" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_adapter VARCHAR(32)"))
                    if "runtime_cmd_start" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_start TEXT"))
                    if "runtime_cmd_stop" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_stop TEXT"))
                    if "runtime_cmd_restart" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_restart TEXT"))
                    if "runtime_cmd_reload" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_reload TEXT"))
                    if "runtime_cmd_status" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN runtime_cmd_status TEXT"))
                    if "video_finder_enabled" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN video_finder_enabled INTEGER"))
                    if "video_finder_sources_json" not in cols:
                        conn.execute(text("ALTER TABLE payment_bot_settings ADD COLUMN video_finder_sources_json TEXT"))
                    if "video_finder_max_links_per_source" not in cols:
                        conn.execute(
                            text(
                                "ALTER TABLE payment_bot_settings ADD COLUMN video_finder_max_links_per_source INTEGER"
                            )
                        )
                    if "macro_search_custom_sources_json" not in cols:
                        conn.execute(
                            text("ALTER TABLE payment_bot_settings ADD COLUMN macro_search_custom_sources_json TEXT")
                        )
                    if "macro_search_disabled_json" not in cols:
                        conn.execute(
                            text("ALTER TABLE payment_bot_settings ADD COLUMN macro_search_disabled_json TEXT")
                        )
        except Exception:
            logger.exception("Startup: failed to ensure payment_bot_settings table")
        # Alembic 044 — many deployments pull code before running upgrade head.
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS promo_affiliate_links (
                            id SERIAL PRIMARY KEY,
                            label VARCHAR(512) NOT NULL,
                            url TEXT NOT NULL,
                            short_url TEXT,
                            payout_kind VARCHAR(16) NOT NULL DEFAULT 'other',
                            payout_detail VARCHAR(64),
                            priority_tier INTEGER NOT NULL DEFAULT 10,
                            expires_at TIMESTAMP WITHOUT TIME ZONE,
                            active BOOLEAN NOT NULL DEFAULT TRUE,
                            created_at TIMESTAMP WITHOUT TIME ZONE
                        )
                        """
                    )
                )
            logger.info("Startup: ensured promo_affiliate_links table exists (PostgreSQL)")
        except Exception:
            logger.exception(
                "Startup: failed to ensure promo_affiliate_links — run: cd backend && python -m alembic upgrade head"
            )
        try:
            inspector = inspect(engine)
            if "promo_affiliate_links" in inspector.get_table_names():
                pa_cols = {c["name"] for c in inspector.get_columns("promo_affiliate_links")}
                if "short_url" not in pa_cols:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE promo_affiliate_links ADD COLUMN short_url TEXT"))
                    logger.info("PostgreSQL: added promo_affiliate_links.short_url (startup migration)")
        except Exception:
            logger.exception("Startup: failed to ensure promo_affiliate_links.short_url")
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
                if "route_match_tag_slugs" not in cp_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE content_pools ADD COLUMN route_match_tag_slugs VARCHAR(512)"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added content_pools.route_match_tag_slugs (startup migration)"
                    )
                if "route_priority" not in cp_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE content_pools ADD COLUMN route_priority INTEGER NOT NULL DEFAULT 100"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added content_pools.route_priority (startup migration)"
                    )
                if "route_nsfw_tiers" not in cp_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE content_pools ADD COLUMN route_nsfw_tiers VARCHAR(128)"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added content_pools.route_nsfw_tiers (startup migration)"
                    )
        except Exception:
            logger.exception(
                "PostgreSQL: could not add content_pools columns — run: "
                "cd backend && alembic upgrade head"
            )
        try:
            inspector = inspect(engine)
            if "media" in inspector.get_table_names():
                m_cols = {c["name"] for c in inspector.get_columns("media")}
                if "nsfw_tier" not in m_cols:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE media ADD COLUMN nsfw_tier VARCHAR(16)"))
                    logger.info("PostgreSQL: added media.nsfw_tier (startup migration)")
                if "classification_json" not in m_cols:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE media ADD COLUMN classification_json TEXT"))
                    logger.info(
                        "PostgreSQL: added media.classification_json (startup migration)"
                    )
        except Exception:
            logger.exception(
                "PostgreSQL: could not add media classification columns — run: "
                "cd backend && alembic upgrade head"
            )
        try:
            inspector = inspect(engine)
            if "subscription_plans" in inspector.get_table_names():
                sp_cols = {c["name"] for c in inspector.get_columns("subscription_plans")}
                if "bot_section" not in sp_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE subscription_plans ADD COLUMN bot_section VARCHAR(32) NOT NULL DEFAULT 'main'"
                            )
                        )
                    logger.info("PostgreSQL: added subscription_plans.bot_section (startup migration)")
        except Exception:
            logger.exception(
                "PostgreSQL: could not add subscription_plans.bot_section — run: "
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
                if "campaign_group_id" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN campaign_group_id VARCHAR(36)"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.campaign_group_id (startup migration)"
                    )
                if "send_failure_streak" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE scheduled_text_posts ADD COLUMN send_failure_streak INTEGER")
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.send_failure_streak (startup migration)"
                    )
                if "posting_auto_paused_at" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN posting_auto_paused_at TIMESTAMP"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.posting_auto_paused_at (startup migration)"
                    )
                if "posting_auto_pause_reason" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN posting_auto_pause_reason VARCHAR(512)"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.posting_auto_pause_reason (startup migration)"
                    )
                if "campaign_random_channel" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN campaign_random_channel BOOLEAN NOT NULL DEFAULT FALSE"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.campaign_random_channel (startup migration)"
                    )
                if "pool_collective_random" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN pool_collective_random BOOLEAN NOT NULL DEFAULT FALSE"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.pool_collective_random (startup migration)"
                    )
                if "buffer_mirror_enabled" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN buffer_mirror_enabled BOOLEAN NOT NULL DEFAULT FALSE"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.buffer_mirror_enabled (startup migration)"
                    )
                if "buffer_x_queue_json" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE scheduled_text_posts ADD COLUMN buffer_x_queue_json TEXT")
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.buffer_x_queue_json (startup migration)"
                    )
                if "buffer_publish_now" not in st_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE scheduled_text_posts ADD COLUMN buffer_publish_now BOOLEAN NOT NULL DEFAULT FALSE"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added scheduled_text_posts.buffer_publish_now (startup migration)"
                    )
                for col, ddl in (
                    ("caption_llm_rewrite_enabled", "BOOLEAN NOT NULL DEFAULT FALSE"),
                    ("caption_llm_rewrite_mode", "VARCHAR(16)"),
                    ("caption_llm_rewrite_interval", "INTEGER"),
                    ("caption_llm_rewrite_probability", "DOUBLE PRECISION"),
                    ("caption_llm_send_count", "INTEGER NOT NULL DEFAULT 0"),
                    ("last_sent_caption_html", "TEXT"),
                ):
                    if col not in st_cols:
                        with engine.begin() as conn:
                            conn.execute(
                                text(f"ALTER TABLE scheduled_text_posts ADD COLUMN {col} {ddl}")
                            )
                        logger.info(
                            "PostgreSQL: added scheduled_text_posts.%s (startup migration)", col
                        )
            if "listening_relay_settings" in inspector.get_table_names():
                lr_cols = {c["name"] for c in inspector.get_columns("listening_relay_settings")}
                if "message_template_variations" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN message_template_variations TEXT"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.message_template_variations (startup migration)"
                    )
                if "message_template_rotation_index" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN message_template_rotation_index INTEGER"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.message_template_rotation_index (startup migration)"
                    )
                if "message_footer_html" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE listening_relay_settings ADD COLUMN message_footer_html TEXT")
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.message_footer_html (startup migration)"
                    )
                if "message_footer_variations" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN message_footer_variations TEXT"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.message_footer_variations (startup migration)"
                    )
                if "message_copy_block_variations" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN message_copy_block_variations TEXT"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.message_copy_block_variations (startup migration)"
                    )
                if "buffer_relay_enabled" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_enabled BOOLEAN NOT NULL DEFAULT FALSE"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.buffer_relay_enabled (startup migration)"
                    )
                if "buffer_relay_min_interval_minutes" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_min_interval_minutes INTEGER NOT NULL DEFAULT 360"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.buffer_relay_min_interval_minutes (startup migration)"
                    )
                if "buffer_relay_max_per_day_utc" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_max_per_day_utc INTEGER NOT NULL DEFAULT 5"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.buffer_relay_max_per_day_utc (startup migration)"
                    )
                if "buffer_relay_utc_day" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_utc_day VARCHAR(10)"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.buffer_relay_utc_day (startup migration)"
                    )
                if "buffer_relay_posts_today" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_posts_today INTEGER NOT NULL DEFAULT 0"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.buffer_relay_posts_today (startup migration)"
                    )
                if "buffer_relay_last_post_at" not in lr_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE listening_relay_settings ADD COLUMN buffer_relay_last_post_at TIMESTAMP"
                            )
                        )
                    logger.info(
                        "PostgreSQL: added listening_relay_settings.buffer_relay_last_post_at (startup migration)"
                    )
                for col, ddl in (
                    ("template_rotation_mode", "VARCHAR(16) NOT NULL DEFAULT 'sequential'"),
                    ("message_slot_extras_json", "TEXT"),
                    ("ascii_art_enabled", "BOOLEAN NOT NULL DEFAULT FALSE"),
                    ("ascii_art_min_interval", "INTEGER NOT NULL DEFAULT 3"),
                    ("ascii_art_max_interval", "INTEGER NOT NULL DEFAULT 6"),
                    ("ascii_art_scrobble_counter", "INTEGER NOT NULL DEFAULT 0"),
                    ("ascii_art_next_threshold", "INTEGER"),
                    ("ascii_art_library_json", "TEXT"),
                    ("tryptych_enabled", "BOOLEAN NOT NULL DEFAULT FALSE"),
                    ("tryptych_on_ascii_beat", "BOOLEAN NOT NULL DEFAULT TRUE"),
                ):
                    if col not in lr_cols:
                        with engine.begin() as conn:
                            conn.execute(
                                text(f"ALTER TABLE listening_relay_settings ADD COLUMN {col} {ddl}")
                            )
                        logger.info(
                            "PostgreSQL: added listening_relay_settings.%s (startup migration)",
                            col,
                        )
        except Exception:
            logger.exception(
                "PostgreSQL: could not add scheduled_text_posts / listening_relay_settings columns — run: "
                "cd backend && alembic upgrade head"
            )

        try:
            from sqlalchemy import inspect as sa_inspect

            insp = sa_inspect(engine)
            if "import_jobs" in insp.get_table_names():
                ij_cols = {c["name"] for c in insp.get_columns("import_jobs")}
                if "job_kind" not in ij_cols:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE import_jobs ADD COLUMN job_kind VARCHAR(32) NOT NULL DEFAULT 'bytes'"
                            )
                        )
                    logger.info("PostgreSQL: added import_jobs.job_kind (startup migration)")
        except Exception:
            logger.exception(
                "PostgreSQL: could not add import_jobs.job_kind — run: cd backend && alembic upgrade head"
            )

    try:
        from app.database.session import SessionLocal
        from app.services.seed_aof_x_promo_defaults import seed_aof_x_promo_defaults

        db = SessionLocal()
        try:
            seed_aof_x_promo_defaults(db)
        finally:
            db.close()
    except Exception:
        logger.exception("Could not seed default AOF X promo captions (caption library / relay copy blocks)")

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
app.include_router(payment_bot_settings.router, prefix="/payment-bot-settings", tags=["payment-bot-settings"])
app.include_router(loot_bot_settings.router, prefix="/loot-bot-settings", tags=["loot-bot-settings"])
app.include_router(loot.router, prefix="/loot", tags=["loot"])
app.include_router(external_payment_orders.router, prefix="/external-payment-orders", tags=["external-payment-orders"])
app.include_router(webhooks_payment.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(subscription_plans.router, prefix="/subscription-plans", tags=["subscription-plans"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(scheduled_posts.router, prefix="/scheduled-posts", tags=["scheduled-posts"])
app.include_router(internal_launch.router, prefix="/internal", tags=["internal"])
app.include_router(watch_folder.router, prefix="/watch-folder", tags=["watch-folder"])
app.include_router(ops_focus.router)
app.include_router(ops_alerts.router)
app.include_router(link_resolver.router, prefix="/link-resolver", tags=["link-resolver"])
app.include_router(crawler.router, prefix="/crawler", tags=["crawler"])
app.include_router(jdownloader.router, prefix="/jd", tags=["jdownloader"])
app.include_router(caption_snippets.router, prefix="/caption-snippets", tags=["caption-snippets"])
app.include_router(telegram_custom_emoji.router, prefix="/telegram-custom-emoji", tags=["telegram-custom-emoji"])
app.include_router(emoji_factory.router, prefix="/emoji-factory", tags=["emoji-factory"])
app.include_router(promo_affiliate_links.router, prefix="/promo-affiliate-links", tags=["promo-affiliate-links"])
app.include_router(listening_relay_settings.router, prefix="/listening-relay-settings", tags=["listening-relay-settings"])
app.include_router(zip_bundle_settings.router, prefix="/zip-bundle-settings", tags=["zip-bundle-settings"])
app.include_router(gallery_send_promo.router, prefix="/gallery-send-promo", tags=["gallery-send-promo"])
app.include_router(watermark_settings.router, prefix="/watermark-settings", tags=["watermark-settings"])
app.include_router(extension_context_menu.router, prefix="/extension/context-menu", tags=["extension-context-menu"])
app.include_router(album_composer_drafts.router, prefix="/album-composer/drafts", tags=["album-composer-drafts"])
app.include_router(archive.router, tags=["archive"])
app.include_router(macro_search_submissions.router)
app.include_router(secretary.router, tags=["secretary"])
app.include_router(automation.router)
app.include_router(listening_relay_settings.webhook_router, tags=["listening-relay"])


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
        "crypto_auto_checkout": crypto_auto_checkout_ready(),
    }


@app.get("/health/telegram")
async def health_telegram():
    """Telethon admin session (Saved Messages / imports). Requires API_ID + logged-in admin.session."""
    from app.services.telegram_admin import check_admin_telegram_session

    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "Telegram API not configured (API_ID/API_HASH)"},
            headers={"Cache-Control": "no-store"},
        )
    body = await check_admin_telegram_session()
    status = 200 if body.get("ok") else 503
    return JSONResponse(content=body, status_code=status, headers={"Cache-Control": "no-store"})


@app.post("/telegram/open-saved")
async def telegram_open_saved():
    """
    Open Saved Messages in the user's installed Telegram desktop client (Windows tg:// handler).
    Avoids opening https://t.me/ links in the browser (e.g. Ayugram marketing pages).
    """
    import subprocess
    import sys

    from app.services.telegram_admin import check_admin_telegram_session

    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "Telegram API not configured (API_ID/API_HASH)"},
            headers={"Cache-Control": "no-store"},
        )
    body = await check_admin_telegram_session()
    if not body.get("ok"):
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": body.get("error") or "Telegram session not ready"},
            headers={"Cache-Control": "no-store"},
        )

    tg_urls: list[str] = []
    user_id = body.get("user_id")
    username = str(body.get("username") or "").strip().lstrip("@")
    if user_id is not None:
        try:
            uid = int(user_id)
            if uid > 0:
                tg_urls.append(f"tg://user?id={uid}")
        except (TypeError, ValueError):
            pass
    if username:
        tg_urls.append(f"tg://resolve?domain={username}")

    if not tg_urls:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "No Telegram user id/username from session"},
            headers={"Cache-Control": "no-store"},
        )

    last_err = None
    for url in tg_urls:
        try:
            if sys.platform == "win32":
                subprocess.Popen(["cmd", "/c", "start", "", url], close_fds=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", url], close_fds=True)
            else:
                subprocess.Popen(["xdg-open", url], close_fds=True)
            return JSONResponse(content={"ok": True, "opened": url}, headers={"Cache-Control": "no-store"})
        except OSError as e:
            last_err = str(e)

    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": last_err or "Could not launch Telegram client"},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health")
def health():
    # no-store: browsers were caching {"status":"ok"} and hiding new fields during dev
    return JSONResponse(
        content={
            "status": "ok",
            "external_payment_orders_impl": _EXTERNAL_PAY_IMPL,
            "crypto_auto_checkout": crypto_auto_checkout_ready(),
        },
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/health/system")
def health_system():
    """Infra, port conflicts, Telethon session risks, active import jobs, focus profile."""
    from app.services.system_health import collect_system_health
    from app.services.focus_profile import focus_public_snapshot

    body = collect_system_health()
    try:
        body["focus"] = focus_public_snapshot()
    except Exception:
        body["focus"] = None
    status = 200 if body.get("ok") else 503
    return JSONResponse(content=body, status_code=status, headers={"Cache-Control": "no-store"})


@app.post("/health/system/cleanup-uvicorn-orphans")
def health_cleanup_uvicorn_orphans():
    """Kill stale uvicorn --reload child processes (Windows local dev)."""
    from app.services.system_health import remediate_system_issues

    body = remediate_system_issues(["uvicorn_orphans", "api_port_duplicate"])
    return JSONResponse(content=body, headers={"Cache-Control": "no-store"})


class HealthRemediateBody(BaseModel):
    codes: list[str] | None = None


@app.post("/health/system/remediate")
def health_system_remediate(body: HealthRemediateBody | None = None):
    """
    One-click fixes for issues shown in the dashboard banner.
    Optional JSON body: { "codes": ["uvicorn_orphans", "redis_down"] } — omit to fix all current issues.
    """
    from app.services.system_health import remediate_system_issues

    codes = body.codes if body else None
    result = remediate_system_issues(codes)
    return JSONResponse(content=result, headers={"Cache-Control": "no-store"})


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

# Public bundle files (zip modifiers, pack assets) — use public base URL for Telegram clients.
_bundle_dir = ensure_bundle_dir()
app.mount(
    "/static/bundles",
    StaticFiles(directory=str(_bundle_dir)),
    name="bundle_uploads",
)

_zip_promo_dir = ensure_zip_promo_dir()
app.mount(
    "/static/zip-promo",
    StaticFiles(directory=str(_zip_promo_dir)),
    name="zip_promo_uploads",
)

_send_promo_dir = ensure_send_promo_dir()
app.mount(
    "/static/send-promo",
    StaticFiles(directory=str(_send_promo_dir)),
    name="send_promo_uploads",
)
