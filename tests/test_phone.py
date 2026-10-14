"""D-051: the phone link. Which network it may use (Private only), and its server: the token, the
device that owns the link, every upload approved on the PC first, the size limit, safe names,
the 10-minute stop, and nothing logged with the token. The server listens on 127.0.0.1 here;
the app only ever gives it a Private-network address."""

from __future__ import annotations

import http.client
import json
import logging
import threading
import time
import urllib.parse

import pytest

from wisp.phone import network
from wisp.phone.network import Connection, Host, NotAllowed, choose
from wisp.phone.server import PhoneServer

HOME = Connection("A1", True, network.PRIVATE, "Home")
CAFE = Connection("B2", True, network.PUBLIC, "Cafe")
WORK = Connection("C3", True, network.DOMAIN, "corp")


# ----- the network rule ---------------------------------------------------------------------------
def test_only_a_private_network_address_is_used():
    hosts = [Host("B2", "10.0.0.5"), Host("A1", "fe80::1"), Host("A1", "192.168.1.20")]
    assert choose([CAFE, HOME], hosts) == network.LanAddress("192.168.1.20", "Home")


@pytest.mark.parametrize("connections, hosts, message", [
    ([CAFE], [Host("B2", "10.0.0.5")], "Public"),
    ([WORK], [Host("C3", "10.1.0.5")], "work"),
    ([Connection("A1", False, network.PRIVATE, "Home")], [Host("A1", "192.168.1.20")],
     "isn't connected"),
    ([HOME], [Host("A1", "127.0.0.1"), Host("A1", "8.8.8.8")], "isn't connected"),
    ([], [], "isn't connected"),
])
def test_never_on_a_public_or_work_network(connections, hosts, message):
    with pytest.raises(NotAllowed, match=message):
        choose(connections, hosts)


# ----- the server ---------------------------------------------------------------------------------
class Phone:
    """A minimal HTTP client standing in for the phone's browser."""

    def __init__(self, server: PhoneServer, token: str | None = None):
        self.server = server
        self.prefix = f"/{token or server.token}/"

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict | None = None) -> tuple[int, bytes, dict]:
        connection = http.client.HTTPConnection(self.server.host, self.server.port, timeout=10)
        try:
            connection.request(method, self.prefix + path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def ask(self, name: str, size: int) -> tuple[int, dict]:
        status, body, _ = self.request("POST", "ask", json.dumps({"name": name, "size": size})
                                       .encode(), {"Content-Type": "application/json"})
        return status, json.loads(body or b"{}")

    def send(self, upload_id: int, data: bytes) -> int:
        return self.request("PUT", f"upload/{upload_id}", data)[0]


@pytest.fixture
def make_server(tmp_path):
    servers = []

    def make(decide=True, **options) -> tuple[PhoneServer, list]:
        asked = []

        def on_upload(upload):
            asked.append(upload)
            if decide is not None:
                threading.Timer(0.05, upload.decide, args=(decide,)).start()

        options.setdefault("lifetime_s", 30)
        server = PhoneServer("127.0.0.1", tmp_path / "Downloads" / "Wisp",
                             options.pop("max_bytes", 1000), on_upload, **options)
        server.start()
        servers.append(server)
        return server, asked

    yield make
    for server in servers:
        server.stop()


def test_the_link_needs_the_full_token(make_server):
    server, _ = make_server()
    status, body, headers = Phone(server).request("GET", "")
    assert status == 200 and b"Send to your PC" in body
    assert headers["Referrer-Policy"] == "no-referrer"
    assert f"'nonce-{server.nonce}'" in headers["Content-Security-Policy"]
    assert len(server.token) >= 43  # 32 random bytes
    for wrong in ("x" * len(server.token), server.token[:-1], server.token + "x", ""):
        assert Phone(server, wrong or "-").request("GET", "")[0] == 404
    assert Phone(server).request("GET", "../etc/passwd")[0] == 404


def test_the_first_device_owns_the_link(make_server):
    server, _ = make_server()
    assert server.claim("192.168.1.30") and server.claim("192.168.1.30")
    assert not server.claim("192.168.1.31")
    assert Phone(server).request("GET", "")[0] == 403  # this test client is another address


def test_an_accepted_upload_lands_safely_in_downloads_wisp(make_server):
    server, asked = make_server(decide=True)
    phone = Phone(server)
    status, answer = phone.ask("../../evil name?.txt", 5)
    assert status == 200 and answer["name"] == "evil name.txt"
    assert asked[0].name == "evil name.txt" and asked[0].size == 5
    assert phone.send(answer["id"], b"hello") == 200
    assert phone.send(answer["id"], b"hello") == 403  # only once
    saved = server.inbox / "evil name.txt"
    assert saved.read_bytes() == b"hello" and asked[0].saved == saved
    status, again = phone.ask("evil name.txt", 3)
    phone.send(again["id"], b"abc")
    assert (server.inbox / "evil name (2).txt").read_bytes() == b"abc"  # no overwrite
    assert not list(server.inbox.glob("*.part")) and not list(server.inbox.glob(".*"))


def test_declined_unanswered_and_too_large_uploads_keep_nothing(make_server):
    server, asked = make_server(decide=False, approve_timeout_s=0.5)
    phone = Phone(server)
    status, _ = phone.ask("secret.txt", 5)
    assert status == 403
    assert phone.send(1, b"hello") == 403  # never accepted
    quiet, quiet_asked = make_server(decide=None, approve_timeout_s=0.3)
    started = time.monotonic()
    assert Phone(quiet).ask("slow.txt", 5)[0] == 408
    assert time.monotonic() - started < 3 and quiet_asked[0].decision is False
    status, answer = phone.ask("big.iso", 1001)  # over the 1000-byte limit
    assert status == 413 and "limit" in answer and len(asked) == 1  # never asked
    for inbox in (server.inbox, quiet.inbox):
        assert not inbox.exists() or not any(inbox.iterdir())


def test_an_accepted_upload_must_match_what_was_asked(make_server):
    server, _ = make_server(decide=True)
    phone = Phone(server)
    _, answer = phone.ask("photo.jpg", 5)
    assert phone.send(answer["id"], b"more than five") == 403  # size differs from the ask
    _, answer = phone.ask("photo.jpg", 5)
    assert phone.send(answer["id"] + 99, b"hello") == 403  # unknown id


def test_a_cut_short_upload_leaves_no_file(make_server):
    server, _ = make_server(decide=True)
    _, answer = Phone(server).ask("video.mp4", 100)
    connection = http.client.HTTPConnection(server.host, server.port, timeout=10)
    connection.putrequest("PUT", f"/{server.token}/upload/{answer['id']}")
    connection.putheader("Content-Length", "100")
    connection.endheaders()
    connection.send(b"only twenty bytes...")
    connection.close()  # the phone went away
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and (server.inbox.exists() and any(server.inbox.iterdir())):
        time.sleep(0.05)
    time.sleep(0.2)
    assert not server.inbox.exists() or not any(server.inbox.iterdir())


def test_the_phone_downloads_offered_files(make_server, tmp_path):
    server, _ = make_server()
    report = tmp_path / "Q3 report.pdf"
    report.write_bytes(b"%PDF-1.7")
    [offer] = server.offer([report, tmp_path / "missing.pdf"])
    status, body, headers = Phone(server).request("GET", "")
    assert b"Q3 report.pdf" in body
    status, body, headers = Phone(server).request("GET", f"file/{offer.id}")
    assert status == 200 and body == b"%PDF-1.7"
    assert headers["Content-Disposition"] == "attachment; filename*=UTF-8''Q3%20report.pdf"
    assert Phone(server).request("GET", "file/999")[0] == 404


def test_it_stops_by_itself_and_declines_waiting_uploads(make_server):
    stopped = []
    server, asked = make_server(decide=None, lifetime_s=0.6, on_stopped=stopped.append)
    status = []
    worker = threading.Thread(target=lambda: status.append(Phone(server).ask("a.txt", 1)[0]))
    worker.start()
    worker.join(5)
    deadline = time.monotonic() + 3  # shutdown() waits for the serve loop's next poll
    while not stopped and time.monotonic() < deadline:
        time.sleep(0.05)
    assert stopped == ["timeout"] and not server.running and status == [503]
    assert asked[0].decision is False
    with pytest.raises(OSError):
        Phone(server).request("GET", "")


def test_request_lines_with_the_token_are_never_logged(make_server, caplog):
    caplog.set_level(logging.DEBUG)
    server, _ = make_server(decide=True)
    Phone(server).request("GET", "")
    Phone(server, "wrong").request("GET", "")
    assert server.token not in caplog.text and "GET" in caplog.text


# ----- the Qt service -----------------------------------------------------------------------------
def test_phone_link_service_start_accept_and_stop(qtbot, tmp_path):
    from wisp.phone.service import PhoneLink

    link = PhoneLink(lambda: tmp_path / "Wisp", lambda: 1000,
                     address=lambda: network.LanAddress("127.0.0.1", "Home"),
                     wall=lambda: 5000.0, lifetime_s=30)
    report = tmp_path / "report.pdf"
    report.write_text("x")
    with qtbot.waitSignal(link.changed):
        assert link.start([report])
    assert link.running and link.url.startswith("http://127.0.0.1:") and link.ends_at == 5030.0
    assert link.offers() == [report] and link.network == "Home"
    phone = Phone(link.server)
    result = []
    worker = threading.Thread(target=lambda: result.append(phone.ask("note.txt", 2)))
    with qtbot.waitSignal(link.upload_requested, timeout=5000) as request:
        worker.start()
    upload = request.args[0]
    assert link.waiting == [upload]
    link.accept(upload)
    worker.join(5)
    assert result[0][0] == 200 and link.waiting == []
    with qtbot.waitSignal(link.received, timeout=5000):
        assert phone.send(result[0][1]["id"], b"hi") == 200
    with qtbot.waitSignal(link.changed):
        link.stop()
    assert not link.running and link.stop_reason == "closed" and link.ends_at == 0.0


def test_phone_link_explains_a_public_network(qtbot, tmp_path):
    from wisp.phone.service import PhoneLink

    def public():
        raise NotAllowed("“Cafe” is set up as a Public network")

    link = PhoneLink(lambda: tmp_path, lambda: 1000, address=public)
    assert not link.start() and not link.running and "Public" in link.error


# ----- the QR code --------------------------------------------------------------------------------
def test_qr_code_has_its_quiet_zone(qtbot):
    from wisp.phone import qr

    url = "http://192.168.1.20:51234/" + "t" * 43 + "/"
    rows = qr.modules(url)
    assert len(rows) == len(rows[0]) and len(rows) >= 29
    assert all(value == 0 for row in rows[:4] + rows[-4:] for value in row)
    assert all(row[:4] == [0] * 4 and row[-4:] == [0] * 4 for row in rows)
    image = qr.image(url, 132)
    assert image.width() == 132 and image.pixelColor(2, 2).name() == "#ffffff"
    assert urllib.parse.urlsplit(url).scheme == "http"


def test_file_names_on_the_phone_page_are_escaped(make_server, tmp_path):
    server, _ = make_server()
    odd = tmp_path / "R&D 'notes'.txt"  # Windows names can't hold < > or "
    odd.write_text("x")
    server.offer([odd])
    _, body, _ = Phone(server).request("GET", "")
    assert b"R&amp;D &#x27;notes&#x27;.txt" in body and b"R&D 'notes'" not in body
