"""Tests for listening relay post history."""

from app.models.listening_relay_post_log import ListeningRelayPostLog
from app.services.listening_relay_compose import RelayOutbound
from app.services.listening_relay_history import list_listening_relay_posts, record_listening_relay_post


def test_record_and_list_relay_history(db):
    outbound = RelayOutbound(
        main_html="🎧 <b>Artist — Track</b>",
        copy_followups=[],
        artist="Artist",
        title="Track",
        album="Album",
        url="https://last.fm/music",
        source="lastfm",
        source_label="Last.fm",
        template_slot=1,
        template_slots_total=4,
        ascii_beat=True,
    )
    record_listening_relay_post(
        db,
        trigger="lastfm",
        channel_id=1,
        message_thread_id=42,
        random_lane=False,
        outbound=outbound,
        send_silent=True,
    )
    db.commit()

    payload = list_listening_relay_posts(db, limit=10)
    assert payload["items"]
    row = payload["items"][0]
    assert row["trigger"] == "lastfm"
    assert row["headline"] == "Artist — Track"
    assert row["album"] == "Album"
    assert row["ascii_beat"] is True
    assert row["template_slot"] == 1
    assert row["destination"]["thread_id"] == 42
    assert row["telegram_message_url"] is None

    stored = db.query(ListeningRelayPostLog).first()
    assert stored is not None
    assert stored.status == "queued"
