"""The phone link's web server (D-051): a short-lived plain-HTTP page on the home network.

Security rules, all enforced here:

* It listens only on the one Private-network address it is given (wisp.phone.network), on a
  random free port; never on all interfaces.
* Every URL starts with a 256-bit random token (secrets.token_urlsafe(32)), compared in constant
  time; anything else gets a bare 404. The token lives only as long as this server.
* The first device to use the token owns the link; any other address gets 403.
* It stops by itself after ``lifetime_s`` (10 minutes) or when stopped from Wisp.
* Every upload is asked for first (``POST ask`` with its name and size) and waits for Accept on
  the PC (``on_upload``). Only an accepted upload may then be sent (``PUT upload/<id>``, once,
  from the same device, with exactly the size asked for, within a minute). Declined, unanswered
  after ``approve_timeout_s``, over the size limit or cut short: nothing is kept.
* Received names go through wisp.files.names.sanitize (no folders, no path tricks) and never
  overwrite: they land as "name (2).ext" in the Downloads\\Wisp folder. Data is written to a
  ".part" file first and renamed only when complete.
* Request lines (which contain the token) are never logged.
"""

from __future__ import annotations

import hmac
import html
import json
import logging
import secrets
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from wisp.files import names

log = logging.getLogger(__name__)

LIFETIME_S = 600
APPROVE_TIMEOUT_S = 120
MAX_PENDING = 3
SEND_WITHIN_S = 60  # an accepted upload must start within this time
MAX_ASK_BYTES = 4096
DISCARD_BYTES = 64 * 1024  # a refused PUT's body up to this size is read and dropped
CHUNK = 256 * 1024


@dataclass
class Offer:
    id: int
    path: Path

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class Upload:
    """One incoming file, waiting for the person's decision on the PC."""

    id: int
    name: str  # sanitised
    size: int
    client: str
    decision: bool | None = None
    decided_at: float = 0.0
    used: bool = False
    saved: Path | None = None
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def decide(self, accept: bool) -> None:
        if self.decision is None:
            self.decision = accept
            self.decided_at = time.monotonic()
        self._event.set()

    def wait(self, timeout: float) -> bool | None:
        self._event.wait(timeout)
        return self.decision


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "bytes" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class PhoneServer:
    def __init__(self, host: str, inbox: Path, max_bytes: int,
                 on_upload: Callable[[Upload], None],
                 on_received: Callable[[Upload], None] = lambda _u: None,
                 on_stopped: Callable[[str], None] = lambda _r: None,
                 lifetime_s: float = LIFETIME_S, approve_timeout_s: float = APPROVE_TIMEOUT_S,
                 port: int = 0) -> None:
        self.host = host
        self.inbox = inbox
        self.max_bytes = max_bytes
        self.on_upload = on_upload
        self.on_received = on_received
        self.on_stopped = on_stopped
        self.approve_timeout_s = approve_timeout_s
        self.token = secrets.token_urlsafe(32)
        self.nonce = secrets.token_urlsafe(16)
        self.offers: list[Offer] = []
        self.client: str | None = None
        self.pending: dict[int, Upload] = {}  # asked, not yet decided
        self.accepted: dict[int, Upload] = {}  # accepted, not yet sent
        self._ids = iter(range(1, 1_000_000))
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self.stop_reason = ""
        self.lifetime_s = lifetime_s
        self.started = 0.0
        self._httpd = _Server((host, port), _Handler)
        self._httpd.owner = self
        self._thread: threading.Thread | None = None
        self._timer: threading.Timer | None = None

    # ----- lifecycle ----------------------------------------------------------------------------
    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/{self.token}/"

    @property
    def running(self) -> bool:
        return self._thread is not None and not self._stopped.is_set()

    def remaining_s(self) -> float:
        return max(0.0, self.lifetime_s - (time.monotonic() - self.started)) if self.started else 0

    def start(self) -> None:
        self.started = time.monotonic()
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="wisp-phone",
                                        daemon=True)
        self._thread.start()
        self._timer = threading.Timer(self.lifetime_s, self.stop, args=("timeout",))
        self._timer.daemon = True
        self._timer.start()

    def stop(self, reason: str = "closed") -> None:
        """Stop serving; waiting uploads are declined. Safe to call more than once."""
        with self._lock:
            if self._stopped.is_set():
                return
            self._stopped.set()
            self.stop_reason = reason
            waiting = list(self.pending.values())
        if self._timer is not None:
            self._timer.cancel()
        for upload in waiting:
            upload.decide(False)
        if self._thread is not None:
            self._httpd.shutdown()
        self._httpd.server_close()
        self.on_stopped(reason)

    def offer(self, paths: list[Path]) -> list[Offer]:
        with self._lock:
            known = {offer.path for offer in self.offers}
            new = [Offer(next(self._ids), path) for path in paths
                   if path.is_file() and path not in known]
            self.offers.extend(new)
        return new

    # ----- checks used by the handler -------------------------------------------------------------
    def token_ok(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.encode(), self.token.encode())

    def claim(self, client: str) -> bool:
        """The first device to use the link owns it."""
        with self._lock:
            if self.client is None:
                self.client = client
            return self.client == client

    def new_upload(self, raw_name: str, size: int, client: str) -> Upload | None:
        with self._lock:
            if len(self.pending) >= MAX_PENDING or self._stopped.is_set():
                return None
            upload = Upload(next(self._ids), names.sanitize(raw_name), size, client)
            self.pending[upload.id] = upload
        return upload

    def settle(self, upload: Upload) -> None:
        """The person answered (or didn't): an accepted upload may now be sent, once."""
        with self._lock:
            self.pending.pop(upload.id, None)
            if upload.decision and not self._stopped.is_set():
                self.accepted[upload.id] = upload

    def take_accepted(self, upload_id: int, client: str, size: int) -> Upload | None:
        """The accepted upload for a PUT: same device, same size, in time, only once."""
        with self._lock:
            upload = self.accepted.pop(upload_id, None)
        if upload is None or upload.client != client or upload.size != size or upload.used:
            return None
        if time.monotonic() - upload.decided_at > SEND_WITHIN_S:
            return None
        upload.used = True
        return upload


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    owner: PhoneServer


class _Handler(BaseHTTPRequestHandler):
    server: _Server
    timeout = 30  # seconds without data from the phone before a connection is dropped
    server_version = "Wisp"
    sys_version = ""

    # Never log request lines: they carry the token.
    def log_message(self, format: str, *args) -> None:
        return

    def log_request(self, code="-", size="-") -> None:
        log.debug("Phone link: %s → %s", self.command, code)

    # ----- routing ------------------------------------------------------------------------------
    def _route(self) -> list[str] | None:
        owner = self.server.owner
        parts = urllib.parse.urlsplit(self.path).path.split("/")
        if len(parts) < 3 or not owner.token_ok(parts[1]):
            self._plain(HTTPStatus.NOT_FOUND, "Not found.")
            return None
        if not owner.claim(self.client_address[0]):
            self._plain(HTTPStatus.FORBIDDEN, "This link is already in use by another device.")
            return None
        return parts[2:]

    def do_GET(self) -> None:
        route = self._route()
        if route is None:
            return
        if route == [""]:
            self._page()
        elif len(route) == 2 and route[0] == "file" and route[1].isdigit():
            self._send_file(int(route[1]))
        else:
            self._plain(HTTPStatus.NOT_FOUND, "Not found.")

    def do_POST(self) -> None:
        route = self._route()
        if route is None:
            return
        if route != ["ask"]:
            self.close_connection = True
            self._plain(HTTPStatus.NOT_FOUND, "Not found.")
            return
        self._ask()

    def do_PUT(self) -> None:
        route = self._route()
        if route is None:
            return
        if len(route) != 2 or route[0] != "upload" or not route[1].isdigit():
            self.close_connection = True
            self._plain(HTTPStatus.NOT_FOUND, "Not found.")
            return
        self._receive(int(route[1]))

    # ----- responses ----------------------------------------------------------------------------
    def _headers(self, status: HTTPStatus, content_type: str, length: int,
                 extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")  # the token never leaves in a Referer
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _plain(self, status: HTTPStatus, text: str) -> None:
        body = text.encode("utf-8")
        self._headers(status, "text/plain; charset=utf-8", len(body))
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self._headers(status, "application/json", len(body))
        self.wfile.write(body)

    def _page(self) -> None:
        owner = self.server.owner
        body = page_html(owner).encode("utf-8")
        csp = (f"default-src 'none'; script-src 'nonce-{owner.nonce}'; style-src 'unsafe-inline';"
               " connect-src 'self'; img-src data:; form-action 'none'; base-uri 'none'")
        self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body),
                      {"Content-Security-Policy": csp})
        self.wfile.write(body)

    def _send_file(self, offer_id: int) -> None:
        owner = self.server.owner
        offer = next((o for o in owner.offers if o.id == offer_id), None)
        if offer is None or not offer.path.is_file():
            self._plain(HTTPStatus.NOT_FOUND, "That file isn't shared any more.")
            return
        size = offer.path.stat().st_size
        quoted = urllib.parse.quote(offer.name)
        self._headers(HTTPStatus.OK, "application/octet-stream", size,
                      {"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"})
        with offer.path.open("rb") as source:
            while chunk := source.read(CHUNK):
                if owner._stopped.is_set():
                    self.close_connection = True
                    return
                self.wfile.write(chunk)

    def _length(self) -> int | None:
        text = self.headers.get("Content-Length")
        return int(text) if text is not None and text.isdigit() else None

    def _ask(self) -> None:
        """POST ask {"name", "size"}: wait for the person's answer on the PC."""
        owner = self.server.owner
        length = self._length()
        if length is None or length > MAX_ASK_BYTES:
            self.close_connection = True
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            raw_name, size = str(data.get("name", "")), int(data.get("size", -1))
        except (ValueError, TypeError, AttributeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return
        if size < 0:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return
        if size > owner.max_bytes:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                       {"error": "too_large", "limit": human_size(owner.max_bytes)})
            return
        upload = owner.new_upload(raw_name, size, self.client_address[0])
        if upload is None:
            self._json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "busy"})
            return
        try:
            owner.on_upload(upload)
            decision = upload.wait(owner.approve_timeout_s)
            if decision is None:
                upload.decide(False)
        finally:
            owner.settle(upload)
        if owner._stopped.is_set():
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "stopped"})
        elif decision is None:
            self._json(HTTPStatus.REQUEST_TIMEOUT, {"error": "no_answer"})
        elif not decision:
            self._json(HTTPStatus.FORBIDDEN, {"error": "declined"})
        else:
            self._json(HTTPStatus.OK, {"id": upload.id, "name": upload.name})

    def _receive(self, upload_id: int) -> None:
        """PUT upload/<id>: the data of an accepted upload."""
        owner = self.server.owner
        self.close_connection = True  # one upload per connection; nothing left half-read
        length = self._length()
        upload = None if length is None else owner.take_accepted(
            upload_id, self.client_address[0], length)
        if upload is None:
            if length is not None and length <= DISCARD_BYTES:
                self.rfile.read(length)  # read a small body so the phone sees the answer
            self._json(HTTPStatus.FORBIDDEN, {"error": "not_accepted"})
            return
        self._store(upload)

    def _store(self, upload: Upload) -> None:
        owner = self.server.owner
        owner.inbox.mkdir(parents=True, exist_ok=True)
        part = owner.inbox / f".{secrets.token_hex(8)}.part"
        received = 0
        try:
            with part.open("wb") as target:
                while received < upload.size:
                    chunk = self.rfile.read(min(CHUNK, upload.size - received))
                    if not chunk or owner._stopped.is_set():
                        break
                    target.write(chunk)
                    received += len(chunk)
            if received != upload.size:
                part.unlink(missing_ok=True)  # our own partial file, never the person's
                self._json(HTTPStatus.BAD_REQUEST, {"error": "incomplete"})
                return
            final = names.unique(owner.inbox, upload.name)
            part.rename(final)
        except OSError:
            part.unlink(missing_ok=True)
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "disk"})
            return
        upload.saved = final
        owner.on_received(upload)
        self._json(HTTPStatus.OK, {"saved": final.name})


def page_html(owner: PhoneServer) -> str:
    """The phone's page: files offered by the PC, and a picker to send files to the PC."""
    rows = "".join(
        f'<li><a href="file/{offer.id}" download>{html.escape(offer.name)}</a>'
        f'<span>{human_size(offer.path.stat().st_size) if offer.path.exists() else ""}</span></li>'
        for offer in owner.offers)
    offered = (f"<h2>From your PC</h2><ul>{rows}</ul>" if rows else "")
    limit = html.escape(human_size(owner.max_bytes))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Wisp</title>
<style>
body {{ font: 16px/1.45 system-ui, sans-serif; margin: 0; padding: 20px; background: #111;
       color: #eee; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }} h2 {{ font-size: 17px; margin: 24px 0 8px; }}
p {{ color: #aaa; margin: 4px 0; }} ul {{ list-style: none; padding: 0; margin: 0; }}
li {{ display: flex; justify-content: space-between; gap: 12px; padding: 12px 0;
     border-bottom: 1px solid #2a2a2a; }}
a {{ color: #a99bff; word-break: break-all; }} span {{ color: #888; white-space: nowrap; }}
label {{ display: block; margin-top: 8px; padding: 14px; text-align: center; border-radius: 10px;
        background: #7c5cff; color: #fff; font-weight: 600; }}
input {{ display: none; }}
</style></head><body>
<h1>Wisp</h1><p>Connected to your PC over your home Wi-Fi.</p>
{offered}
<h2>Send to your PC</h2>
<p>Each file needs a click to accept on the PC. Up to {limit} per file.</p>
<label>Choose files<input id="pick" type="file" multiple></label>
<ul id="sent"></ul>
<script nonce="{owner.nonce}">
const limit = {owner.max_bytes};
const messages = {{403: "Declined on the PC", 408: "Not accepted in time",
  413: "Too large (limit {limit})", 429: "The PC is busy, try again",
  503: "Sharing has stopped"}};
const list = document.getElementById("sent");
async function send(file) {{
  const row = document.createElement("li");
  const name = document.createElement("a"); name.textContent = file.name;
  const state = document.createElement("span");
  row.append(name, state); list.append(row);
  if (file.size > limit) {{ state.textContent = messages[413]; return; }}
  try {{
    state.textContent = "Waiting for the PC to accept…";
    const ask = await fetch("ask", {{method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{name: file.name, size: file.size}})}});
    if (ask.status !== 200) {{
      state.textContent = messages[ask.status] || ("Failed (" + ask.status + ")"); return;
    }}
    const answer = await ask.json();
    state.textContent = "Sending…";
    const put = await fetch("upload/" + answer.id, {{method: "PUT", body: file}});
    state.textContent = put.status === 200 ? "Saved on the PC"
      : (messages[put.status] || ("Failed (" + put.status + ")"));
  }} catch (error) {{ state.textContent = "Connection lost"; }}
}}
document.getElementById("pick").addEventListener("change", async (event) => {{
  for (const file of event.target.files) {{ await send(file); }}
  event.target.value = "";
}});
</script></body></html>"""
