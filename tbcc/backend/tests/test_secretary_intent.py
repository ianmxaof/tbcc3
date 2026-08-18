from app.services.secretary_behavior import apply_symmetry, corpus_candidates, payment_lane, sanitize_reply
from app.services.secretary_intent import classify_intent
from app.services.secretary_sales_coach import build_sales_coach_suffix


def test_classify_hi_is_noise():
    assert classify_intent("Hi") == "noise"
    assert classify_intent("Hello mate.") == "noise"
    assert classify_intent("Are you interested in buying links?") == "noise"
    assert classify_intent("Why did you block my colleague?") == "noise"


def test_classify_buyer_and_faq():
    assert classify_intent("I want to join") == "buyer"
    assert classify_intent("how much is VIP") == "faq"


def test_corpus_hi_skips_payment_bot():
    cands = corpus_candidates("Hi", intent="noise")
    assert cands is not None
    blob = " ".join(cands.values()).lower()
    assert "subscribe" not in blob
    assert "payment" not in blob


def test_symmetry_hi_stays_short():
    long = "Hey there! I appreciate you reaching out. How can I assist you today with subscriptions?"
    out = apply_symmetry("Hi", long, variant="natural")
    assert len(out.split()) <= 6
    assert "assist you" not in out.lower()


def test_sanitize_strips_signature():
    raw = 'I can\'t share contacts. If you have questions about our services or subscriptions, feel free to ask! AOF SECRETARY, 23:53'
    out = sanitize_reply(raw)
    assert "AOF SECRETARY" not in out
    assert "feel free to ask" not in out.lower()


def test_payment_lane_intro_stars_recovery_private():
    assert payment_lane("introduction", message_count=1) == "stars"
    assert payment_lane("recovery", message_count=2) == "private"


def test_sales_coach_silent_on_hi(db, monkeypatch):
    monkeypatch.setenv("TBCC_SECRETARY_RAG_ENABLED", "0")
    suffix, hint = build_sales_coach_suffix("Hi", db=db)
    assert suffix == ""
    assert hint == ""
