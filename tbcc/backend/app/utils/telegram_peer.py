"""Normalize Channel.identifier values for Telethon (get_input_entity / send_file)."""


def normalize_telethon_peer_identifier(raw: str | None) -> str:
    """
    Telegram channel / supergroup API ids use -100xxxxxxxxxx.

    Operators often paste only the inner digits (e.g. from /appeal3835807622 or RawDataBot
    fragments) or strip -100 thinking it means "group not channel". Telethon then raises
    ValueError: Cannot find any entity corresponding to "3835807622".

    - @username, t.me/..., +invite hashes: returned unchanged
    - bare digits: prefixed with -100
    - already -100... or other negative ids: unchanged
    """
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return s
    low = s.lower()
    if s.startswith("@"):
        return s
    if "t.me/" in low or low.startswith("http://") or low.startswith("https://"):
        return s
    if low.startswith("joinchat/"):
        return s
    if s.startswith("+") and not s.startswith("+-"):  # +hash invite
        return s
    if s.startswith("-100") and len(s) > 4 and s[4:].isdigit():
        return s
    if s.startswith("-") and s[1:].isdigit():
        return s
    if s.isdigit():
        return f"-100{s}"
    return s
