"""Post digest layout variants to Storage Hub Workshop (topic 3092).

One-shot. Does not start any bot process. Uses album-composer (or secretary) token
from tbcc/.env via HTTP sendMessage only.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HUB = -1003812457581
WORKSHOP_THREAD = 3092
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
VARIANTS_DIR = Path(__file__).resolve().parent / "variants"

INTRO = """<b>DIGEST LAYOUT PICK</b>

Four rewrites of the Fri 21 Aug digest. Reply with <b>A</b>, <b>B</b>, <b>C</b>, or <b>D</b>.

All four already follow the rules you called out:
• no angle-bracket emails (those were being parsed as HTML tags)
• no body quote-indents
• emoji outside, title inside the quote block
• settings-page links on every action
• warning-triangle reserved for real money/lockout — not used here

<b>A</b> quote-title cards (closest to your mock) + tap buttons
<b>B</b> action-first — the first line of each card is the tap
<b>C</b> densest ops board
<b>D</b> same cards, quieter chrome"""

A_BUTTONS = {
    "inline_keyboard": [
        [{"text": "Wells Fargo login", "url": "https://connect.secure.wellsfargo.com/auth/login/present"}],
        [{"text": "GitHub Applications", "url": "https://github.com/settings/applications"}],
        [{"text": "Google connections", "url": "https://myaccount.google.com/connections"}],
        [{"text": "SCCHA RentCafe portal", "url": "https://portal.scchousingauthority.org/"}],
    ]
}


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _token(env: dict[str, str]) -> tuple[str, str]:
    for key in (
        "TBCC_ALBUM_COMPOSER_BOT_TOKEN",
        "TBCC_SECRETARY_BOT_TOKEN",
        "SECRETARY_BOT_TOKEN",
    ):
        val = (env.get(key) or "").strip()
        if val:
            return key, val
    raise SystemExit("No bot token in tbcc/.env (album composer or secretary)")


def send(token: str, text: str, reply_markup: dict | None = None) -> int:
    payload: dict = {
        "chat_id": HUB,
        "message_thread_id": WORKSHOP_THREAD,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Telegram HTTP {exc.code}: {err[:500]}") from exc
    if not body.get("ok"):
        raise SystemExit(f"Telegram not ok: {body}")
    return int(body["result"]["message_id"])


def main() -> None:
    _key, token = _token(_parse_env(ENV_PATH))
    posted: list[tuple[str, int]] = []
    mid = send(token, INTRO)
    posted.append(("intro", mid))
    for letter in ("A", "B", "C", "D"):
        html = (VARIANTS_DIR / f"{letter}.html").read_text(encoding="utf-8").strip()
        markup = A_BUTTONS if letter == "A" else None
        mid = send(token, html, reply_markup=markup)
        posted.append((letter, mid))
    print("posted to Workshop https://t.me/c/3812457581/3092")
    for label, mid in posted:
        print(f"  {label}: message_id={mid}")


if __name__ == "__main__":
    main()
