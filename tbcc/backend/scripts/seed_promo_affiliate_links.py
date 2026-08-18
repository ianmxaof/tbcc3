#!/usr/bin/env python3
"""Seed promo_affiliate_links with Musebox + core AOF sponsors + AI tool affiliates (idempotent by URL)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.promo_affiliate_link import PromoAffiliateLink

# Retired affiliates — deactivated on every seed run (fake / dead programs).
PURGE_LABELS = frozenset({"Carrot Wallet"})
PURGE_URL_SUBSTRINGS = ("carrotwallettgbot", "carrotwallet", "temu.com")

SEED_ITEMS: list[dict] = [
    {
        # Top cash CPA — $2 USDT per referral; lead rotation on all cash surfaces.
        "label": "Cloud Farm Wallet",
        "url": "https://t.me/CloudFarmWalletBot/cloud?startapp=7787282561",
        "payout_kind": "cpa",
        "payout_detail": "usd_cash",
        "priority_tier": 0,
        "placements": [
            "x_buffer",
            "telegram_footer",
            "links_hub",
            "links_hub_sfw",
            "loot_roll",
        ],
        "network_keys": [],
        "copy_template": "☁️ {link} — $2 USDT per referral · cloud farm",
    },
    {
        "label": "AOF VIP card checkout",
        "url": "https://aof69.gumroad.com/l/ynnulc",
        "payout_kind": "subscription",
        "payout_detail": "subscription",
        "priority_tier": 3,
        "placements": ["x_buffer", "telegram_footer", "links_hub"],
        "network_keys": [],
        "copy_template": "⭐ {link} — VIP from $6/mo · card · PayPal",
    },
    {
        "label": "Musebox AI",
        "url": "https://musebox.ai/?ref=uOg77ImI",
        "payout_kind": "revshare",
        "payout_detail": "usd_revshare",
        "priority_tier": 10,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎨 {link} — AI creative playground",
    },
    {
        "label": "AI affiliate (aftrk3)",
        "url": (
            "https://track.aftrk3.com/38df6f12-f103-452f-9386-22bba88ec8ef"
            "?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MzcsInMiOjczNSwiZSI6MTEwNTIsInAiOjMxN30="
            "&aff_token=IDAgLBMhJS8NJSE6Jw"
        ),
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 5,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🤖 {link} — AI sponsor · tap while it's live",
    },
    {
        "label": "Lucid Dreams video bot",
        "url": "https://ndfy.store/tg/bot?username=Luciddreamstobot&ref_id=7787282561",
        "payout_kind": "revshare",
        "payout_detail": "platform_credits",
        "priority_tier": 4,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll", "companion_dm"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — best video poses + free removals",
    },
    {
        "label": "Undress AI bot",
        "url": "https://nodress.site/tg/bot?username=Aifasteditbot&ref_id=7787282561",
        "payout_kind": "revshare",
        "payout_detail": "platform_credits",
        "priority_tier": 30,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai"],
        "network_keys": [],
        "copy_template": "💰 {link} — free credits",
    },
    {
        "label": "Undress umbrella ndfy Alfastedit",
        "url": "https://ndfy.space/tg/bot?username=Aifasteditbot&ref_id=7787282561",
        "payout_kind": "revshare",
        "payout_detail": "platform_credits",
        "priority_tier": 31,
        "placements": ["links_hub_ai", "telegram_footer"],
        "network_keys": ["ai"],
        "copy_template": "💰 {link} — undress credits (ndfy)",
    },
    {
        "label": "Undress umbrella nudress Okbraoff",
        "url": "https://nudress.store/tg/bot?username=Okbraoffbot&ref_id=7787282561",
        "payout_kind": "revshare",
        "payout_detail": "platform_credits",
        "priority_tier": 31,
        "placements": ["links_hub_ai"],
        "network_keys": ["ai"],
        "copy_template": "💰 {link} — undress credits (nudress.store)",
    },
    {
        "label": "Undress umbrella ndfy Teststtscr",
        "url": "https://ndfy.space/tg/bot?username=Teststtscrditsbot&ref_id=7787282561",
        "payout_kind": "revshare",
        "payout_detail": "platform_credits",
        "priority_tier": 32,
        "placements": ["links_hub_ai"],
        "network_keys": ["ai"],
        "copy_template": "💰 {link} — easy AI photo credits",
    },
    {
        "label": "DrawAI",
        "url": "https://t.me/drawai_0_bot?start=7787282561",
        "payout_kind": "revshare",
        "payout_detail": "revshare_unknown",
        "priority_tier": 20,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — photo to motion",
    },
    {
        "label": "BotyNude",
        "url": "https://botynude.com/ref/39Z9HHK3",
        "payout_kind": "revshare",
        "payout_detail": "usd_revshare",
        "priority_tier": 11,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "💰 {link} — 2 free coins per join",
    },
    {
        "label": "MotionMuse",
        "url": "https://motionmuse.ai/r/wi9rtg3l",
        "payout_kind": "revshare",
        "payout_detail": "platform_credits",
        "priority_tier": 32,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai"],
        "copy_template": "🎬 {link} — invite friends, earn credits",
    },
    {
        "label": "BangBros PPS",
        "url": "https://landing.bangbrosnetwork.com/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MTMwLCJzIjo2OTMsImUiOjEwNjczLCJwIjoxMX0=",
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 1,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["milf", "taboo", "big_tits"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Reality Kings PPS",
        "url": "https://landing.rk.com/tgp1/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MjAsInMiOjM1OCwiZSI6ODAzNCwicCI6MTF9",
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 3,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["milf", "voyeur"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Spicevids PPS",
        "url": "https://landing.spicevids.com/affiliates/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MTIwLCJzIjo2ODAsImUiOjEwNDMyLCJwIjoxMX0=",
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 4,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["goon", "bop"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Brazzers PPS",
        "url": "https://landing.brazzersnetwork.com/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MTQsInMiOjkwLCJlIjo4ODAzLCJwIjoxMX0=",
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 2,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["milf", "big_tits", "taboo"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Babes Network PPS",
        "url": "https://landing.babesnetwork.com/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MTYsInMiOjE2NiwiZSI6ODk5NywicCI6MTF9",
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 5,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["milf", "main"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Men Network PPS",
        "url": "https://landing.mennetwork.com/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MjIsInMiOjU0MiwiZSI6OTA5NCwicCI6MTF9",
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 6,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["bop"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Erito Network PPS",
        "url": "https://landing.eritonetwork.com/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MjYsInMiOjIzMCwiZSI6ODk5NSwicCI6MTF9",
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 7,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["abg", "ai"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Bromo Network PPS",
        "url": "https://landing.bromonetwork.com/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MjMsInMiOjUzNCwiZSI6OTA4OCwicCI6MTF9",
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 8,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["bop", "goon"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Sean Cody PPS",
        "url": "https://landing.seancodynetwork.com/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MjcsInMiOjUzOCwiZSI6OTA5NiwicCI6MTF9",
        "payout_kind": "pps",
        "payout_detail": "usd_cash",
        "priority_tier": 9,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["bop"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Nutaku — Lust Goddess",
        "url": "https://network.nutaku.net/images/lp/lust-goddess/video/1/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MSwicyI6MSwiZSI6MTA5MDMsInAiOjJ9",
        "payout_kind": "cpa",
        "payout_detail": "usd_cash",
        "priority_tier": 12,
        "placements": ["x_buffer", "links_hub"],
        "network_keys": [],
        "copy_template": "🎮 {link}",
    },
    # --- Infrastructure / ops (links_hub PARTNERS lane — not links_hub_ai) ---
    {
        "label": "Pulsed Media seedbox",
        "url": "https://pulsedmedia.com/clients/aff.php?aff=10812",
        "payout_kind": "other",
        "priority_tier": 45,
        "placements": ["manual_only", "links_hub", "links_hub_sfw"],
        "network_keys": [],
        "copy_template": "📦 {link} — remote storage & fast cloud transfers",
    },
    {
        "label": "Microsoft Rewards (Bing)",
        "url": "https://rewards.bing.com/welcome?rh=LjD_QLCQ3xc&ref=rafsrchae",
        "payout_kind": "referral",
        "payout_detail": "referral_points",
        "priority_tier": 46,
        "placements": ["manual_only", "links_hub", "x_buffer", "links_hub_sfw"],
        "network_keys": ["main"],
        "copy_template": "🔎 {link} — earn gift cards searching with Bing",
    },
    {
        "label": "Cursor referral",
        "url": "https://cursor.com/referral?code=WKMSQ8BYPM1O",
        "payout_kind": "other",
        "payout_detail": "referral_credits",
        "priority_tier": 50,
        "placements": ["manual_only", "links_hub_sfw"],
        "network_keys": [],
        "copy_template": "🛠 {link} — Cursor AI editor",
    },
    {
        "label": "Claude referral",
        "url": "https://claude.ai/referral/ve9d3Ki_QA",
        "payout_kind": "other",
        "payout_detail": "referral_credits",
        "priority_tier": 51,
        "placements": ["manual_only", "links_hub_sfw"],
        "network_keys": [],
        "copy_template": "🛠 {link} — Claude AI assistant",
    },
    {
        "label": "Abliteration.ai",
        "url": "https://abliteration.ai/sign-up?referral_code=ref_5zTlwMOPEFFe",
        "payout_kind": "referral",
        "payout_detail": "referral_credits",
        "priority_tier": 52,
        "placements": ["manual_only", "links_hub_sfw", "links_hub_ai"],
        "network_keys": ["ai"],
        "copy_template": "⚕ {link} — uncensored open-weight API · Hermdog / agent stack",
    },
    # --- The Checkout List (@thecheckoutlist) — SFW silo only ---
    {
        "label": "Proton — $20 credits",
        "url": "https://pr.tn/ref/95GM632C",
        "payout_kind": "referral",
        "payout_detail": "referral_credits",
        "priority_tier": 11,
        "placements": ["links_hub_sfw"],
        "network_keys": [],
        "copy_template": "🔐 {link} — $20 Proton credits · mail & VPN",
    },
    {
        "label": "Chime",
        "url": "https://www.chime.com/r/ianmurphy47/",
        "payout_kind": "referral",
        "payout_detail": "referral_bonus",
        "priority_tier": 14,
        "placements": ["links_hub_sfw"],
        "network_keys": [],
        "copy_template": "💳 {link} — fee-free mobile banking",
    },
    {
        "label": "Rakuten",
        "url": "https://www.rakuten.com/r/IANMPO3?eeid=28187",
        "payout_kind": "referral",
        "payout_detail": "cashback",
        "priority_tier": 15,
        "placements": ["links_hub_sfw"],
        "network_keys": [],
        "copy_template": "🛍 {link} — cashback when you shop",
    },
    # --- AI tools lane (retention / bot directory) ---
    {
        "label": "Cherry Affair (nudify.systems)",
        "url": "https://link.nudify.systems/?r=Nzc4NzI4MjU2MeHdSjY",
        "payout_kind": "revshare",
        "payout_detail": "usd_revshare_crypto",
        "priority_tier": 8,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🕯️ {link} — Cherry Affair · 25% lifetime · TON/USDT/BTC withdraw",
    },
    {
        "label": "Nakedly (nudify.now)",
        "url": "https://nudify.now/?code=U214D",
        "payout_kind": "revshare",
        "payout_detail": "usd_revshare",
        "priority_tier": 18,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🧠 {link} — AI tools hub (revshare on purchases)",
    },
    {
        "label": "Playbun",
        "url": "https://www.playbun.com/?ref=freeusegod",
        "payout_kind": "revshare",
        "payout_detail": "usd_revshare",
        "priority_tier": 13,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — NSFW AI video",
    },
    {
        "label": "PornMaker AI",
        "url": "https://pornmaker.ai?ref=DExnc3FJ",
        "payout_kind": "revshare",
        "payout_detail": "usd_revshare",
        "priority_tier": 14,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — AI porn maker",
    },
    {
        "label": "Vixal — image to video",
        "url": "https://vixal.to/i2v/7787282561",
        "payout_kind": "revshare",
        "priority_tier": 14,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — still → motion (115k/mo)",
    },
    {
        "label": "Lucid Dreams Bot",
        "url": "https://t.me/luciddreams?start=_tgr_LISc0X42MTBh",
        "payout_kind": "revshare",
        "priority_tier": 12,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "💭 {link} — your AI girlfriend",
    },
    {
        "label": "Eetrrfgh Bot",
        "url": "https://t.me/eetrrfghbot?start=_tgr_wSlUZdFjNTgx",
        "payout_kind": "revshare",
        "priority_tier": 12,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "✨ {link} — TG sponsor bot",
    },
    {
        "label": "Vvv11r Bot",
        "url": "https://t.me/vvv11rbot?start=_tgr_fyTwFwI5NDdh",
        "payout_kind": "revshare",
        "priority_tier": 12,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "✨ {link} — TG sponsor bot",
    },
    {
        "label": "Perfecto 69 Bot",
        "url": "https://t.me/Perfecto_69_Bot?start=_tgr_5NKS5UYwOGMx",
        "payout_kind": "revshare",
        "priority_tier": 12,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "✨ {link} — AI companion bot",
    },
    {
        "label": "Hot Dreams Bot",
        "url": "https://hotdreamsai.com/?start=7787282561",
        "payout_kind": "revshare",
        "priority_tier": 15,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": [],
        "copy_template": "✨ {link} — photo/video dream engine",
    },
    {
        "label": "Video Generator bot",
        "url": "https://t.me/image2videos6919bot?start=7787282561",
        "payout_kind": "revshare",
        "priority_tier": 16,
        "placements": ["telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — image2video TG bot",
    },
    {
        "label": "DeleteMyPanties Bot",
        "url": "https://braundress.me/entry?start=eNCA01Du",
        "payout_kind": "revshare",
        "priority_tier": 17,
        "placements": ["telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🧠 {link} — undress TG bot",
    },
    {
        "label": "Fapify",
        "url": "https://www.fapify.com/?ref=freeusegod",
        "payout_kind": "revshare",
        "payout_detail": "usd_revshare",
        "priority_tier": 15,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎨 {link} — AI generator suite",
    },
    {
        "label": "AI Bot Gateway",
        "url": "https://botsgates-html.vercel.app/?b=img2vid&r=7787282561",
        "payout_kind": "revshare",
        "priority_tier": 19,
        "placements": ["telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🤖 {link} — img2vid / img2img gateway",
    },
    {
        "label": "Satisfactory (Randi123)",
        "url": "https://satisfactory.studio/r/ref_7787282561",
        "payout_kind": "revshare",
        "priority_tier": 20,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🤖 {link} — TG bot",
    },
    {
        "label": "AI ULTRA (Veners)",
        "url": "https://venersbot.com/7i85gp",
        "payout_kind": "revshare",
        "priority_tier": 20,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🤖 {link} — AI ULTRA TG bot",
    },
    {
        "label": "Sweet Sdx (Veners legacy)",
        "url": "https://venersbot.com/7787282561",
        "payout_kind": "revshare",
        "priority_tier": 22,
        "placements": ["telegram_footer", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "💋 {link} — TG bot",
    },
    {
        "label": "HeatMe",
        "url": "https://heatme.ai/r/wrzw79feke",
        "payout_kind": "revshare",
        "payout_detail": "platform_credits",
        "priority_tier": 33,
        "placements": ["telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🔥 {link} — invite credits",
    },
    {
        # Owned funnel — beacon wrap rewrites start=src_* to the placement ref,
        # so click → /start touch → Stars revenue join on one source_ref.
        "label": "AOF Spicy Companion",
        "url": "https://telegram.me/aof_spicybot_bot?start=src_companion_promo",
        "payout_kind": "funnel",
        "payout_detail": "funnel",
        # Tier 1 — owned Stars funnel; X rotation also biases every Nth slot to this row.
        "priority_tier": 1,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "💋 {link} — AOF AI girlfriend · free trial photo + chat in DM",
    },
    {
        "label": "Loot God free roll",
        "url": "https://telegram.me/aof_lootgod_bot?start=loot_free",
        "payout_kind": "funnel",
        "payout_detail": "funnel",
        "priority_tier": 40,
        "placements": ["telegram_footer", "loot_roll", "links_hub"],
        "network_keys": ["loot", "main", "voyeur", "goon"],
        "copy_template": "🎲 {link} — five free DM rolls (tier teaser)",
    },
    {
        "label": "Loot Goblin — channel FOMO",
        "url": "https://telegram.me/aof_lootgod_bot",
        "payout_kind": "funnel",
        "payout_detail": "funnel",
        "priority_tier": 41,
        "placements": ["telegram_footer", "loot_roll"],
        "network_keys": [],
        "copy_template": "👺 {link} — goblin grants blink into lanes on scrobble; tap Claim fast",
    },
]


def _encode_list(values: list[str]) -> str | None:
    cleaned = [v.strip().lower() for v in values if v and str(v).strip()]
    return json.dumps(cleaned) if cleaned else None


def _ensure_tables() -> None:
    from sqlalchemy import inspect

    from app.database.session import engine
    from app.models.base import Base
    from app.models.promo_affiliate_link import PromoAffiliateLink  # noqa: F401
    from app.models.promo_affiliate_rotation_cursor import PromoAffiliateRotationCursor  # noqa: F401

    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    if "promo_affiliate_links" not in names or "promo_affiliate_rotation_cursors" not in names:
        Base.metadata.create_all(
            bind=engine,
            tables=[
                PromoAffiliateLink.__table__,
                PromoAffiliateRotationCursor.__table__,
            ],
        )


def _purge_retired_affiliates(db) -> int:
    n = 0
    for row in db.query(PromoAffiliateLink).all():
        label = (row.label or "").strip()
        url = (row.url or "").strip().lower()
        if label in PURGE_LABELS or any(s in url for s in PURGE_URL_SUBSTRINGS):
            row.active = False
            n += 1
    return n


def main() -> None:
    _ensure_tables()
    db = SessionLocal()
    created = 0
    updated = 0
    try:
        purged = _purge_retired_affiliates(db)
        for item in SEED_ITEMS:
            url = str(item["url"]).strip()
            label = str(item["label"]).strip()
            row = db.query(PromoAffiliateLink).filter(PromoAffiliateLink.url == url).first()
            if not row:
                row = (
                    db.query(PromoAffiliateLink)
                    .filter(PromoAffiliateLink.label == label)
                    .first()
                )
            if not row:
                row = PromoAffiliateLink(label=label, url=url)
                db.add(row)
                created += 1
            else:
                updated += 1
            row.url = url
            row.label = str(item["label"])[:512]
            row.payout_kind = str(item.get("payout_kind") or "other")[:16]
            detail = item.get("payout_detail")
            row.payout_detail = str(detail).strip()[:64] if detail else None
            raw_tier = item.get("priority_tier")
            row.priority_tier = 10 if raw_tier is None else int(raw_tier)
            row.active = True
            row.placements_json = _encode_list(list(item.get("placements") or ["manual_only"]))
            row.network_keys_json = _encode_list(list(item.get("network_keys") or []))
            row.copy_template = str(item.get("copy_template") or "")[:1024] or None
        db.commit()
        print(f"Seed complete: created={created} updated={updated} purged={purged} total={len(SEED_ITEMS)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
