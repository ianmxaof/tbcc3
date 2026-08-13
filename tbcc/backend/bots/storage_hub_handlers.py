"""Register Storage Hub operator handlers on payment bot or album composer (remixer)."""

from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)


async def bootstrap_storage_hub_panels(bot) -> dict:
    from app.services.storage_hub_control_panels import ensure_all_hub_control_panels

    return await ensure_all_hub_control_panels(bot, force_new=True)


def register_storage_hub_handlers(app: Application, *, bot_label: str) -> None:
    """Wire /deposit, panels, Q&A controls, and auto-pipe intake for one bot."""
    from app.services.storage_topic_deposit import storage_hub_chat_id_int

    if bot_label == "payment":

        async def cmd_deposit(update, context):
            from bots.storage_hub_deposit_bot import cmd_deposit

            await cmd_deposit(update, context, bot_label="payment")

        async def cmd_depositpanel(update, context):
            from bots.storage_deposit_control_handlers import cmd_deposit_panel

            await cmd_deposit_panel(update, context)

        async def cmd_hubpanel(update, context):
            from bots.storage_hub_control_handlers import cmd_hubpanel

            await cmd_hubpanel(update, context)

        async def cmd_qapanel(update, context):
            from bots.qa_master_panel_handlers import cmd_qa_master_panel

            await cmd_qa_master_panel(update, context)

        async def cmd_intake(update, context):
            from bots.intake_control_handlers import cmd_intake

            await cmd_intake(update, context)

        async def cmd_review(update, context):
            from bots.review_control_handlers import cmd_review

            await cmd_review(update, context)

    else:

        async def cmd_deposit(update, context):
            from bots.storage_hub_deposit_bot import cmd_deposit

            await cmd_deposit(update, context, bot_label="album-composer")

        async def cmd_depositpanel(update, context):
            from bots.storage_deposit_control_handlers import cmd_deposit_panel

            await cmd_deposit_panel(update, context)

        async def cmd_hubpanel(update, context):
            from bots.storage_hub_control_handlers import cmd_hubpanel

            await cmd_hubpanel(update, context)

        async def cmd_qapanel(update, context):
            from bots.qa_master_panel_handlers import cmd_qa_master_panel

            await cmd_qa_master_panel(update, context)

        async def cmd_intake(update, context):
            from bots.intake_control_handlers import cmd_intake

            await cmd_intake(update, context)

        async def cmd_review(update, context):
            from bots.review_control_handlers import cmd_review

            await cmd_review(update, context)

    async def handle_gatekeeper_review_callback(update, context):
        from bots.gatekeeper_review_handlers import on_gatekeeper_review_callback

        await on_gatekeeper_review_callback(update, context)

    async def handle_deposit_control_callback(update, context):
        from bots.storage_deposit_control_handlers import on_deposit_control_callback

        await on_deposit_control_callback(update, context)

    async def handle_intake_control_callback(update, context):
        from bots.intake_control_handlers import on_intake_control_callback

        await on_intake_control_callback(update, context)

    async def handle_hub_lane_control_callback(update, context):
        from bots.storage_hub_control_handlers import on_hub_lane_control_callback

        await on_hub_lane_control_callback(update, context)

    async def handle_sent_cache_control_callback(update, context):
        from bots.storage_hub_control_handlers import on_sent_cache_control_callback

        await on_sent_cache_control_callback(update, context)

    async def handle_qa_master_panel_callback(update, context):
        from bots.qa_master_panel_handlers import on_qa_master_panel_callback

        await on_qa_master_panel_callback(update, context)

    app.add_handler(CommandHandler("deposit", cmd_deposit))
    app.add_handler(CommandHandler("depositpanel", cmd_depositpanel))
    app.add_handler(CommandHandler("hubpanel", cmd_hubpanel))
    app.add_handler(CommandHandler("qapanel", cmd_qapanel))
    app.add_handler(CommandHandler("intake", cmd_intake))
    app.add_handler(CommandHandler("review", cmd_review))

    for pattern, handler in (
        (r"^/deposit(@\w+)?(?:\s|$)", cmd_deposit),
        (r"^/depositpanel(@\w+)?(?:\s|$)", cmd_depositpanel),
        (r"^/hubpanel(@\w+)?(?:\s|$)", cmd_hubpanel),
        (r"^/qapanel(@\w+)?(?:\s|$)", cmd_qapanel),
        (r"^/review(@\w+)?(?:\s|$)", cmd_review),
        (r"^/intake(@\w+)?(?:\s|$)", cmd_intake),
    ):
        app.add_handler(
            MessageHandler(filters.UpdateType.CHANNEL_POST & filters.Regex(pattern), handler)
        )

    from bots.storage_hub_auto_pipe_handlers import on_storage_hub_lane_media_post

    hub_id = storage_hub_chat_id_int()
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST
            & filters.Chat(chat_id=hub_id)
            & (
                filters.PHOTO
                | filters.VIDEO
                | filters.Document.VIDEO
                | filters.ATTACHMENT
            ),
            on_storage_hub_lane_media_post,
        )
    )

    app.add_handler(CallbackQueryHandler(handle_gatekeeper_review_callback, pattern=r"^gk:[atr]:"))
    app.add_handler(CallbackQueryHandler(handle_gatekeeper_review_callback, pattern=r"^gk:b[ar]:"))
    app.add_handler(CallbackQueryHandler(handle_gatekeeper_review_callback, pattern=r"^gk:p:"))
    app.add_handler(CallbackQueryHandler(handle_intake_control_callback, pattern=r"^intake:"))
    app.add_handler(CallbackQueryHandler(handle_hub_lane_control_callback, pattern=r"^hubctl:"))
    app.add_handler(CallbackQueryHandler(handle_sent_cache_control_callback, pattern=r"^sctl:"))
    app.add_handler(CallbackQueryHandler(handle_deposit_control_callback, pattern=r"^depctl:"))
    app.add_handler(CallbackQueryHandler(handle_qa_master_panel_callback, pattern=r"^qmp:"))

    logger.info("Storage Hub handlers registered on %s bot", bot_label)
