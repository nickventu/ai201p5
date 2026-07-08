"""
tests/test_feed_listening_now_repro.py — Mixtape

Reproduction for Issue #2 (reported by nova):
"Friends Listening Now" shows friends whose last listen was YESTERDAY EVENING,
still appearing this morning. Expected: only friends who listened TODAY
should appear.

This test seeds the exact scenario from the bug report (a friend, "darius",
who listened at 11pm the previous night and hasn't opened the app since) and
checks the feed at 9am the next morning — the exact repro steps nova took.

We control "now" via mock instead of relying on wall-clock time, so the test
is deterministic regardless of when it's actually run.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from app import create_app, db
from models import User, Song, ListeningEvent, friendships
from services.feed_service import get_friends_listening_now


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def nova_and_darius(app):
    """Recreates the nova/darius friendship from the bug report."""
    with app.app_context():
        nova = User(username="nova", email="nova@mixtape.app")
        darius = User(username="darius", email="darius@mixtape.app")
        db.session.add_all([nova, darius])
        db.session.flush()

        db.session.execute(friendships.insert().values(user_id=nova.id, friend_id=darius.id))
        db.session.execute(friendships.insert().values(user_id=darius.id, friend_id=nova.id))

        song = Song(title="Late Night Drive", artist="Some Artist", shared_by=darius.id)
        db.session.add(song)
        db.session.commit()

        yield {"nova_id": nova.id, "darius_id": darius.id, "song_id": song.id}


def _fake_now(fixed_time):
    """Patch target for services.feed_service.datetime, keeping timedelta/timezone real."""
    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_time
    return _FakeDateTime


def test_repro_stale_listen_from_last_night_still_shows_this_morning(app, nova_and_darius):
    """
    Exact repro of nova's report:
      - darius listened at 11:00 PM last night (2024-06-10)
      - it is now 9:00 AM the next morning (2024-06-11)
      - darius has not opened the app since
      - EXPECTED: darius should NOT appear in "listening now" (his last
        listen was yesterday, not today)
      - ACTUAL (current buggy code): darius still appears, because the
        24-hour rolling window (`RECENT_THRESHOLD = timedelta(hours=24)`)
        hasn't elapsed yet (only ~10 hours have passed).
    """
    ids = nova_and_darius
    last_night = datetime(2024, 6, 10, 23, 0, 0, tzinfo=timezone.utc)   # darius's listen
    this_morning = datetime(2024, 6, 11, 9, 0, 0, tzinfo=timezone.utc)  # nova checks feed

    with app.app_context():
        event = ListeningEvent(
            user_id=ids["darius_id"],
            song_id=ids["song_id"],
            listened_at=last_night,
        )
        db.session.add(event)
        db.session.commit()

        with patch("services.feed_service.datetime", _fake_now(this_morning)):
            feed = get_friends_listening_now(ids["nova_id"])

        darius_in_feed = any(f["friend"]["username"] == "darius" for f in feed)

        # This assertion encodes the EXPECTED behavior per the bug report.
        # It currently FAILS against the buggy implementation, which is the
        # reproduction: darius (listened yesterday evening) still shows up
        # in "listening now" the next morning.
        assert not darius_in_feed, (
            "BUG REPRODUCED: darius's 11pm listen from the previous night "
            "is still showing up in 'listening now' at 9am the next day. "
            "get_friends_listening_now() is using a rolling 24h window "
            "(RECENT_THRESHOLD = timedelta(hours=24)) instead of a "
            "calendar-day ('today only') cutoff."
        )


def test_control_friend_who_listened_today_does_show(app, nova_and_darius):
    """
    Sanity control: a friend who listened EARLIER TODAY should still show up.
    This confirms the feed isn't just broadly broken — only the day-boundary
    logic is wrong.
    """
    ids = nova_and_darius
    earlier_today = datetime(2024, 6, 11, 7, 0, 0, tzinfo=timezone.utc)
    this_morning = datetime(2024, 6, 11, 9, 0, 0, tzinfo=timezone.utc)

    with app.app_context():
        event = ListeningEvent(
            user_id=ids["darius_id"],
            song_id=ids["song_id"],
            listened_at=earlier_today,
        )
        db.session.add(event)
        db.session.commit()

        with patch("services.feed_service.datetime", _fake_now(this_morning)):
            feed = get_friends_listening_now(ids["nova_id"])

        darius_in_feed = any(f["friend"]["username"] == "darius" for f in feed)
        assert darius_in_feed
