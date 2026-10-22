import logging
from datetime import UTC, datetime, timedelta

import pytest

from app import digest
from app.digest import ConsoleSender, InMemorySender, build_digests, run
from app.models import FeedEvent, Room, StoredFollow
from app.store import Store

NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def public_url_env(monkeypatch):
    monkeypatch.delenv("FERNSLOP_PUBLIC_URL", raising=False)


@pytest.fixture
def store():
    return Store(seed=False)


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


def make_follow(store, room_id="room-1", email="ada@example.com", token="tok-ada"):
    follow = StoredFollow(
        id=f"f-{email}-{room_id}", room_id=room_id, email=email, created_at=NOW, unsubscribe_token=token
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


# --- build_digests: who gets one ---------------------------------------------


def test_one_digest_per_follow_with_recipient_subject_body_and_room(store):
    make_room(store)
    make_event(store)
    make_follow(store, email="ada@example.com", token="tok-ada")
    make_follow(store, email="bob@example.com", token="tok-bob")

    digests = build_digests(store, NOW)

    assert sorted(d.to for d in digests) == ["ada@example.com", "bob@example.com"]
    for d in digests:
        assert d.room_id == "room-1"
        assert "Elm Street" in d.subject
        assert d.body


def test_room_without_follows_gives_no_digest(store):
    make_room(store)
    make_event(store)

    assert build_digests(store, NOW) == []


def test_one_follower_of_two_active_rooms_gets_one_digest_per_room(store):
    make_room(store, "room-1", "Elm Street")
    make_room(store, "room-2", "Balcony")
    make_event(store, "room-1", event_id="e1")
    make_event(store, "room-2", event_id="e2")
    make_follow(store, "room-1", token="t1")
    make_follow(store, "room-2", token="t2")

    digests = build_digests(store, NOW)

    assert sorted(d.room_id for d in digests) == ["room-1", "room-2"]


def test_build_digests_does_not_read_the_clock_or_change_the_store(store, monkeypatch):
    make_room(store)
    make_event(store)
    make_follow(store)
    monkeypatch.setattr(digest.timestamps, "now", lambda: pytest.fail("clock read"), raising=False)
    before = store.list_feed_events("room-1")

    build_digests(store, NOW)

    assert store.list_feed_events("room-1") == before


# --- build_digests: active window ---------------------------------------------


def test_six_day_old_event_counts_and_eight_day_old_does_not(store):
    make_room(store, "room-1", "Fresh")
    make_room(store, "room-2", "Stale")
    make_event(store, "room-1", event_id="e1", age=timedelta(days=6))
    make_event(store, "room-2", event_id="e2", age=timedelta(days=8))
    make_follow(store, "room-1", token="t1")
    make_follow(store, "room-2", token="t2")

    digests = build_digests(store, NOW)

    assert [d.room_id for d in digests] == ["room-1"]


def test_room_with_recent_last_activity_but_only_old_events_gives_no_digest(store):
    room = make_room(store)  # last_activity_at == NOW
    assert room.last_activity_at == NOW
    make_event(store, age=timedelta(days=9))
    make_follow(store)

    assert build_digests(store, NOW) == []


def test_old_events_are_not_listed_beside_recent_ones(store):
    make_room(store)
    make_event(store, event_id="e1", text="recent thing", age=timedelta(days=2))
    make_event(store, event_id="e2", text="ancient thing", age=timedelta(days=20))
    make_follow(store)

    body = build_digests(store, NOW)[0].body

    assert "recent thing" in body
    assert "ancient thing" not in body


# --- build_digests: body --------------------------------------------------------


def test_body_names_the_room_and_lists_event_text_newest_first(store):
    make_room(store, name="Elm Street")
    make_event(store, event_id="e1", text="oldest event", age=timedelta(days=5))
    make_event(store, event_id="e3", text="newest event", age=timedelta(hours=1))
    make_event(store, event_id="e2", text="middle event", age=timedelta(days=2))
    make_follow(store)

    body = build_digests(store, NOW)[0].body

    assert "Elm Street" in body
    assert body.index("newest event") < body.index("middle event") < body.index("oldest event")


def test_undone_events_never_appear(store):
    make_room(store)
    make_event(store, event_id="e1", text="kept event", age=timedelta(days=1))
    make_event(store, event_id="e2", text="undone event", age=timedelta(days=1), undone=True)
    make_follow(store)

    body = build_digests(store, NOW)[0].body

    assert "kept event" in body
    assert "undone event" not in body


def test_room_whose_only_recent_events_are_undone_gets_no_digest(store):
    make_room(store)
    make_event(store, event_id="e1", undone=True)
    make_event(store, event_id="e2", age=timedelta(days=30))
    make_follow(store)

    assert build_digests(store, NOW) == []


# --- build_digests: unsubscribe link -------------------------------------------


def test_body_ends_with_the_followers_unsubscribe_link_on_the_default_base(store):
    make_room(store)
    make_event(store)
    make_follow(store, token="tok-ada")

    body = build_digests(store, NOW)[0].body

    assert body.endswith("http://localhost:5173/unsubscribe?token=tok-ada")


def test_two_followers_get_two_different_links(store):
    make_room(store)
    make_event(store)
    make_follow(store, email="ada@example.com", token="tok-ada")
    make_follow(store, email="bob@example.com", token="tok-bob")

    bodies = {d.to: d.body for d in build_digests(store, NOW)}

    assert bodies["ada@example.com"].endswith("/unsubscribe?token=tok-ada")
    assert bodies["bob@example.com"].endswith("/unsubscribe?token=tok-bob")
    assert "tok-bob" not in bodies["ada@example.com"]


@pytest.mark.parametrize("configured", ["https://fern.example.com", "https://fern.example.com/", "https://fern.example.com//"])
def test_base_url_comes_from_env_with_trailing_slash_stripped(store, monkeypatch, configured):
    monkeypatch.setenv("FERNSLOP_PUBLIC_URL", configured)
    make_room(store)
    make_event(store)
    make_follow(store, token="tok-ada")

    body = build_digests(store, NOW)[0].body

    assert body.endswith(" https://fern.example.com/unsubscribe?token=tok-ada")
    assert "//unsubscribe" not in body


# --- Senders ---------------------------------------------------------------------


def test_in_memory_sender_records_each_message():
    sender = InMemorySender()

    sender.send("a@example.com", "Hi", "Body")

    assert sender.sent == [("a@example.com", "Hi", "Body")]


def test_console_sender_prints_the_message(capsys):
    ConsoleSender().send("a@example.com", "Hi there", "Body text")

    out = capsys.readouterr().out
    assert "a@example.com" in out
    assert "Hi there" in out
    assert "Body text" in out


def test_run_sends_every_digest_and_reports_counts(store):
    make_room(store)
    make_event(store)
    make_follow(store, email="ada@example.com", token="tok-ada")
    make_follow(store, email="bob@example.com", token="tok-bob")
    sender = InMemorySender()

    report = run(store, sender, NOW)

    assert (report.sent, report.failed) == (2, 0)
    assert sorted(to for to, _, _ in sender.sent) == ["ada@example.com", "bob@example.com"]


def test_main_uses_console_sender_and_the_clock_from_timestamps(monkeypatch, capsys, store):
    make_room(store)
    make_event(store)
    make_follow(store, token="tok-ada")
    monkeypatch.setattr("app.store.store", store)
    monkeypatch.setattr(digest.timestamps, "now", lambda: NOW)

    code = digest.main()

    out = capsys.readouterr().out
    assert code == 0
    assert "To: ada@example.com" in out
    assert "Digests sent: 1, failed: 0" in out


# --- Failures ----------------------------------------------------------------------


def test_one_failing_send_does_not_stop_the_others_and_is_reported(store, caplog):
    make_room(store)
    make_event(store)
    make_follow(store, email="ada@example.com", token="tok-ada")
    make_follow(store, email="bob@example.com", token="tok-bob")
    make_follow(store, email="cy@example.com", token="tok-cy")
    sender = FailingFor("bob@example.com")

    with caplog.at_level(logging.ERROR, logger="app.digest"):
        report = run(store, sender, NOW)

    assert (report.sent, report.failed) == (2, 1)
    assert sender.sent == ["ada@example.com", "cy@example.com"]
    assert "bob@example.com" in caplog.text


def test_main_exits_non_zero_and_prints_counts_when_a_send_fails(monkeypatch, capsys, store):
    make_room(store)
    make_event(store)
    make_follow(store, email="ada@example.com", token="tok-ada")
    monkeypatch.setattr("app.store.store", store)
    monkeypatch.setattr(digest.timestamps, "now", lambda: NOW)
    monkeypatch.setattr(digest, "ConsoleSender", lambda: FailingFor("ada@example.com"))

    code = digest.main()

    assert code == 1
    assert "Digests sent: 0, failed: 1" in capsys.readouterr().out


# --- Token hygiene --------------------------------------------------------------------


def test_token_appears_only_inside_the_link_in_console_output_and_never_in_logs(store, capsys, caplog):
    make_room(store)
    make_event(store)
    make_follow(store, email="ada@example.com", token="secret-tok-ada")
    make_follow(store, email="bob@example.com", token="secret-tok-bob")
    digests = build_digests(store, NOW)
    # Console output: each token once, as part of its link.
    digest.send_digests(digests, ConsoleSender())
    out = capsys.readouterr().out
    assert out.count("secret-tok-ada") == 1
    assert out.count("secret-tok-bob") == 1
    assert "/unsubscribe?token=secret-tok-ada" in out

    # Logs: a failed send must not leak the token.
    with caplog.at_level(logging.DEBUG):
        report = digest.send_digests(digests, FailingFor("ada@example.com", "bob@example.com"))

    assert report.failed == 2
    assert "secret-tok" not in caplog.text
