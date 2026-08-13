"""
Operator sandbox — unlimited QA for hardcoded owner Telegram ids only.

Three accounts (see HARDCODED_TBCC_OPERATOR_IDS) get full product access without
Stars invoices, gates, rate limits, or pull caps. Nothing is advertised to the
public; only operator-facing bot copy mentions sandbox mode.

Real undress API credits may still burn on companion reveals — sandbox skips
*user* monetization (Stars, trials, gates), not upstream COGS.
"""

from __future__ import annotations

from app.services.tbcc_operator_ids import is_tbcc_operator, tbcc_operator_ids

# Shown only in DMs to operator ids — never in channel/group copy.
OPERATOR_SANDBOX_BADGE = "🔧 Operator QA"
OPERATOR_SANDBOX_HINT = (
    f"{OPERATOR_SANDBOX_BADGE} — unlimited sandbox (no Stars, no gate). "
    "Undress API credits still apply."
)


def is_operator_sandbox(telegram_user_id: int | None) -> bool:
    return is_tbcc_operator(telegram_user_id)


def operator_sandbox_ids() -> frozenset[int]:
    return tbcc_operator_ids()


def skip_stars_checkout(telegram_user_id: int | None) -> bool:
    """Operators never see Stars invoices or post-trial upsell."""
    return is_operator_sandbox(telegram_user_id)


def skip_companion_gate(telegram_user_id: int | None) -> bool:
    return is_operator_sandbox(telegram_user_id)


def skip_companion_rate_limit(telegram_user_id: int | None) -> bool:
    return is_operator_sandbox(telegram_user_id)


def companion_allowance_label(telegram_user_id: int) -> str:
    if is_operator_sandbox(telegram_user_id):
        return "∞"
    from app.services.companion_access import get_access

    return str(get_access(telegram_user_id).generations_remaining())


def operator_status_line(telegram_user_id: int | None) -> str | None:
    """One-line footer for /balance and /start — None for normal users."""
    if not is_operator_sandbox(telegram_user_id):
        return None
    return OPERATOR_SANDBOX_HINT
