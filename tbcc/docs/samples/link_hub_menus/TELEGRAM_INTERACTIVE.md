# Interactive LINK HUB menus on Telegram

## What Telegram does **not** support

**You cannot make regions inside a PNG clickable.** There is no image-map / hotspot API in Telegram bots or channels. Tapping the image itself does nothing unless the whole message has a single link (rare) or you use a Web App overlay.

If a menu *looks* like a picture but links work when you tap text, it is usually:

- **HTML text** with `<a href="...">` per row (not a PNG), or
- **A photo + inline keyboard buttons** under the image (this repo’s approach).

## What we ship

**Hybrid post:** menu artwork PNG + **inline URL buttons** — one button per channel lane or AI partner.

| Piece | Role |
|-------|------|
| `sendPhoto` | Visual menu artwork |
| `reply_markup.inline_keyboard` | Each button opens your gate URL or `affiliate_outbound_url` (referral / beacon wrap) |
| HTML caption | Short instructions |

Built in:

- [`backend/app/services/aof_links_hub_menu_variants.py`](../../backend/app/services/aof_links_hub_menu_variants.py) — `build_interactive_menu_post()`
- [`backend/app/services/telegram_bot_markup.py`](../../backend/app/services/telegram_bot_markup.py) — `send_photo_with_inline_keyboard()`
- [`backend/scripts/post_links_hub_interactive_menu.py`](../../backend/scripts/post_links_hub_interactive_menu.py) — dry-run / post

## Post to @aofmainhub (or any chat)

Payment bot (`BOT_TOKEN`) must be **admin** in the target chat.

```powershell
cd tbcc\backend

# Preview JSON (buttons + URLs) — needs DB + affiliate seed
python scripts\post_links_hub_interactive_menu.py --kind channels --variant v1

# AI partners menu (MotionMuse etc. from links_hub_ai)
python scripts\post_links_hub_interactive_menu.py --kind ai --variant v1

# Actually send
python scripts\post_links_hub_interactive_menu.py --kind ai --variant v1 --execute
```

Options: `--variant v1|v2|v3`, `--columns 2`, `--chat -1003970144685`

## Fully clickable **text** menu (no image)

For maximum link density without button rows, use the existing HTML bulletin — every line is a real `<a href>`:

- `build_links_hub_bulletin()` in `aof_growth_hub.py`
- Or HTML variants from `build_channel_menu_variant` / `build_ai_menu_variant` (v2/v3 use linked HTML, not `<pre>`)

## Button limits

- Button label: **64 characters** max
- URL: **512** chars (Bot API); use short URLs / beacon wrap when needed
- ~30 affiliate buttons + nav rows fits; for more, split into 2 messages or paginate (future).
