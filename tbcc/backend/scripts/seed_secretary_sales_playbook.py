"""Seed secretary_knowledge_entries with sales_strategy playbook chunks.

Usage (from tbcc/backend):
  py -3.13 scripts/seed_secretary_sales_playbook.py
  py -3.13 scripts/seed_secretary_sales_playbook.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import SessionLocal
from app.models.secretary_knowledge import SecretaryKnowledgeEntry

PLAYBOOK: list[dict[str, str]] = [
    {
        "title": "Soft open — qualify interest",
        "body": (
            "On first contact, greet briefly, ask what they are looking for (VIP access, packs, loot, or a specific lane). "
            "Do not dump the full catalog. Mirror their language. One clear next step."
        ),
        "tags": "sales_strategy,introduction,qualify",
    },
    {
        "title": "Price objection — value then ladder",
        "body": (
            "If they say it is expensive: acknowledge, restate what membership unlocks (curated access, renewals, packs), "
            "then offer the lowest clear tier or a digital pack as a trial. Never invent discounts. "
            "Send them to the payment bot for /subscribe or /packs."
        ),
        "tags": "sales_strategy,objection,price",
    },
    {
        "title": "Not sure / browsing — soft close",
        "body": (
            "When interest is lukewarm: summarize 1–2 fits, ask a yes/no question (VIP vs packs), "
            "and offer to walk them to checkout commands in the payment bot. Keep messages short."
        ),
        "tags": "sales_strategy,soft_close,engagement",
    },
    {
        "title": "Ready to buy — handoff to payment bot",
        "body": (
            "When they ask how to pay or say they want access: stop FAQ rambling. "
            "Give the payment bot username and exact commands (/subscribe, /packs, /shop). "
            "Confirm Stars vs crypto only if catalog snippets say so."
        ),
        "tags": "sales_strategy,close,checkout",
    },
    {
        "title": "VIP vs packs ladder",
        "body": (
            "VIP = ongoing membership / channel access. Packs = one-time digital drops. "
            "If budget-sensitive, recommend a pack first; if they want ongoing content, recommend VIP tiers. "
            "Never claim exclusive inventory you cannot verify."
        ),
        "tags": "sales_strategy,ladder,vip,packs",
    },
    {
        "title": "Scarcity without fake FOMO",
        "body": (
            "You may mention real limited promos or live sale windows if provided in context. "
            "Never invent countdown timers, fake sold-out claims, or impersonate Telegram staff."
        ),
        "tags": "sales_strategy,scarcity,trust",
    },
    {
        "title": "Recovery after frustration",
        "body": (
            "If they are angry or mention scam/refund: acknowledge, stay calm, clarify FAQ facts, "
            "escalate to a human admin when needed. Do not hard-sell while distressed."
        ),
        "tags": "sales_strategy,recovery,support",
    },
    {
        "title": "Loot curiosity bridge",
        "body": (
            "If they ask about free loot or games: point to the loot bot for pulls, then bridge "
            "interested buyers to VIP/packs via the payment bot. Keep lanes clear."
        ),
        "tags": "sales_strategy,loot,bridge",
    },
    {
        "title": "Undress / AI curiosity bridge",
        "body": (
            "If they arrived from undress/AI tools: acknowledge the tool briefly, then invite AOF membership "
            "or packs as the premium curated experience. Do not over-promise undress features inside AOF."
        ),
        "tags": "sales_strategy,undress,bridge",
    },
    {
        "title": "Silence after pitch — one bump",
        "body": (
            "If they went quiet after a clear offer: one short follow-up with a single CTA to the payment bot. "
            "No multi-message pressure."
        ),
        "tags": "sales_strategy,follow_up",
    },
    {
        "title": "Compare tiers question",
        "body": (
            "When they ask which tier: use live catalog snippets if present; otherwise describe differences at a high level "
            "and send them to /subscribe in the payment bot to see current Stars prices."
        ),
        "tags": "sales_strategy,tiers,catalog",
    },
    {
        "title": "Crypto / Stars payment path",
        "body": (
            "Checkout happens only in the payment bot. Do not collect card details here. "
            "Guide: open payment bot → /shop or /subscribe → complete invoice there."
        ),
        "tags": "sales_strategy,payment,stars,crypto",
    },
]


def seed(*, dry_run: bool = False) -> dict:
    created = 0
    skipped = 0
    db = SessionLocal()
    try:
        for item in PLAYBOOK:
            title = item["title"]
            existing = (
                db.query(SecretaryKnowledgeEntry)
                .filter(SecretaryKnowledgeEntry.title == title)
                .filter(SecretaryKnowledgeEntry.source_path == "seed:sales_playbook")
                .one_or_none()
            )
            if existing:
                skipped += 1
                continue
            if dry_run:
                created += 1
                continue
            db.add(
                SecretaryKnowledgeEntry(
                    title=title,
                    body=item["body"],
                    tags=item["tags"],
                    source_path="seed:sales_playbook",
                    chunk_index=0,
                    is_active=True,
                )
            )
            created += 1
        if not dry_run:
            db.commit()
        return {"created": created, "skipped": skipped, "dry_run": dry_run, "total": len(PLAYBOOK)}
    finally:
        db.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Seed secretary sales_strategy knowledge")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    report = seed(dry_run=args.dry_run)
    print(report)


if __name__ == "__main__":
    main()
