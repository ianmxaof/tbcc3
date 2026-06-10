from sqlalchemy import Column, Integer, String, Text

from .base import Base


class PaymentBotSettings(Base):
    """
    DB overrides for payment bot runtime behavior.

    Null values mean "fall back to env/defaults" so existing deployments keep working.
    """

    __tablename__ = "payment_bot_settings"

    id = Column(Integer, primary_key=True, autoincrement=False, default=1)
    # JSON array rows: [[{label, action}, ...], ...]
    main_menu_json = Column(Text, nullable=True)
    welcome_html = Column(Text, nullable=True)
    loot_intro_html = Column(Text, nullable=True)
    subscribe_title_main = Column(String(128), nullable=True)
    subscribe_title_loot = Column(String(128), nullable=True)
    subscription_catalog_columns = Column(Integer, nullable=True)
    min_subscription_stars = Column(Integer, nullable=True)
    runtime_adapter = Column(String(32), nullable=True)  # local | command
    runtime_cmd_start = Column(Text, nullable=True)
    runtime_cmd_stop = Column(Text, nullable=True)
    runtime_cmd_restart = Column(Text, nullable=True)
    runtime_cmd_reload = Column(Text, nullable=True)
    runtime_cmd_status = Column(Text, nullable=True)
    video_finder_enabled = Column(Integer, nullable=True)  # 1/0
    video_finder_sources_json = Column(Text, nullable=True)
    video_finder_max_links_per_source = Column(Integer, nullable=True)
    # Telegram /macroaddsource — extra macro sources (extension parity); built-in JSON still loaded.
    macro_search_custom_sources_json = Column(Text, nullable=True)
    macro_search_disabled_json = Column(Text, nullable=True)  # {"site_id": false, ...}
