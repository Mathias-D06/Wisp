"""``Wisp.exe --self-check [report.json]``: prove that a build (source or PyInstaller bundle) has
everything it needs — every module imports, Qt plugins, SQLite FTS5, DPAPI, PortAudio, WinRT,
UI Automation (comtypes code generation), APScheduler's SQLite job store, Pillow/mss, the Google
Calendar client, the phone link and share sheet pieces, Screen Assist's capture-to-request path
(with the real google-genai client talking to a loopback stand-in), the Gemini SDK types and the
tool declarations. Nothing touches the network (only 127.0.0.1), the user's data folder, audio
output, settings or the clipboard; data goes to a temporary folder.

Exit code 0 when every required check passes. Optional checks (audio devices, media session)
may fail on machines without that hardware and are reported only.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path

CHECKS: list[tuple[str, bool, Callable[[], str]]] = []


def check(name: str, required: bool = True):
    def register(fn: Callable[[], str]) -> Callable[[], str]:
        CHECKS.append((name, required, fn))
        return fn
    return register


@check("modules")
def _modules() -> str:
    import importlib
    import pkgutil

    import wisp

    names = sorted(m.name for m in pkgutil.walk_packages(wisp.__path__, "wisp."))
    for name in names:
        if name != "wisp.__main__":
            importlib.import_module(name)
    if len(names) < 60:
        raise RuntimeError(f"only {len(names)} modules found")
    return f"{len(names)} modules imported"


@check("qt")
def _qt() -> str:
    from PySide6.QtGui import QImage, QImageReader
    from PySide6.QtWidgets import QApplication

    from wisp.system.clipboard_monitor import image_to_png
    from wisp.ui.icons import orb_pixmap

    app = QApplication.instance() or QApplication([])
    formats = {bytes(f).decode() for f in QImageReader.supportedImageFormats()}
    missing = {"png", "jpg", "jpeg", "bmp", "ico"} - formats
    if missing:
        raise RuntimeError(f"Qt image plugins missing: {sorted(missing)}")
    png = image_to_png(orb_pixmap(64, "#7c5cff").toImage())
    if QImage.fromData(png, "PNG").isNull():
        raise RuntimeError("PNG round trip failed")
    from PySide6.QtCore import QSize

    from wisp.ui.iconset import ICONS, icon

    for name in ICONS:  # every bundled Lucide icon renders (QtSvg + assets present)
        if icon(name, "#ffffff").pixmap(QSize(16, 16), 1.5).isNull():
            raise RuntimeError(f"icon {name} did not render")
    return f"{app.platformName()} platform, image formats and {len(ICONS)} icons ok"


@check("sqlite_fts5")
def _sqlite() -> str:
    from wisp.db import Database
    from wisp.stores.memory import MemoryStore

    db = Database(":memory:")
    store = MemoryStore(db)
    store.add("Self-check fact about bananas")
    if not store.search("banana"):
        raise RuntimeError("FTS5 search returned nothing")
    import sqlite3

    return f"SQLite {sqlite3.sqlite_version} with FTS5"


@check("dpapi")
def _dpapi() -> str:
    from wisp.keystore import KeyStore

    store = KeyStore(Path(tempfile.mkdtemp(prefix="wisp-check-")) / "k.bin")
    secret = "AIza" + "S" * 35
    store.set(secret)
    if store.get() != secret:
        raise RuntimeError("DPAPI round trip mismatch")
    store.clear()
    return "encrypt/decrypt ok"


@check("portaudio")
def _portaudio() -> str:
    import sounddevice as sd

    apis = [api["name"] for api in sd.query_hostapis()]
    return f"PortAudio {sd.get_portaudio_version()[1]}; host APIs: {', '.join(apis)}"


@check("audio_devices", required=False)
def _audio_devices() -> str:
    from wisp.audio import devices

    mics, speakers = devices.input_devices(), devices.output_devices()
    if not mics or not speakers:
        raise RuntimeError(f"{len(mics)} microphones, {len(speakers)} speakers")
    return f"{len(mics)} microphones, {len(speakers)} speakers"


@check("images")
def _images() -> str:
    from PIL import Image

    from wisp.winapi import screen

    jpeg = screen.encode(Image.new("RGB", (2000, 1000), "#336699"))
    with Image.open(io.BytesIO(jpeg)) as img:
        size = img.size
    left, top, *_ = screen.monitors()[0]
    shot = screen.capture((left, top, left + 16, top + 16))
    return f"JPEG {size}, screen grab {shot.width}x{shot.height}"


@check("winrt")
def _winrt() -> str:
    import winrt.windows.devices.radios
    import winrt.windows.foundation.collections
    import winrt.windows.media.control as mc
    import winrt.windows.storage.streams  # noqa: F401  (album art for the island)

    async def manager() -> object:
        return await mc.GlobalSystemMediaTransportControlsSessionManager.request_async()

    found = asyncio.run(manager())
    return f"media session manager: {type(found).__name__}"


@check("uia")
def _uia() -> str:
    from wisp.winapi import uia

    client = uia.Uia.for_thread()
    root = client.auto.GetRootElement()
    return f"UI Automation root: {root.CurrentName or root.CurrentClassName}"


@check("shell_icons")
def _icons() -> str:
    from wisp.ui.island.common import _com_init
    from wisp.winapi.shell_icons import icon_png

    result: dict[str, object] = {}

    def work() -> None:
        try:
            _com_init()
            result["png"] = icon_png(os.path.join(os.environ["SYSTEMROOT"], "notepad.exe"), 32)
        except Exception as exc:
            result["error"] = exc

    worker = threading.Thread(target=work)
    worker.start()
    worker.join(30)
    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    if not result.get("png"):
        raise RuntimeError("no icon")
    return f"{len(result['png'])} byte PNG"


@check("scheduler")
def _scheduler() -> str:
    from datetime import datetime, timedelta

    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.schedulers.background import BackgroundScheduler

    folder = Path(tempfile.mkdtemp(prefix="wisp-check-"))
    scheduler = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{folder / 'jobs.sqlite3'}")})
    scheduler.start(paused=True)
    try:
        scheduler.add_job("wisp.scheduling.runner:run_scheduled_task", "date",
                          run_date=datetime.now().astimezone() + timedelta(days=1),
                          args=["self-check"], id="self-check")
        jobs = scheduler.get_jobs()
        if [j.id for j in jobs] != ["self-check"]:
            raise RuntimeError("job not stored")
    finally:
        scheduler.shutdown(wait=False)
    return "SQLAlchemy job store ok"


@check("google_calendar")
def _google_calendar() -> str:
    """The Calendar client builds from the one bundled discovery document (D-050) and the
    OAuth flow imports. Offline: a dummy token, and nothing is executed."""
    import google_auth_oauthlib.flow  # noqa: F401
    from googleapiclient import discovery_cache

    from wisp.gcal.google import SCOPES_READ, GoogleCalendarApi

    api = GoogleCalendarApi({"token": "self-check", "refresh_token": "self-check",
                             "client_id": "self-check", "client_secret": "self-check",
                             "token_uri": "https://oauth2.googleapis.com/token",
                             "scopes": list(SCOPES_READ)})
    request = api._service.events().list(calendarId="primary", syncToken="x")
    if "calendar/v3/calendars/primary/events" not in request.uri:
        raise RuntimeError(f"unexpected request URI {request.uri}")
    documents = len(list(Path(discovery_cache.DISCOVERY_DOC_DIR).glob("*.json")))
    return f"Calendar v3 client ok; {documents} discovery document(s) bundled"


@check("files_share")
def _files_share() -> str:
    """D-051 pieces, offline and without opening anything: a QR code, the network list (counts
    only: no names or addresses in the report), a WinRT StorageFile for a temporary file, and
    the share sheet's interop factory."""
    from wisp.phone import network, qr
    from wisp.winapi import share
    from wisp.winapi import winrt_abi as abi

    if len(qr.modules("http://192.168.1.2:50000/" + "t" * 43 + "/")) < 29:
        raise RuntimeError("QR code too small")
    connections = network.system_connections()
    hosts = network.system_hosts()
    sample = Path(tempfile.mkdtemp(prefix="wisp-check-")) / "share.txt"
    sample.write_text("Wisp self-check", encoding="utf-8")
    items = share.storage_items([sample])
    for item in items:
        abi.release(item)
    abi.release(abi.activation_factory(share.MANAGER_CLASS, share.IID_INTEROP))
    return (f"QR ok; {len(connections)} network connection(s), {len(hosts)} IPv4 address(es); "
            "StorageFile and share sheet interop ok")


@check("screen_assist")
def _screen_assist() -> str:
    """D-052's path as the hotkey runs it, on worker threads like the app: the real Windows
    calls choose the window (or the whole screen when none can be captured, D-056) → blocked
    windows masked → downscale → JPEG ("assist-capture"), then the real google-genai client
    sends it ("screen-assist") — to a loopback stand-in for the API (wisp.ai.loopback, D-054),
    so nothing leaves the PC. The stand-in answers "503 high demand" once, so the SDK's retry
    and Wisp's busy note run too (D-057); the answer is then read aloud the same way. The image
    stays in memory. This path failed in the build of 2026-10-15: the SDK closed a temporary
    client before sending."""
    from concurrent.futures import Future

    from PIL import Image

    from wisp.ai.loopback import GeminiLoopback
    from wisp.assist.client import GeminiAssistModel
    from wisp.assist.engine import AssistEngine, Capturer, real_window_system
    from wisp.assist.imaging import MAX_EDGE
    from wisp.assist.privacy import Blocklist

    system = real_window_system()
    source = "screen"
    if not system.desktop_available():  # a locked PC: same path, a drawn image
        system.grab = lambda box: Image.new("RGB", (box[2] - box[0], box[3] - box[1]), "#2b4c7e")
        system.desktop_available, source = (lambda: True), "drawn image (secure desktop)"
    capturer = Capturer(system, Blocklist)
    shot_future: Future = Future()

    def grab() -> None:
        try:
            shot_future.set_result(capturer.capture("window", "screen_assist", "self-check"))
        except Exception as exc:
            shot_future.set_exception(exc)

    threading.Thread(target=grab, name="assist-capture", daemon=True).start()
    shot = shot_future.result(30)
    notes: list[str] = []
    with GeminiLoopback("A self-check answer.", pcm=b"\x10\x00" * 2400) as stub:
        stub.busy["gemini-self-check"] = 1
        model = GeminiAssistModel(lambda: "self-check-key", lambda: "gemini-self-check",
                                  lambda: "gemini-self-check-tts", make_client=stub.client)
        engine = AssistEngine(model, capturer, lambda: "English (UK)")
        answer: Future = Future()

        def ask() -> None:
            try:
                exchange = engine.ask("What is on the screen?", shot=shot,
                                      on_busy=notes.append)
                answer.set_result((exchange, model.speak(exchange.answer, "Kore")))
            except Exception as exc:
                answer.set_exception(exc)

        threading.Thread(target=ask, name="screen-assist", daemon=True).start()
        exchange, speech = answer.result(60)
        sent = stub.requests[0]["body"]
        asked = stub.models_asked()
    if exchange.answer != "A self-check answer.":
        raise RuntimeError(f"unexpected answer {exchange.answer!r}")
    if asked[:2] != ["gemini-self-check"] * 2 or len(notes) != 1:
        raise RuntimeError(f"the busy answer wasn't retried ({asked}, {notes})")
    def field(item: dict, name: str, camel: str):  # the SDK writes either spelling
        return item.get(camel, item.get(name))

    inline = [field(part, "inline_data", "inlineData") or {} for content in sent["contents"]
              for part in content["parts"]]
    images = [data for data in inline if field(data, "mime_type", "mimeType") == "image/jpeg"]
    if len(images) != 1:
        raise RuntimeError(f"{len(images)} images in the request")
    import base64

    data = images[0]["data"]  # URL-safe base64, as the SDK sends it
    with Image.open(io.BytesIO(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))) as img:
        size = img.size
    if max(size) > MAX_EDGE:
        raise RuntimeError(f"image {size} not downscaled")
    config = field(sent, "generation_config", "generationConfig") or {}
    if field(config, "media_resolution", "mediaResolution") != "MEDIA_RESOLUTION_MEDIUM":
        raise RuntimeError(f"generation config {config}")
    if len(speech.pcm) != 4800 or speech.rate != 24000:
        raise RuntimeError(f"speech {len(speech.pcm)} bytes at {speech.rate} Hz")
    what = source if source != "screen" else (
        "the whole screen" if shot.target == "screen" else "a window")
    return (f"{what} → JPEG {size[0]}x{size[1]} ({len(shot.jpeg) // 1024} KB) → google-genai "
            "via loopback, a 503 retried → answer and speech ok")


@check("gemini_config")
def _gemini() -> str:
    import ssl
    from datetime import datetime

    import certifi

    from wisp.live.config import build_live_config, system_instruction
    from wisp.settings import Settings
    from wisp.tools.registry import ToolRegistry

    registry = ToolRegistry()
    from wisp.tools.builtin import (
        apps,
        calendar,
        core,
        discreet,
        files,
        memory,
        raw_input,
        schedule,
        screen,
        share,
        system,
        terminal,
        todos,
        ui,
        web,
        windows,
    )

    for module in (core, apps, windows, web, screen, ui, files, share, todos, calendar, memory,
                   system, terminal, raw_input, discreet):
        registry.register_all(module.tools())
    registry.register_all(schedule.tools(registry))
    settings = Settings()
    instruction = system_instruction(settings, [], datetime.now())
    config = build_live_config(settings, registry.declarations(settings), instruction, None)
    ssl.create_default_context(cafile=certifi.where())
    count = len(config.tools[0].function_declarations)
    return f"{count} tool declarations; CA bundle {Path(certifi.where()).name}"


def run(report: Path | None = None) -> int:
    os.environ["WISP_DATA_DIR"] = tempfile.mkdtemp(prefix="wisp-check-data-")
    import comtypes.client  # noqa: F401  (main-thread COM init, as in the app; D-021)

    from wisp import __version__

    results = []
    ok = True
    for name, required, fn in CHECKS:
        started = time.perf_counter()
        try:
            detail, passed = fn(), True
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            passed = False
            if os.environ.get("WISP_SELFCHECK_TRACE"):
                detail += "\n" + traceback.format_exc()
        ok = ok and (passed or not required)
        results.append({"check": name, "ok": passed, "required": required, "detail": detail,
                        "ms": round((time.perf_counter() - started) * 1000)})
    payload = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
               "python": sys.version.split()[0], "ok": ok, "checks": results}
    text = json.dumps(payload, indent=2)
    if report is not None:
        report.write_text(text, encoding="utf-8")
    if sys.stdout is not None:
        print(text)
    return 0 if ok else 1
