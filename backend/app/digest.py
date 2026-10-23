"""Weekly digest email job.

``uv run python -m app.digest`` emails each follower of a room with recent
activity a summary of it, with their personal unsubscribe link.
``build_digests`` is pure: it reads the store and returns what to send, and
never sends or reads the clock. Sending goes through ``EmailSender``.

Only confirmed follows get digests. Everything users wrote (the room name, feed lines) is
untrusted: the subject is kept to one line, and the body puts the unsubscribe link first and
makes every feed line a bullet with any further lines indented, so no user text can pass for
one of the email's own lines. Links carry the token in the URL fragment, which browsers never
send, so it stays out of server and proxy access logs.
"""

import logging
import os
import sys
import unicodedata
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


def get_email_sender() -> EmailSender:
    """FastAPI dependency: the sender for emails sent during a request. Nothing real is sent yet
    (``backlog/parked/110-api-email-sender.md``)."""
    return ConsoleSender()


def public_url() -> str:
    """The base URL of the web app, from ``FERNSLOP_PUBLIC_URL``, without a trailing slash."""
    return (os.environ.get("FERNSLOP_PUBLIC_URL") or DEFAULT_PUBLIC_URL).rstrip("/")


def unsubscribe_link(token: str) -> str:
    return f"{public_url()}/unsubscribe#token={token}"


def confirm_link(token: str) -> str:
    return f"{public_url()}/confirm-follow#token={token}"


def one_line(text: str) -> str:
    """``text`` with every control, format or separator character (other than a plain space)
    replaced by a space, so it fits on one header line."""
    return "".join(" " if char != " " and unicodedata.category(char)[0] in "CZ" else char for char in text)


def _bullet(text: str) -> str:
    """One feed line as a ``- `` bullet, with any further lines indented under it."""
    first, *rest = text.splitlines() or [""]
    return "\n".join([f"- {first}", *(f"  {line}" for line in rest)])


def confirmation_email(room_name: str, token: str) -> tuple[str, str]:
    """Subject and body of the email that confirms a new follow. The room name is only in the
    subject, on one line."""
    subject = one_line(f"Confirm weekly updates from {room_name}")
    body = (
        "Someone asked for weekly updates from a Fernslop garden to be sent to this address.\n\n"
        f"To confirm, open this link within 7 days: {confirm_link(token)}\n\n"
        "If it wasn't you, ignore this email and you won't hear from us again.\n"
    )
    return subject, body


def build_digests(store: StoreProtocol, now: datetime) -> list[Digest]:
    """One digest per confirmed follow of each room with a not-undone feed event in the 7 days up to ``now``.

    Soft-deleted rooms get none: ``list_rooms`` leaves them out.
    """
    since = now - DIGEST_WINDOW
    digests: list[Digest] = []
    for room in store.list_rooms():
        follows = [follow for follow in store.list_follows(room.id) if follow.confirmed_at is not None]
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
        lines = "\n".join(_bullet(event.text) for event in events)
        subject = one_line(f"This week in {room.name}")
        for follow in follows:
            body = (
                f"To stop these emails, unsubscribe here: {unsubscribe_link(follow.unsubscribe_token)}\n\n"
                "Here is what people wrote in the garden this week:\n\n"
                f"{lines}\n"
            )
            digests.append(
                Digest(
                    to=follow.email,
                    subject=subject,
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
