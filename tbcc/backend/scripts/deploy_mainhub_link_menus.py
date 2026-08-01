#!/usr/bin/env python3
"""Deploy all interactive LINK HUB menus to @aofmainhub (seed + post).

Works with DB when available; falls back to static seed + manual gate URLs.

  python scripts/deploy_mainhub_link_menus.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_network import ADDLIST_RAW, MAINHUB_CHANNEL_IDENT, MAINHUB_RAW, MAIN_GROUP_INVITE
from app.services.aof_links_hub_menu_variants import (
    AI_VARIANTS,
    CHANNEL_PIPES,
    CHANNEL_VARIANTS,
    MENU_IMAGE_DIR,
    _interactive_menu_caption,
    build_interactive_menu_post,
)
from app.services.telegram_bot_markup import send_photo_with_inline_keyboard


def _load_seed_items() -> list[dict]:
    path = BACKEND / "scripts" / "seed_promo_affiliate_links.py"
    spec = importlib.util.spec_from_file_location("seed_promo_affiliate_links", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return list(mod.SEED_ITEMS)


def _gate_url(key: str) -> str:
    from app.data.aof_manual_gate_links import manual_gate_url
    from app.data.aof_network import network_channel_by_key

    url = (manual_gate_url(key) or "").strip()
    if not url:
        ch = network_channel_by_key(key)
        url = (ch.invite if ch else "").strip()
    return url


def _short_btn(text: str, *, max_len: int = 64) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"


def _chunk(buttons: list[dict[str, str]], columns: int = 2) -> list[list[dict[str, str]]]:
    cols = max(1, min(columns, 3))
    return [buttons[i : i + cols] for i in range(0, len(buttons), cols)]


def _offline_channel_keyboard(*, columns: int = 2) -> list[list[dict[str, str]]]:
    buttons: list[dict[str, str]] = []
    for num, key, label in CHANNEL_PIPES:
        url = _gate_url(key)
        if not url:
            continue
        short = label.split("·")[0].strip() if "·" in label else label
        buttons.append({"text": _short_btn(f"{num} {short}"), "url": url})
    nav = [
        {"text": "🔗 HUB", "url": MAINHUB_RAW},
        {"text": "🪙 LOOT", "url": _gate_url("loot") or MAIN_GROUP_INVITE},
        {"text": "📌 ADDLIST", "url": _gate_url("addlist") or ADDLIST_RAW},
    ]
    return _chunk(buttons, columns) + [nav]


def _offline_ai_keyboard(seed: list[dict], *, columns: int = 2, limit: int = 18) -> list[list[dict[str, str]]]:
    rows = []
    for item in seed:
        placements = [str(p).strip().lower() for p in (item.get("placements") or [])]
        if "links_hub_ai" not in placements:
            continue
        url = str(item.get("url") or "").strip()
        if not url.startswith(("http://", "https://", "tg://")):
            continue
        rows.append(item)
    rows.sort(key=lambda it: (int(it.get("priority_tier") or 10), str(it.get("label") or "")))
    buttons: list[dict[str, str]] = []
    for i, item in enumerate(rows[:limit], start=1):
        label = str(item.get("label") or "Partner").strip()
        buttons.append({"text": _short_btn(f"{i:02d} {label}"), "url": url if (url := str(item.get("url")).strip()) else ""})
    footer = [
        {"text": "📋 Secretary", "url": "https://t.me/aof_secretary_bot"},
        {"text": "🎲 Loot God", "url": "https://t.me/aof_lootgod_bot?start=loot_free"},
        {"text": "🌶 Spicy", "url": "https://t.me/aof_spicybot_bot"},
    ]
    nav = [
        {"text": "🔗 HUB", "url": MAINHUB_RAW},
        {"text": "🪙 LOOT", "url": _gate_url("loot") or MAIN_GROUP_INVITE},
    ]
    return _chunk(buttons, columns) + [footer, nav]


def _caption(kind: str, variant: str, title: str) -> str:
    return _interactive_menu_caption(kind, title)  # type: ignore[arg-type]


def _variant_title(kind: str, variant: str) -> str:
    titles = {
        ("channels", "v1"): "CLASSIC ORANGE PANEL",
        ("channels", "v2"): "NEON GRID",
        ("channels", "v3"): "VHS BROADCAST",
        ("ai", "v1"): "DARK PANEL",
        ("ai", "v2"): "REVEAL BOARD",
        ("ai", "v3"): "UNIFORM GRID",
    }
    return titles.get((kind, variant), variant.upper())


def _image_file(kind: str, variant: str) -> Path:
    from app.services.aof_links_hub_menu_variants import MENU_IMAGE_FILES

    name = MENU_IMAGE_FILES[(kind, variant)]  # type: ignore[index]
    return MENU_IMAGE_DIR / name


def _seed_affiliates(execute: bool) -> dict:
    if not execute:
        return {"ok": True, "dry_run": True}
    try:
        path = BACKEND / "scripts" / "seed_promo_affiliate_links.py"
        spec = importlib.util.spec_from_file_location("seed_promo_affiliate_links", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        mod.main()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def _sync_affiliate_rotation(execute: bool) -> dict:
    if not execute:
        return {"ok": True, "dry_run": True}
    try:
        from app.database.session import SessionLocal
        from app.services.aof_growth_hub import sync_affiliate_network

        db = SessionLocal()
        try:
            sync_affiliate_network(db)
            db.commit()
            return {"ok": True}
        finally:
            db.close()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "skipped": "db_unavailable"}


def _build_posts(db=None, *, columns: int = 2) -> list[dict]:
    posts: list[dict] = []
    seed = _load_seed_items()
    if db is not None:
        try:
            for kind, variants in (("channels", CHANNEL_VARIANTS), ("ai", AI_VARIANTS)):
                for variant in variants:
                    post = build_interactive_menu_post(db, kind, variant, button_columns=columns)
                    posts.append(
                        {
                            "kind": kind,
                            "variant": variant,
                            "title": post.title,
                            "caption": post.caption_html,
                            "keyboard": post.inline_keyboard,
                            "image": str(post.image_path),
                        }
                    )
            return posts
        except Exception:
            pass
    for kind, variants in (("channels", CHANNEL_VARIANTS), ("ai", AI_VARIANTS)):
        for variant in variants:
            title = _variant_title(kind, variant)
            img = _image_file(kind, variant)
            kb = _offline_channel_keyboard(columns=columns) if kind == "channels" else _offline_ai_keyboard(seed, columns=columns)
            posts.append(
                {
                    "kind": kind,
                    "variant": variant,
                    "title": title,
                    "caption": _caption(kind, variant, title),
                    "keyboard": kb,
                    "image": str(img),
                }
            )
    return posts


async def _try_telethon_photo(chat_id: str, post: dict) -> dict:
    from telethon import TelegramClient
    from telethon.errors import RPCError

    from app.services.scheduled_post_service import _build_reply_markup
    from app.utils.telegram_peer import resolve_poster_peer
    from app.utils.telethon_session import admin_session_stem, import_session_stem, poster_session_stem

    api_id = int((os.getenv("API_ID") or "0").strip() or 0)
    api_hash = (os.getenv("API_HASH") or "").strip()
    img = Path(post["image"])
    markup = _build_reply_markup(post["keyboard"])
    for label, stem in (("admin_poster", poster_session_stem()), ("admin", admin_session_stem()), ("admin_import", import_session_stem())):
        if not Path(f"{stem}.session").is_file():
            continue
        client = TelegramClient(stem, api_id, api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                continue
            peer = await resolve_poster_peer(client, chat_id, invite_fallback=MAINHUB_RAW)
            msg = await client.send_file(
                peer,
                str(img),
                caption=post["caption"],
                parse_mode="html",
                buttons=markup,
                force_document=False,
            )
            return {"ok": True, "method": f"telethon:{label}", "message_id": int(getattr(msg, "id", 0) or 0)}
        except RPCError as e:
            last = f"{e.__class__.__name__}: {str(e)[:200]}"
        except Exception as e:
            last = str(e)[:300]
        finally:
            await client.disconnect()
    return {"ok": False, "method": "telethon", "error": last if "last" in dir() else "no session"}


async def _post_all(chat_id: str, posts: list[dict], *, execute: bool, delay_s: float) -> list[dict]:
    results: list[dict] = []
    for post in posts:
        row = {"kind": post["kind"], "variant": post["variant"], "title": post["title"]}
        if not execute:
            row.update({"ok": True, "dry_run": True, "image": post["image"], "buttons": sum(len(r) for r in post["keyboard"])})
            results.append(row)
            continue
        if not Path(post["image"]).is_file():
            row.update({"ok": False, "error": f"missing image {post['image']}"})
            results.append(row)
            continue
        mid = await send_photo_with_inline_keyboard(
            chat_id,
            photo_path=post["image"],
            caption=post["caption"],
            buttons_data=post["keyboard"],
        )
        if mid:
            row.update({"ok": True, "method": "payment_bot", "message_id": mid})
        else:
            fb = await _try_telethon_photo(chat_id, post)
            row.update(fb)
        results.append(row)
        if delay_s > 0:
            await asyncio.sleep(delay_s)
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="Deploy interactive LINK HUB menus to @aofmainhub")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--chat", default=MAINHUB_CHANNEL_IDENT)
    p.add_argument("--columns", type=int, default=2)
    p.add_argument("--delay", type=float, default=2.0, help="Seconds between posts")
    p.add_argument("--skip-seed", action="store_true")
    args = p.parse_args()

    report: dict = {"chat": args.chat, "execute": args.execute, "steps": {}}
    if not args.skip_seed:
        report["steps"]["seed_affiliates"] = _seed_affiliates(args.execute)
        report["steps"]["sync_affiliate_rotation"] = _sync_affiliate_rotation(args.execute)

    db = None
    if args.execute:
        try:
            from app.database.session import SessionLocal

            db = SessionLocal()
            db.execute(__import__("sqlalchemy").text("select 1"))
        except Exception:
            db = None
            report["db"] = "offline_static_fallback"

    try:
        posts = _build_posts(db, columns=max(1, min(3, args.columns)))
        report["post_count"] = len(posts)
        report["posts"] = asyncio.run(_post_all(args.chat, posts, execute=args.execute, delay_s=args.delay))
    finally:
        if db is not None:
            db.close()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = all(p.get("ok") for p in report.get("posts", []))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
