from app.utils.telegram_peer import extract_invite_hash, normalize_telethon_peer_identifier


def test_normalize_bare_digits_to_minus100():
    assert normalize_telethon_peer_identifier("3206350461") == "-1003206350461"


def test_extract_invite_hash_tme_plus():
    assert (
        extract_invite_hash("https://t.me/+hMQzGsBFjF02MDkx")
        == "hMQzGsBFjF02MDkx"
    )


def test_extract_invite_hash_joinchat():
    assert extract_invite_hash("https://t.me/joinchat/AbCdEf123") == "AbCdEf123"


def test_extract_invite_hash_bare_plus():
    assert extract_invite_hash("+4umB83be5n41MmEx") == "4umB83be5n41MmEx"


def test_extract_invite_hash_public_username_none():
    assert extract_invite_hash("https://t.me/somepublicchannel") is None
