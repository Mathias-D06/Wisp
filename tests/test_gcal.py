"""D-050: Google Calendar: sync merge logic, the offline cache, time zones and daylight saving,
token storage and the connection service. A fake API stands in for Google; nothing here (or in
CI) talks to Google."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from wisp.db import Database
from wisp.gcal import google
from wisp.gcal.store import CalendarStore
from wisp.gcal.sync import BACKOFF_MIN, Backoff, sync_all
from wisp.gcal.times import (
    agenda,
    creation_body,
    day_label,
    event_from_item,
    localize,
    month_grid,
    parse_local,
    span_text,
    zone,
)

LONDON = zone("Europe/London")
NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


def timed(event_id, start, end, summary="Meeting", status="confirmed"):
    return {"id": event_id, "status": status, "summary": summary,
            "start": {"dateTime": start}, "end": {"dateTime": end},
            "htmlLink": f"https://www.google.com/calendar/event?eid={event_id}"}


def all_day(event_id, first, last_exclusive, summary="Holiday"):
    return {"id": event_id, "status": "confirmed", "summary": summary,
            "start": {"date": first}, "end": {"date": last_exclusive}}


class FakeApi:
    """Pages of events per calendar; full syncs and incremental syncs recorded."""

    def __init__(self):
        self.calendar_items = [
            {"id": "me@example.com", "summary": "Me", "backgroundColor": "#4285f4",
             "primary": True, "selected": True, "accessRole": "owner",
             "timeZone": "Europe/London"},
            {"id": "family", "summary": "Family", "backgroundColor": "#e67c73",
             "selected": True, "accessRole": "writer", "timeZone": "Europe/London"},
            {"id": "holidays", "summary": "UK holidays", "backgroundColor": "#0b8043",
             "selected": False, "accessRole": "reader"},
            {"id": "boss", "summary": "Boss (free/busy)", "accessRole": "freeBusyReader"},
        ]
        self.full = {"me@example.com": [[timed("a", "2026-10-13T10:00:00+01:00",
                                               "2026-10-13T11:00:00+01:00", "Standup")],
                                        [timed("b", "2026-10-14T15:00:00+01:00",
                                               "2026-10-14T16:00:00+01:00", "Dentist")]],
                     "family": [[all_day("h", "2026-10-15", "2026-10-17", "Half-term")]],
                     "holidays": [[all_day("x", "2026-12-25", "2026-12-26", "Christmas")]]}
        self.changes: dict[str, list[dict]] = {}
        self.gone: set[str] = set()
        self.calls: list[tuple] = []
        self.inserted: list[tuple] = []
        self.token = {"token": "access", "refresh_token": "refresh", "scopes": []}

    def calendars(self):
        return self.calendar_items

    def events_page(self, calendar_id, sync_token=None, page_token=None, time_min=None,
                    time_max=None):
        self.calls.append((calendar_id, sync_token, page_token, time_min is not None))
        if sync_token:
            assert time_min is None and time_max is None  # never together (events.list)
            if calendar_id in self.gone:
                self.gone.discard(calendar_id)
                raise google.SyncTokenGone("410")
            return {"items": self.changes.pop(calendar_id, []),
                    "nextSyncToken": f"{calendar_id}-t2"}
        pages = self.full.get(calendar_id, [[]])
        index = int(page_token or 0)
        response = {"items": pages[index]}
        if index + 1 < len(pages):
            response["nextPageToken"] = str(index + 1)  # no sync token on middle pages
        else:
            response["nextSyncToken"] = f"{calendar_id}-t1"
        return response

    def insert(self, calendar_id, body):
        self.inserted.append((calendar_id, body))
        return {"id": "new", "summary": body["summary"], "start": body["start"],
                "end": body["end"], "status": "confirmed"}

    def info(self):
        return self.token

    def bind(self, info):
        """Like GoogleCalendarApi(info): later info() returns these credentials."""
        self.token = dict(info)
        return self


@pytest.fixture
def store(tmp_path):
    return CalendarStore(Database(tmp_path / "wisp.sqlite3"))


def shown_events(store, days=30, start=NOW):
    return {e.id for e in store.events_between(start - timedelta(days=1),
                                               start + timedelta(days=days))}


# ----- sync -----------------------------------------------------------------------------------
def test_full_sync_pages_then_incremental_merges_changes_and_deletions(store):
    api = FakeApi()
    result = sync_all(api, store, NOW)
    assert (result.calendars, result.full) == (3, 3)  # the free/busy calendar is skipped
    assert store.sync_state("me@example.com")[0] == "me@example.com-t1"  # from the last page
    assert {"a", "b", "h"} <= shown_events(store)
    assert "x" not in shown_events(store, 100)  # in a calendar Google doesn't show
    api.changes["me@example.com"] = [
        timed("b", "2026-10-14T16:00:00+01:00", "2026-10-14T17:00:00+01:00", "Dentist (moved)"),
        {"id": "a", "status": "cancelled"},
        timed("c", "2026-10-16T09:00:00+01:00", "2026-10-16T09:30:00+01:00", "Call Ana")]
    result = sync_all(api, store, NOW + timedelta(minutes=5))
    assert result.full == 0 and (result.changed, result.removed) == (2, 1)
    events = {e.id: e for e in store.events_between(NOW, NOW + timedelta(days=7))}
    assert set(events) == {"b", "c", "h"}
    assert events["b"].title == "Dentist (moved)"
    assert events["b"].start == datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    incremental = [c for c in api.calls if c[1]]
    assert incremental and all(not c[3] for c in incremental)


def test_gone_sync_token_wipes_the_calendar_and_syncs_it_fully(store):
    api = FakeApi()
    sync_all(api, store, NOW)
    api.full["me@example.com"] = [[timed("z", "2026-10-20T10:00:00+01:00",
                                         "2026-10-20T11:00:00+01:00", "Fresh")]]
    api.gone.add("me@example.com")
    result = sync_all(api, store, NOW + timedelta(minutes=5))
    assert result.full == 1
    ids = shown_events(store)
    assert "z" in ids and not {"a", "b"} & ids  # old events gone, new full sync in


def test_full_sync_window_moves_on_weekly(store):
    api = FakeApi()
    sync_all(api, store, NOW)
    api.calls.clear()
    sync_all(api, store, NOW + timedelta(days=8))
    assert all(c[1] is None for c in api.calls)  # full syncs again, with a fresh window


def test_calendar_list_keeps_choices_and_drops_removed_calendars(store):
    api = FakeApi()
    sync_all(api, store, NOW)
    titles = {c["id"]: c for c in store.calendars()}
    assert set(titles) == {"me@example.com", "family", "holidays"}
    assert titles["me@example.com"]["shown"] and not titles["holidays"]["shown"]
    store.set_shown("holidays", True)
    store.set_shown("family", False)
    api.calendar_items = [c for c in api.calendar_items if c["id"] != "family"]
    sync_all(api, store, NOW + timedelta(minutes=5))
    titles = {c["id"]: c for c in store.calendars()}
    assert "family" not in titles and titles["holidays"]["shown"]  # choice kept
    assert "h" not in shown_events(store)  # the removed calendar's events went with it
    assert store.primary()["id"] == "me@example.com" and store.time_zone() == "Europe/London"
    assert store.find_calendar("uk holidays")["id"] == "holidays"


def test_the_cache_works_offline_after_a_restart(tmp_path):
    first = CalendarStore(Database(tmp_path / "wisp.sqlite3"))
    sync_all(FakeApi(), first, NOW)
    first.db.close()
    again = CalendarStore(Database(tmp_path / "wisp.sqlite3"))  # no API at all
    assert {"a", "b", "h"} <= shown_events(again)
    assert again.last_synced() == NOW
    again.clear()
    assert again.count() == 0 and again.calendars() == [] and again.last_synced() is None


def test_backoff_after_errors_and_back_to_every_five_minutes():
    backoff = Backoff()
    assert [backoff.failure() for _ in range(7)] == [*BACKOFF_MIN, 60, 60]
    assert backoff.success() == 5 and backoff.failure() == 5


# ----- times, time zones and daylight saving ------------------------------------------------
def test_the_repeated_hour_when_clocks_go_back_keeps_order_and_wall_time():
    bst = event_from_item("c", timed("1", "2026-10-25T01:30:00+01:00",
                                     "2026-10-25T01:45:00+01:00", "First 01:30"))
    gmt = event_from_item("c", timed("2", "2026-10-25T01:30:00Z", "2026-10-25T01:45:00Z",
                                     "Second 01:30"))
    [(day, events)] = agenda([gmt, bst], date(2026, 10, 25), 1, LONDON)
    assert day == date(2026, 10, 25) and [e.title for e in events] == ["First 01:30",
                                                                         "Second 01:30"]
    assert span_text(bst, day, LONDON) == span_text(gmt, day, LONDON) == "01:30–01:45"


def test_summer_and_winter_times_show_in_local_time():
    summer = event_from_item("c", timed("s", "2026-07-01T09:00:00Z", "2026-07-01T10:00:00Z"))
    winter = event_from_item("c", timed("w", "2026-12-01T09:00:00Z", "2026-12-01T10:00:00Z"))
    assert span_text(summer, date(2026, 7, 1), LONDON) == "10:00–11:00"  # BST = UTC+1
    assert span_text(winter, date(2026, 12, 1), LONDON) == "09:00–10:00"  # GMT


def test_new_event_durations_are_real_time_across_clock_changes():
    body = creation_body("Night shift", datetime(2026, 10, 25, 0, 30), "Europe/London",
                         minutes=120)
    assert body["start"] == {"dateTime": "2026-10-25T00:30:00+01:00",
                             "timeZone": "Europe/London"}
    assert body["end"]["dateTime"] == "2026-10-25T01:30:00+00:00"  # two real hours
    skipped = creation_body("Early", datetime(2026, 3, 29, 1, 30), "Europe/London", minutes=30)
    assert skipped["start"]["dateTime"] == "2026-03-29T02:30:00+01:00"  # 01:30 doesn't exist
    assert localize(datetime(2026, 10, 25, 1, 30), LONDON).utcoffset() == timedelta(hours=1)
    with pytest.raises(ValueError):
        creation_body("Backwards", datetime(2026, 10, 14, 15), "Europe/London",
                      end=datetime(2026, 10, 14, 14))


def test_all_day_and_multi_day_events():
    trip = event_from_item("c", all_day("t", "2026-10-15", "2026-10-18", "Trip"))
    assert trip.days(LONDON) == [date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17)]
    overnight = event_from_item("c", timed("o", "2026-10-15T22:00:00+01:00",
                                           "2026-10-16T02:00:00+01:00", "Flight"))
    assert overnight.days(LONDON) == [date(2026, 10, 15), date(2026, 10, 16)]
    assert span_text(overnight, date(2026, 10, 15), LONDON) == "from 22:00"
    assert span_text(overnight, date(2026, 10, 16), LONDON) == "until 02:00"
    standup = event_from_item("c", timed("s", "2026-10-16T09:00:00+01:00",
                                         "2026-10-16T09:15:00+01:00", "Standup"))
    days = agenda([standup, trip, overnight], date(2026, 10, 16), 1, LONDON)
    assert [e.title for e in days[0][1]] == ["Trip", "Flight", "Standup"]  # all-day first
    body = creation_body("Trip", datetime(2026, 10, 15), None, all_day=True,
                         end=datetime(2026, 10, 17))
    assert body["start"] == {"date": "2026-10-15"} and body["end"] == {"date": "2026-10-18"}


def test_month_grid_labels_and_parsing():
    grid = month_grid(2026, 10)
    assert len(grid) == 6 and grid[0][0] == date(2026, 9, 28)  # Monday first
    assert date(2026, 10, 31) in grid[4]
    assert day_label(date(2026, 10, 13), date(2026, 10, 13)) == "Today"
    assert day_label(date(2026, 10, 14), date(2026, 10, 13)) == "Tomorrow"
    assert day_label(date(2026, 10, 16), date(2026, 10, 13)) == "Fri 16 Oct"
    assert parse_local("2026-10-14 15:00") == datetime(2026, 10, 14, 15, 0)
    with pytest.raises(ValueError):
        parse_local("2026-10-14T15:00+01:00")


# ----- the OAuth client and tokens -------------------------------------------------------------
DESKTOP = ('{"installed": {"client_id": "123-abc.apps.googleusercontent.com", '
           '"client_secret": "s3cret", "auth_uri": "https://accounts.google.com/o/oauth2/auth", '
           '"token_uri": "https://oauth2.googleapis.com/token", '
           '"redirect_uris": ["http://localhost"]}}')


def test_only_desktop_app_clients_are_accepted():
    config = google.parse_client(DESKTOP)
    assert config["installed"]["client_id"].startswith("123-")
    assert google.client_label(config) == "123…apps.googleusercontent.com"
    with pytest.raises(google.CalendarError, match="Desktop app"):
        google.parse_client('{"web": {"client_id": "x"}}')
    for bad in ("not json", "[]", '{"installed": {"client_id": "x"}}'):
        with pytest.raises(google.CalendarError):
            google.parse_client(bad)


def test_scopes_start_read_only_and_add_only_owned_events():
    assert all(s.endswith(".readonly") for s in google.scopes_for(False))
    assert google.scopes_for(True)[-1].endswith("/calendar.events.owned")


@pytest.mark.windows
def test_tokens_are_stored_encrypted(tmp_path):
    from wisp.keystore import SecretJson

    path = tmp_path / "google_token.bin"
    secret = SecretJson(path, b"Wisp/test/v1", "Google token")
    secret.save({"refresh_token": "1//super-secret-refresh-token", "scopes": ["x"]})
    assert b"super-secret" not in path.read_bytes()  # DPAPI, not plain JSON
    assert secret.load()["refresh_token"] == "1//super-secret-refresh-token"
    assert SecretJson(path, b"other-entropy", "Google token").load() is None
    secret.clear()
    assert secret.load() is None and not secret.exists()


def test_google_errors_become_wisp_errors():
    import httplib2
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError

    api = google.GoogleCalendarApi.__new__(google.GoogleCalendarApi)

    class Request:
        def __init__(self, error):
            self.error = error

        def execute(self):
            raise self.error

    def http(status, body=b"{}"):
        return HttpError(httplib2.Response({"status": status}), body)

    cases = [(http(410), google.SyncTokenGone), (http(401), google.AuthExpired),
             (RefreshError("invalid_grant"), google.AuthExpired),
             (http(403, b'{"error": {"message": "Request had insufficient authentication '
                        b'scopes."}}'), google.MissingPermission),
             (http(500), google.CalendarError), (ConnectionResetError(), google.CalendarError)]
    for error, expected in cases:
        with pytest.raises(expected):
            api._run(Request(error))


def test_events_list_requests_follow_the_sync_rules():
    """Built from the bundled discovery document with a dummy token; nothing is sent."""
    from urllib.parse import parse_qs, urlparse

    api = google.GoogleCalendarApi({"token": "x", "refresh_token": "x", "client_id": "x",
                                    "client_secret": "x", "scopes": list(google.SCOPES_READ),
                                    "token_uri": "https://oauth2.googleapis.com/token"})
    requests = []
    api._run = lambda request: requests.append(request) or {}
    api.events_page("me@example.com", time_min="2026-10-06T00:00:00Z",
                    time_max="2027-04-11T00:00:00Z")
    api.events_page("me@example.com", sync_token="t1", page_token="p2")
    full, incremental = (parse_qs(urlparse(r.uri).query) for r in requests)
    same = {"singleEvents": ["true"], "showDeleted": ["true"], "maxResults": ["2500"]}
    assert same.items() <= full.items() and same.items() <= incremental.items()
    assert "timeMin" in full and "syncToken" not in full
    assert incremental["syncToken"] == ["t1"] and incremental["pageToken"] == ["p2"]
    assert not {"timeMin", "timeMax", "orderBy", "q", "updatedMin"} & incremental.keys()


# ----- the service (connect, sync, reconnect, disconnect, add) -----------------------------------
class MemorySecret:
    def __init__(self, value=None):
        self.value = value

    def load(self):
        return dict(self.value) if self.value is not None else None

    def save(self, value):
        self.value = dict(value)

    def clear(self):
        self.value = None

    def exists(self):
        return self.value is not None


@pytest.fixture
def service(qtbot, store):
    from wisp.gcal.service import CalendarService

    api = FakeApi()
    revoked = []
    granted = {"scopes": google.scopes_for(False)}

    def authorize(config, scopes):
        assert config["installed"]["client_id"].startswith("123-")
        return {"token": "t", "refresh_token": "r", "scopes": scopes}

    svc = CalendarService(store, MemorySecret(), MemorySecret(), api_factory=api.bind,
                          authorize=authorize, revoke=lambda info: revoked.append(info) or True,
                          now=lambda: NOW)
    svc.api, svc.revoked, svc.granted = api, revoked, granted
    return svc


def test_connect_syncs_and_disconnect_revokes_and_forgets(service, qtbot):
    assert service.state() == "disconnected" and not service.connect_account(False)  # no client
    service.import_client(DESKTOP)
    assert service.has_client() and service.connect_account(False)
    qtbot.waitUntil(lambda: service.busy is None and service.store.count() > 0, timeout=3000)
    assert service.state() == "connected" and not service.can_create()
    assert service._token_file.value["scopes"] == google.scopes_for(False)
    service.disconnect()
    qtbot.waitUntil(lambda: service.busy is None, timeout=3000)
    assert service.revoked and service.revoked[0]["refresh_token"] == "r"
    assert service.state() == "disconnected" and service.store.count() == 0


def test_expired_sign_in_asks_to_reconnect(service, qtbot):
    service._token_file.save({"token": "t", "refresh_token": "r", "scopes": []})

    def expired(*args, **kwargs):
        raise google.AuthExpired("Google sign-in expired or was revoked.")

    service.api.calendars = expired
    assert service.sync_now()
    qtbot.waitUntil(lambda: service.busy is None, timeout=3000)
    assert service.state() == "reconnect" and "expired" in service.error
    assert not service.sync_now()  # no retry loop until the user reconnects


def test_sync_errors_back_off(service, qtbot):
    service._token_file.save({"token": "t", "refresh_token": "r", "scopes": []})

    def offline(*args, **kwargs):
        raise google.CalendarError("Couldn't reach Google Calendar (ConnectionError).")

    service.api.calendars = offline
    service.sync_now()
    qtbot.waitUntil(lambda: service.busy is None, timeout=3000)
    assert service.state() == "error" and service._timer.interval() == 5 * 60_000
    service.sync_now()
    qtbot.waitUntil(lambda: service.busy is None, timeout=3000)
    assert service._timer.interval() == 10 * 60_000


def test_adding_events_needs_the_owned_events_scope(service, qtbot):
    service._token_file.save({"token": "t", "refresh_token": "r",
                              "scopes": google.scopes_for(False)})
    service.sync_now()
    qtbot.waitUntil(lambda: service.busy is None, timeout=3000)
    body = creation_body("Dentist", datetime(2026, 10, 14, 15), "Europe/London", minutes=30)
    with pytest.raises(google.MissingPermission):
        service.create("me@example.com", body)
    service._token_file.save({"token": "t", "refresh_token": "r",
                              "scopes": google.scopes_for(True)})
    assert service.can_create()
    event = service.create("me@example.com", body)
    assert event.title == "Dentist" and service.api.inserted[0][0] == "me@example.com"
    assert "new" in shown_events(service.store)  # cached at once
    for shared in ("UK holidays", "Family"):  # read-only; shared with write access
        with pytest.raises(google.CalendarError, match="don't own"):
            service.writable_calendar(shared)
    assert service.writable_calendar(None)["id"] == "me@example.com"


def test_next_event_for_the_island(service, qtbot):
    service._token_file.save({"token": "t", "refresh_token": "r", "scopes": []})
    service.sync_now()
    qtbot.waitUntil(lambda: service.busy is None, timeout=3000)
    standup_start = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)  # 10:00 BST
    soon = service.next_event(standup_start - timedelta(minutes=8), 10)
    assert soon is not None and soon.title == "Standup"
    assert service.next_event(standup_start - timedelta(minutes=30), 10) is None
    assert service.next_event(standup_start - timedelta(minutes=8), 0) is None  # setting off
