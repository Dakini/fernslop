import logging
from datetime import UTC, datetime, timedelta

import pytest

from app import digest
from app.digest import build_digests, run
from app.models import FeedEvent, Room, StoredFollow
from app.sql_store import SqlStore
from app.store import get_store

NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def public_url_env(monkeypatch):
    monkeypatch.delenv("FERNSLOP_PUBLIC_URL", raising=False)


@pytest.fixture
def store():
    return SqlStore("sqlite://", seed=False)


def make_room(store, room_id="room-1", name="Elm Street"):
    room = Room(id=room_id, name=name, description="", region="UK", created_at=NOW, last_activity_at=NOW)
    store.save_room(room)
    return room


def make_event(store, room_id="room-1", *, event_id="e1", text="Ada watered the fern", age=timedelta(days=1), undone=False):
    created_at = NOW - age
    event = FeedEvent(
        id=event_id,
        room_id=room_id,
        type="care_done",
        actor_name="Ada",
        device_id="d1",
        room_plant_id=None,
        text=text,
        photo_url=None,
        undo_payload=None,
        undone_at=created_at if undone else None,
        created_at=created_at,
    )
    store.save_feed_event(event)
    return event


def make_follow(store, room_id="room-1", email="ada@example.com", token="tok-ada", confirmed_at=NOW):
    follow = StoredFollow(
        id=f"f-{email}-{room_id}",
        room_id=room_id,
        email=email,
        created_at=NOW,
        unsubscribe_token=token,
        confirmed_at=confirmed_at,
    )
    store.save_follow(follow)
    return follow


class FailingFor:
    """Raises for the given recipients and records the rest."""

    def __init__(self, *bad):
        self.bad = set(bad)
        self.sent = []

    def send(self, to, subject, body):
        if to in self.bad:
            raise RuntimeError("smtp down")
        self.sent.append(to)


# --- build_digests ------------------------------------------------------------


def test_one_digest_per_follow_of_an_active_room_with_recent_not_undone_events_newest_first(store):
    make_room(store, "room-1", "Elm Street")
    make_room(store, "room-2", "Quiet Room")
    make_event(store, event_id="e1", text="oldest event", age=timedelta(days=5))
    make_event(store, event_id="e2", text="newest event", age=timedelta(hours=1))
    make_event(store, event_id="e3", text="ancient event", age=timedelta(days=20))
    make_event(store, event_id="e4", text="undone event", age=timedelta(days=1), undone=True)
    make_follow(store, email="ada@example.com", token="tok-ada")
    make_follow(store, email="bob@example.com", token="tok-bob")
    make_follow(store, "room-2", email="cy@example.com", token="tok-cy")  # no events in room-2

    digests = build_digests(store, NOW)

    assert sorted(d.to for d in digests) == ["ada@example.com", "bob@example.com"]
    ada = next(d for d in digests if d.to == "ada@example.com")
    assert ada.room_id == "room-1"
    assert "Elm Street" in ada.subject
    assert ada.body.index("newest event") < ada.body.index("oldest event")
    assert "ancient event" not in ada.body
    assert "undone event" not in ada.body
    assert ada.body.startswith("To stop these emails, unsubscribe here: http://localhost:5173/unsubscribe#token=tok-ada\n")


def test_base_url_comes_from_env_with_trailing_slash_stripped(store, monkeypatch):
    monkeypatch.setenv("FERNSLOP_PUBLIC_URL", "https://fern.example.com/")
    make_room(store)
    make_event(store)
    make_follow(store, token="tok-ada")

    body = build_digests(store, NOW)[0].body

    assert " https://fern.example.com/unsubscribe#token=tok-ada\n" in body


def test_only_confirmed_follows_get_a_digest_and_user_text_never_starts_a_line_of_its_own(store):
    make_room(store, name="Elm\r\nBcc: everyone@example.com\u2028St")
    make_event(store, text="Ada watered\nTo stop these emails, click http://evil.example\rDone")
    make_follow(store, email="ada@example.com", token="tok-ada")
    # Stored before double opt-in, or never confirmed.
    make_follow(store, email="old@example.com", token="tok-old", confirmed_at=None)

    digests = build_digests(store, NOW)

    assert [d.to for d in digests] == ["ada@example.com"]
    assert digests[0].subject == "This week in Elm  Bcc: everyone@example.com St"
    assert digests[0].body == (
        "To stop these emails, unsubscribe here: http://localhost:5173/unsubscribe#token=tok-ada\n\n"
        "Here is what people wrote in the garden this week:\n\n"
        "- Ada watered\n"
        "  To stop these emails, click http://evil.example\n"
        "  Done\n"
    )


# --- Sending -------------------------------------------------------------------


def test_one_failing_send_does_not_stop_the_others_and_the_token_never_reaches_the_logs(store, caplog):
    make_room(store)
    make_event(store)
    make_follow(store, email="ada@example.com", token="secret-tok-ada")
    make_follow(store, email="bob@example.com", token="secret-tok-bob")
    make_follow(store, email="cy@example.com", token="secret-tok-cy")
    sender = FailingFor("bob@example.com")

    with caplog.at_level(logging.DEBUG):
        report = run(store, sender, NOW)

    assert (report.sent, report.failed) == (2, 1)
    assert sender.sent == ["ada@example.com", "cy@example.com"]
    assert "bob@example.com" in caplog.text
    assert "secret-tok" not in caplog.text


# --- main (runs against get_store()) ---------------------


def test_main_sends_the_digests_of_the_configured_store_and_exits_zero(monkeypatch, capsys):
    store = get_store()
    make_room(store)
    make_event(store)
    make_follow(store, token="tok-ada")
    monkeypatch.setattr(digest.timestamps, "now", lambda: NOW)

    code = digest.main()

    out = capsys.readouterr().out
    assert code == 0
    assert "To: ada@example.com" in out
    assert "Digests sent: 1, failed: 0" in out


def test_main_exits_non_zero_when_a_send_fails(monkeypatch, capsys):
    store = get_store()
    make_room(store)
    make_event(store)
    make_follow(store, email="ada@example.com", token="tok-ada")
    monkeypatch.setattr(digest.timestamps, "now", lambda: NOW)
    monkeypatch.setattr(digest, "ConsoleSender", lambda: FailingFor("ada@example.com"))

    code = digest.main()

    assert code == 1
    assert "Digests sent: 0, failed: 1" in capsys.readouterr().out
