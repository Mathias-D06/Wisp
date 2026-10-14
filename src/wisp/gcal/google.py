"""Google sign-in and the Calendar API (D-050), with Google's official Python libraries:
google-auth-oauthlib for the installed-app flow, google-api-python-client for the API.

Sign-in is the "Desktop app" OAuth flow from Google's Calendar quickstart:
InstalledAppFlow.run_local_server, which opens the browser and listens once on a loopback
address (http://127.0.0.1:<random port>) for the redirect. The library adds PKCE (a random
code_verifier with an S256 code_challenge) and access_type=offline (a refresh token). Installed
apps "cannot keep secrets", so the client secret isn't treated as one, but the client and the
tokens are still stored encrypted with DPAPI and never logged.

Scopes: read-only to start (calendar list + events). Adding events uses calendar.events.owned,
the narrowest scope that can create events on the user's own calendars. Installed apps can't add
scopes incrementally, so allowing it means connecting again with the extra scope.
"""

from __future__ import annotations

import json
import logging
import socket

log = logging.getLogger(__name__)

SCOPES_READ = [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]
SCOPE_CREATE = "https://www.googleapis.com/auth/calendar.events.owned"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CONNECT_TIMEOUT_S = 300
SUCCESS_PAGE = ("Wisp is connected to Google Calendar. You can close this tab and go back to "
                "Wisp.")


class CalendarError(Exception):
    """Something went wrong talking to Google; the message is fit to show the user."""


class AuthExpired(CalendarError):
    """The sign-in no longer works (expired, revoked): the user must connect again."""


class MissingPermission(CalendarError):
    """The token lacks a scope (adding events wasn't allowed when connecting)."""


class SyncTokenGone(CalendarError):
    """410 GONE: the sync token is no longer valid; wipe the calendar and sync it fully."""


def scopes_for(allow_create: bool) -> list[str]:
    return SCOPES_READ + ([SCOPE_CREATE] if allow_create else [])


def parse_client(text: str) -> dict:
    """Check an OAuth client JSON downloaded from the Google Cloud console (Clients → Desktop
    app → Download JSON). Returns the config for InstalledAppFlow.from_client_config."""
    try:
        config = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise CalendarError("That isn't a client JSON file from the Google Cloud console.") \
            from exc
    if not isinstance(config, dict):
        raise CalendarError("That isn't a client JSON file from the Google Cloud console.")
    if "web" in config:
        raise CalendarError("That's a Web application client. Create a client of type "
                            "Desktop app instead (Google Auth platform → Clients).")
    installed = config.get("installed")
    needed = ("client_id", "client_secret", "auth_uri", "token_uri")
    if not isinstance(installed, dict) or not all(installed.get(key) for key in needed):
        raise CalendarError("The file is missing the Desktop app client details "
                            "(client_id, client_secret, auth_uri, token_uri).")
    return {"installed": {key: installed[key] for key in (*needed, "redirect_uris")
                          if key in installed}}


def client_label(config: dict) -> str:
    client_id = config["installed"]["client_id"]
    return client_id.split("-")[0] + "…apps.googleusercontent.com" if "-" in client_id \
        else client_id


def authorize(config: dict, scopes: list[str], open_browser: bool = True,
              timeout_s: int = CONNECT_TIMEOUT_S) -> dict:
    """Run the browser sign-in and return the credentials as a dict (authorized-user JSON).
    Blocks until the redirect arrives or ``timeout_s`` passes: run it off the UI thread."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_config(config, scopes)
    try:
        credentials = flow.run_local_server(
            host="127.0.0.1", port=0, open_browser=open_browser,
            authorization_prompt_message=None, success_message=SUCCESS_PAGE,
            timeout_seconds=timeout_s, prompt="consent")
    except Exception as exc:
        name = type(exc).__name__
        if name == "WSGITimeoutError":
            raise CalendarError("Google sign-in timed out. Try Connect again.") from exc
        if isinstance(exc, (OSError, socket.error)):
            raise CalendarError(f"Couldn't wait for Google's sign-in on this PC ({exc}).") \
                from exc
        raise CalendarError(f"Google sign-in didn't finish ({name}).") from exc
    return json.loads(credentials.to_json())


def credentials_from(info: dict):
    from google.oauth2.credentials import Credentials

    return Credentials.from_authorized_user_info(info, info.get("scopes"))


def granted(info: dict | None) -> set[str]:
    if not info:
        return set()
    return set(info.get("scopes") or [])


def revoke(info: dict) -> bool:
    """Revoke the refresh token (that also revokes its access tokens)."""
    import requests

    token = info.get("refresh_token") or info.get("token")
    if not token:
        return False
    try:
        response = requests.post(REVOKE_URL, params={"token": token}, timeout=15,
                                 headers={"content-type": "application/x-www-form-urlencoded"})
        return response.status_code == 200
    except requests.RequestException as exc:
        log.info("Token revocation failed: %s", type(exc).__name__)
        return False


class GoogleCalendarApi:
    """The few Calendar API calls Wisp makes. Wraps google-api-python-client; Google's errors
    become AuthExpired, MissingPermission, SyncTokenGone or CalendarError. Credentials refresh
    themselves (google-auth); ``info`` returns them, possibly refreshed, for saving."""

    def __init__(self, info: dict):
        from googleapiclient.discovery import build

        self._credentials = credentials_from(info)
        self._service = build("calendar", "v3", credentials=self._credentials,
                              cache_discovery=False, static_discovery=True)

    def info(self) -> dict:
        return json.loads(self._credentials.to_json())

    def _run(self, request) -> dict:
        from google.auth.exceptions import RefreshError
        from googleapiclient.errors import HttpError

        try:
            return request.execute()
        except RefreshError as exc:
            raise AuthExpired("Google sign-in expired or was revoked. Connect again in "
                              "Settings → Accounts.") from exc
        except HttpError as exc:
            status = exc.status_code
            if status == 410:
                raise SyncTokenGone("Sync token expired") from exc
            if status == 401:
                raise AuthExpired("Google sign-in expired. Connect again in Settings → "
                                  "Accounts.") from exc
            if status == 403 and "insufficient" in str(exc).lower():
                raise MissingPermission("Wisp isn't allowed to add events. Tick “Let Wisp add "
                                        "events” in Settings → Accounts and connect again.") \
                    from exc
            raise CalendarError(f"Google Calendar error {status}.") from exc
        except OSError as exc:
            raise CalendarError(f"Couldn't reach Google Calendar ({type(exc).__name__}).") \
                from exc

    def calendars(self) -> list[dict]:
        items, page = [], None
        while True:
            response = self._run(self._service.calendarList().list(pageToken=page,
                                                                    maxResults=250))
            items.extend(response.get("items", []))
            page = response.get("nextPageToken")
            if not page:
                return items

    def events_page(self, calendar_id: str, sync_token: str | None = None,
                    page_token: str | None = None, time_min: str | None = None,
                    time_max: str | None = None) -> dict:
        # The same parameters on full and incremental syncs (Google's sync guide); timeMin and
        # timeMax only on full syncs: events.list doesn't combine them with syncToken.
        args = {"calendarId": calendar_id, "singleEvents": True, "showDeleted": True,
                "maxResults": 2500, "pageToken": page_token}
        if sync_token:
            args["syncToken"] = sync_token
        else:
            args.update({"timeMin": time_min, "timeMax": time_max})
        return self._run(self._service.events().list(**args))

    def insert(self, calendar_id: str, body: dict) -> dict:
        return self._run(self._service.events().insert(calendarId=calendar_id, body=body))
