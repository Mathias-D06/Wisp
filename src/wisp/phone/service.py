"""The phone link as the rest of Wisp sees it (D-051): start it (optionally offering files to the
phone), see what the phone wants to send, accept or decline each file, stop it.

The server runs on its own threads; everything it reports reaches the Qt thread through
signals. While it runs, ``changed`` fires every second so the countdown and the island's
"Phone link" activity stay current.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from wisp.phone import network
from wisp.phone.server import LIFETIME_S, PhoneServer, Upload

log = logging.getLogger(__name__)


class PhoneLink(QObject):
    changed = Signal()
    upload_requested = Signal(object)  # Upload, waiting for accept/decline
    received = Signal(object)  # Upload, saved
    _upload = Signal(object)
    _received = Signal(object)
    _stopped = Signal(str)

    def __init__(self, inbox: Callable[[], Path], max_bytes: Callable[[], int],
                 address: Callable[[], network.LanAddress] = network.lan_address,
                 server_factory=PhoneServer, wall: Callable[[], float] = time.time,
                 lifetime_s: float = LIFETIME_S) -> None:
        super().__init__()
        self._inbox = inbox
        self._max_bytes = max_bytes
        self._address = address
        self._factory = server_factory
        self._wall = wall
        self.lifetime_s = lifetime_s
        self.server: PhoneServer | None = None
        self.network = ""
        self.error = ""
        self.waiting: list[Upload] = []
        self.stop_reason = ""
        self.ends_at = 0.0  # wall clock, for the island's countdown
        self._tick = QTimer(self, interval=1000)
        self._tick.timeout.connect(self._update)
        self._upload.connect(self._on_upload)
        self._received.connect(self._on_received)
        self._stopped.connect(self._on_stopped)

    # ----- state ---------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.server is not None and self.server.running

    @property
    def url(self) -> str:
        return self.server.url if self.server is not None else ""

    def remaining_s(self) -> float:
        return self.server.remaining_s() if self.server is not None else 0.0

    def offers(self) -> list[Path]:
        return [offer.path for offer in self.server.offers] if self.server is not None else []

    # ----- control -------------------------------------------------------------------------
    def start(self, paths: list[Path] | None = None) -> bool:
        """Start (or, if running, add ``paths`` to what the phone can download). False with
        ``error`` set when no Private network is available or the port can't be opened."""
        if self.running:
            if paths:
                self.server.offer(paths)
                self.changed.emit()
            return True
        try:
            address = self._address()
            server = self._factory(address.ip, self._inbox(), self._max_bytes(),
                                   on_upload=self._upload.emit, on_received=self._received.emit,
                                   on_stopped=self._stopped.emit, lifetime_s=self.lifetime_s)
        except network.NotAllowed as exc:
            self.error = str(exc)
            self.changed.emit()
            return False
        except OSError as exc:
            self.error = f"Couldn't open the link on this PC ({exc.strerror or exc})."
            self.changed.emit()
            return False
        except Exception as exc:  # COM / WinRT failures while reading the network state
            log.warning("Phone link: network check failed: %s", type(exc).__name__)
            self.error = "Couldn't check which network this PC is on."
            self.changed.emit()
            return False
        self.server, self.network, self.error, self.stop_reason = server, address.network, "", ""
        if paths:
            server.offer(paths)
        server.start()
        self.ends_at = self._wall() + self.lifetime_s
        self._tick.start()
        log.info("Phone link started on a Private network")
        self.changed.emit()
        return True

    def stop(self) -> None:
        if self.server is not None:
            self.server.stop("closed")

    def accept(self, upload: Upload) -> None:
        upload.decide(True)
        self._forget(upload)

    def decline(self, upload: Upload) -> None:
        upload.decide(False)
        self._forget(upload)

    # ----- server events (queued to the Qt thread) ----------------------------------------
    def _forget(self, upload: Upload) -> None:
        if upload in self.waiting:
            self.waiting.remove(upload)
        self.changed.emit()

    def _on_upload(self, upload: Upload) -> None:
        self.waiting.append(upload)
        self.upload_requested.emit(upload)
        self.changed.emit()

    def _on_received(self, upload: Upload) -> None:
        self.received.emit(upload)
        self.changed.emit()

    def _on_stopped(self, reason: str) -> None:
        self._tick.stop()
        self.stop_reason = reason
        self.waiting.clear()
        self.server = None
        self.ends_at = 0.0
        log.info("Phone link stopped (%s)", reason)
        self.changed.emit()

    def _update(self) -> None:
        self.waiting = [upload for upload in self.waiting if upload.decision is None]
        self.changed.emit()
