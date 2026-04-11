from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text

from .base import Base


class SubscriptionPlan(Base):
    """
    Shop product row: subscription access (channel/group) or future digital bundles.

    The payment bot loads plans from GET /subscription-plans/ on each /subscribe — no redeploy needed.
    """

    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)  # e.g. "AOF — 1 month"
    price_stars = Column(Integer, default=0)  # Telegram Stars (0 = hidden from Stars checkout)
    duration_days = Column(Integer, default=30)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True)  # e.g. private AOF group channel
    description = Column(Text, nullable=True)  # Shown on Telegram invoice / future catalog
    # JSON array of extra description lines; bot picks randomly with `description` for invoices / pack cards
    description_variations_json = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)  # Inactive = hidden from bot
    product_type = Column(String(32), default="subscription", nullable=False)  # subscription | bundle
    # HTTPS URL shown in /shop promo carousel (optional); kept as first of album for backward compatibility
    promo_image_url = Column(String(1024), nullable=True)
    # JSON array of up to 5 HTTPS URLs (Telegram album); invoice still uses first URL only
    promo_image_urls_json = Column(Text, nullable=True)
    # Digital pack: uploaded .zip (path = uploads/bundles/{id}.zip); original filename for Telegram send_document
    bundle_zip_original_name = Column(String(512), nullable=True)
    # Optional second zip (uploads/bundles/{id}_2.zip) for split packs over Telegram sendDocument limit
    bundle_zip2_original_name = Column(String(512), nullable=True)
    # JSON array of original filenames for all parts (order matches bundle_zip_nth_path index); supersedes legacy when set
    bundle_zip_parts_json = Column(Text, nullable=True)
    # JSON array of tbcc_tags.id values (shop catalog / hashtags on Telegram)
    plan_tag_ids_json = Column(Text, nullable=True)
