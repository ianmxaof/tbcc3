from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.services.subscription_metrics import active_subscription_subscriber_count
from app.services.bundle_parts import bundle_parts_for_api
from app.services.payment_admin_notify import notify_sale_fulfilled

router = APIRouter()


def _build_subscription_api_result(
    db: Session,
    sub: Subscription,
    plan: SubscriptionPlan,
    *,
    referrer_rewarded: bool,
    referrer_id_for_response: int | None,
) -> dict:
    """JSON shape returned to the payment bot after create or idempotent replay."""
    is_bundle = (plan.product_type or "").lower() == "bundle"
    result = orm_to_dict(sub)
    result["referrer_rewarded"] = referrer_rewarded
    result["plan_product_type"] = plan.product_type
    result["plan_description"] = plan.description
    if referrer_id_for_response and not is_bundle:
        result["referrer_id"] = referrer_id_for_response
    if plan.channel_id:
        from app.models.channel import Channel
        from app.services.aof_vip_fulfillment import fulfillment_invite_link

        invite = fulfillment_invite_link(db, plan)
        if invite:
            result["invite_link"] = invite
        else:
            ch = db.query(Channel).filter(Channel.id == plan.channel_id).first()
            if ch and ch.invite_link:
                result["invite_link"] = ch.invite_link
    if is_bundle:
        parts = bundle_parts_for_api(plan)
        n = len(parts)
        result["bundle_zip_available"] = n > 0
        result["bundle_zip_parts"] = parts
        result["bundle_zip_part_count"] = n
        result["bundle_zip1_available"] = n >= 1
        result["bundle_zip2_available"] = n >= 2
        result["bundle_zip_original_name"] = plan.bundle_zip_original_name
        result["bundle_zip2_original_name"] = plan.bundle_zip2_original_name
    prog = _get_milestone_progress(db)
    if prog:
        result["milestone_progress"] = prog["message"]
    return result


def _grant_referrer_reward(db: Session, referrer_id: int, reward_days: int, plan_id: int) -> None:
    """Extend referrer's active subscription by reward_days, or create bonus + grant channel access."""
    active = (
        db.query(Subscription)
        .filter(
            Subscription.telegram_user_id == referrer_id,
            Subscription.status == "active",
        )
        .order_by(Subscription.expires_at.desc())
        .first()
    )
    if active and active.expires_at:
        active.expires_at = active.expires_at + timedelta(days=reward_days)
    else:
        bonus_expires = datetime.utcnow() + timedelta(days=reward_days)
        bonus = Subscription(
            telegram_user_id=referrer_id,
            plan_id=plan_id,
            plan="Referral bonus",
            status="active",
            expires_at=bonus_expires,
            payment_method="referral",
            referrer_id=None,
        )
        db.add(bonus)
        from app.workers.grant_access_worker import grant_channel_access
        grant_channel_access.delay(referrer_id, plan_id)


def subscription_create_from_payload(data: dict, db: Session) -> dict:
    """
    Create a subscription / fulfill purchase (Stars, manual external pay, etc.).
    Used by POST /subscriptions/ and external-payment mark-paid.
    """
    telegram_user_id = data.get("telegram_user_id")
    plan_id = data.get("plan_id")
    payment_method = data.get("payment_method", "stars")
    charge_id = (data.get("telegram_payment_charge_id") or "").strip() or None

    if not telegram_user_id or not plan_id:
        return {"error": "telegram_user_id and plan_id required"}

    # Idempotent Stars: Telegram may retry successful_payment; same charge_id = same row
    if charge_id:
        existing = (
            db.query(Subscription)
            .filter(Subscription.telegram_payment_charge_id == charge_id)
            .first()
        )
        if existing:
            plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == existing.plan_id).first()
            if not plan:
                return {"error": "Plan not found for subscription"}
            result = _build_subscription_api_result(
                db,
                existing,
                plan,
                referrer_rewarded=False,
                referrer_id_for_response=existing.referrer_id
                if (plan.product_type or "").lower() != "bundle"
                else None,
            )
            result["fulfillment_replay"] = True
            return result

    referrer_id = data.get("referrer_id")

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if not plan:
        return {"error": "Plan not found"}

    from app.services.vip_intro_eligibility import assert_vip_intro_allowed

    intro_err = assert_vip_intro_allowed(
        db, telegram_user_id=int(telegram_user_id), plan=plan
    )
    if intro_err:
        return {"error": intro_err}

    is_bundle = (plan.product_type or "").lower() == "bundle"

    # Bundle purchases: no referral rewards; keep referral tracking for a future subscription
    if is_bundle:
        referrer_id = None
    elif referrer_id is None:
        from app.models.referral_tracking import ReferralTracking

        rt = (
            db.query(ReferralTracking)
            .filter(ReferralTracking.referred_user_id == int(telegram_user_id))
            .first()
        )
        if rt:
            referrer_id = rt.referrer_user_id
            db.delete(rt)

    if is_bundle and (plan.duration_days or 0) <= 0:
        expires_at = None
    else:
        expires_at = datetime.utcnow() + timedelta(days=max(plan.duration_days or 1, 1))

    sub = Subscription(
        telegram_user_id=int(telegram_user_id),
        plan_id=plan.id,
        plan=plan.name,
        status="active",
        expires_at=expires_at,
        payment_method=payment_method,
        amount_stars=plan.price_stars,
        referrer_id=int(referrer_id) if referrer_id else None,
        telegram_payment_charge_id=charge_id,
    )
    try:
        from app.services.traffic_attribution import resolve_attribution_for_user

        attr = resolve_attribution_for_user(db, int(telegram_user_id))
        sub.traffic_source_ref = attr.get("traffic_source_ref")
        sub.traffic_entry_payload = attr.get("traffic_entry_payload")
    except Exception:
        pass
    db.add(sub)
    db.commit()
    db.refresh(sub)

    try:
        from app.services.income_ledger import record_subscription_income

        record_subscription_income(
            db,
            sub,
            plan,
            payment_method=payment_method,
            charge_id=charge_id,
            amount_usd_override=(
                float(data["income_amount_usd"])
                if data.get("income_amount_usd") is not None
                else None
            ),
            external_ref=(str(data.get("reference_code") or "").strip() or None),
        )
    except Exception:
        pass

    try:
        from app.services.growth_attribution import EVENT_SUBSCRIPTION_CREATED, record_growth_attribution

        record_growth_attribution(
            db,
            event_type=EVENT_SUBSCRIPTION_CREATED,
            telegram_user_id=int(telegram_user_id),
            amount_stars=int(plan.price_stars or 0),
            plan_id=int(plan.id),
            channel_id=int(plan.channel_id) if plan.channel_id else None,
            traffic_source_ref=sub.traffic_source_ref,
            start_payload_raw=sub.traffic_entry_payload,
            extra={"payment_method": payment_method},
        )
        db.commit()
    except Exception:
        pass

    # Enqueue task to add user to channel (premium group or pack delivery channel)
    if plan.channel_id:
        from app.workers.grant_access_worker import grant_channel_access

        grant_channel_access.delay(int(telegram_user_id), plan_id)

    # Grant referrer reward only for subscription products
    reward_days = int(data.get("referral_reward_days", 7))
    if not is_bundle and referrer_id and reward_days > 0:
        _grant_referrer_reward(db, int(referrer_id), reward_days, plan_id)
        db.commit()

    perk_result = None
    if not is_bundle:
        _check_milestones(db)
        from app.workers.milestone_worker import broadcast_progress

        broadcast_progress.delay()
        try:
            from app.services.aof_vip_perks import grant_vip_subscription_perks

            perk_result = grant_vip_subscription_perks(
                db,
                int(telegram_user_id),
                int(plan.id),
                charge_id=charge_id,
            )
        except Exception:
            perk_result = None
        if active_subscription_subscriber_count(db) == 1:
            from app.services.aof_network_liveness import queue_first_subscription_celebration

            try:
                queue_first_subscription_celebration(db)
            except Exception:
                pass  # never block fulfillment on celebration copy

    notify_sale_fulfilled(
        telegram_user_id=int(telegram_user_id),
        plan_name=str(plan.name or "Product"),
        product_type=str(plan.product_type or ""),
        payment_method=str(payment_method or ""),
        amount_stars=int(plan.price_stars or 0),
        bot_section=str(getattr(plan, "bot_section", None) or ""),
        plan_id=int(plan.id),
        external_order_id=int(data["external_order_id"]) if data.get("external_order_id") else None,
        reference_code=(str(data.get("reference_code") or "").strip() or None),
    )

    if not is_bundle:
        try:
            from app.workers.vip_welcome_worker import send_subscription_welcome_dm

            send_subscription_welcome_dm.delay(
                int(telegram_user_id),
                int(plan_id),
                charge_id,
                str(payment_method or ""),
            )
        except Exception:
            pass

    result = _build_subscription_api_result(
        db,
        sub,
        plan,
        referrer_rewarded=bool(referrer_id) and not is_bundle,
        referrer_id_for_response=int(referrer_id) if referrer_id and not is_bundle else None,
    )
    if not is_bundle and perk_result:
        result["vip_perks"] = perk_result

    try:
        from app.services.fulfillment_entitlement import record_fulfillment_entitlement

        record_fulfillment_entitlement(
            db,
            telegram_user_id=int(telegram_user_id),
            plan=plan,
            subscription_id=int(sub.id),
            invite_url=result.get("invite_link"),
            payment_method=str(payment_method or ""),
        )
    except Exception:
        pass

    buyer_email = (data.get("buyer_email") or data.get("email") or "").strip() or None
    if buyer_email:
        try:
            from app.services.kit_buyer_capture import capture_buyer_email_on_purchase

            capture_buyer_email_on_purchase(
                buyer_email,
                telegram_user_id=int(telegram_user_id),
                plan_name=str(plan.name or ""),
                payment_method=str(payment_method or ""),
                product_type=str(plan.product_type or ""),
            )
        except Exception:
            pass

    return result


@router.post("/")
def create_subscription(data: dict = Body(...), db: Session = Depends(get_db)):
    """Create a subscription (called by payment bot on successful payment)."""
    return subscription_create_from_payload(data, db)


def _get_milestone_progress(db: Session) -> dict | None:
    """Progress row for subscription API responses (message matches landing bulletin / FOMO)."""
    from app.services.growth_promo import milestone_progress_api_dict

    return milestone_progress_api_dict(db)


def _check_milestones(db: Session) -> None:
    """If active subscriber count crossed a milestone, trigger mass-extend + broadcast."""
    from app.models.subscription_milestone import SubscriptionMilestone

    active_count = active_subscription_subscriber_count(db)

    # Find milestones we just crossed (not yet triggered)
    pending = (
        db.query(SubscriptionMilestone)
        .filter(
            SubscriptionMilestone.triggered_at.is_(None),
            SubscriptionMilestone.threshold <= active_count,
        )
        .order_by(SubscriptionMilestone.threshold.asc())
        .all()
    )

    for m in pending:
        from app.workers.milestone_worker import process_milestone
        process_milestone.delay(m.id, m.threshold, m.reward_days)


@router.get("/milestone-progress")
def milestone_progress(db: Session = Depends(get_db)):
    """Return progress toward next milestone for 'crowdsourced FOMO' messaging."""
    from app.services.growth_promo import milestone_progress_api_dict

    return milestone_progress_api_dict(db)


@router.get("/")
def list_subscriptions(
    db: Session = Depends(get_db),
    status: str | None = None,
    telegram_user_id: int | None = None,
):
    q = db.query(Subscription)
    if status:
        q = q.filter(Subscription.status == status)
    if telegram_user_id is not None:
        q = q.filter(Subscription.telegram_user_id == telegram_user_id)
    return [orm_to_dict(s) for s in q.order_by(Subscription.expires_at.desc()).limit(200).all()]


@router.get("/{sub_id}")
def get_subscription(sub_id: int, db: Session = Depends(get_db)):
    s = db.query(Subscription).filter(Subscription.id == sub_id).first()
    if not s:
        return {"error": "Not found"}
    return orm_to_dict(s)
