"""Weekly digest email job.

``uv run python -m app.digest`` emails each follower of a room with recent
activity a summary of it, with their personal unsubscribe link.
``build_digests`` is pure: it reads the store and returns what to send, and
never sends or reads the clock. Sending goes through ``EmailSender``.
"""

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app import timestamps
from app.store import StoreProtocol, get_store

logger = logging.getLogger(__name__)

DIGEST_WINDOW = timedelta(days=7)
DEFAULT_PUBLIC_URL = "http://localhost:5173"


@dataclass(frozen=True)
class Digest:
    """One email, for one follow of one room."""

    to: str
    subject: str
    body: str
    room_id: str


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleSender:
    """Prints each message instead of sending it."""

    def send(self, to: str, subject: str, body: str) -> None:
        print(f"To: {to}\nSubject: {subject}\n\n{body}\n")


class InMemorySender:
    """Records each message, for tests."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


@dataclass(frozen=True)
class SendReport:
    sent: int
    failed: int


def public_url() -> str:
    """The base URL of the web app, from ``FERNSLOP_PUBLIC_URL``, without a trailing slash."""
    return (os.environ.get("FERNSLOP_PUBLIC_URL") or DEFAULT_PUBLIC_URL).rstrip("/")


def build_digests(store: StoreProtocol, now: datetime) -> list[Digest]:
    """One digest per follow of each room with a not-undone feed event in the 7 days up to ``now``.

    Soft-deleted rooms get none: ``list_rooms`` leaves them out.
    """
    since = now - DIGEST_WINDOW
    base = public_url()
    digests: list[Digest] = []
    for room in store.list_rooms():
        follows = store.list_follows(room.id)
        if not follows:
            continue
        # list_feed_events is newest first.
        events = [
            event
            for event in store.list_feed_events(room.id)
            if event.undone_at is None and since <= event.created_at <= now
        ]
        if not events:
            continue
        lines = "\n".join(f"- {event.text}" for event in events)
        for follow in follows:
            body = (
                f"Here is what happened in {room.name} this week:\n\n"
                f"{lines}\n\n"
                f"To stop these emails, unsubscribe here: "
                f"{base}/unsubscribe?token={follow.unsubscribe_token}"
            )
            digests.append(
                Digest(
                    to=follow.email,
                    subject=f"This week in {room.name}",
                    body=body,
                    room_id=room.id,
                )
            )
    return digests


def send_digests(digests: list[Digest], sender: EmailSender) -> SendReport:
    """Send every digest; a failing send is logged and counted, and the rest still go out."""
    sent = failed = 0
    for digest in digests:
        try:
            sender.send(digest.to, digest.subject, digest.body)
        except Exception as exc:  # noqa: BLE001 - one bad send must not stop the rest
            failed += 1
            # Only the exception type: the body, and so the token, must stay out of logs.
            logger.error("Digest to %s failed: %s", digest.to, type(exc).__name__)
        else:
            sent += 1
    return SendReport(sent=sent, failed=failed)


def run(store: StoreProtocol, sender: EmailSender, now: datetime) -> SendReport:
    return send_digests(build_digests(store, now), sender)


def main() -> int:
    """Run the job. Exits non-zero if any send failed, so the scheduler notices."""
    logging.basicConfig(level=logging.INFO)
    report = run(get_store(), ConsoleSender(), timestamps.now())
    print(f"Digests sent: {report.sent}, failed: {report.failed}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
