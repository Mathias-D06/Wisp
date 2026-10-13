"""Now playing + transport controls via Windows' global media sessions (WinRT).

Source: learn.microsoft.com/uwp/api/windows.media.control.globalsystemmediatransportcontrols
sessionmanager — RequestAsync, GetCurrentSession; session.TryGetMediaPropertiesAsync,
GetTimelineProperties, GetPlaybackInfo, TryTogglePlayPauseAsync, TrySkipNext/PreviousAsync.
Proven from an unpackaged desktop process on Wisp's asyncio thread
(spikes/winrt_in_loop_thread.py). Runs on the core asyncio loop; no API key needed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

log = logging.getLogger(__name__)

POLL_SECONDS = 1.0
MAX_ART_BYTES = 2_000_000


@dataclass(frozen=True)
class MediaState:
    active: bool = False
    title: str = ""
    artist: str = ""
    app: str = ""
    playing: bool = False
    position: float = 0.0  # seconds
    duration: float = 0.0  # seconds
    art: bytes = field(default=b"", repr=False)  # thumbnail image (album art), may be empty

    @property
    def progress(self) -> float:
        return min(1.0, self.position / self.duration) if self.duration > 0 else 0.0


def current_position(position_s: float, last_updated: datetime | None, playing: bool,
                     now: datetime) -> float:
    """The timeline is a snapshot; while playing, add the time since it was taken."""
    if not playing or last_updated is None:
        return position_s
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=UTC)
    elapsed = (now - last_updated).total_seconds()
    return position_s + max(0.0, elapsed)


async def read_thumbnail(reference) -> bytes:
    """The media's thumbnail (an IRandomAccessStreamReference) as image bytes; b"" when there
    is none, it is too large or it can't be read. OpenReadAsync → DataReader.LoadAsync →
    ReadBytes (learn.microsoft.com, Windows.Storage.Streams)."""
    if reference is None:
        return b""
    try:
        import winrt.windows.storage.streams as streams

        stream = await reference.open_read_async()
        size = int(stream.size)
        if not 0 < size <= MAX_ART_BYTES:
            return b""
        reader = streams.DataReader(stream.get_input_stream_at(0))
        loaded = await reader.load_async(size)
        data = bytearray(loaded)
        reader.read_bytes(data)
        return bytes(data)
    except Exception as exc:
        log.info("No album art: %s", type(exc).__name__)
        return b""


class MediaWatcher:
    def __init__(self, loop: asyncio.AbstractEventLoop, on_change: Callable[[MediaState], None]):
        self._loop = loop
        self._on_change = on_change
        self._manager = None
        self._task: asyncio.Future | None = None
        self._last = MediaState()
        self._props_cache: tuple[object, str, str] | None = None
        self.error: str | None = None

    def start(self) -> None:
        self._task = asyncio.run_coroutine_threadsafe(self._run(), self._loop)

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def _session(self):
        import winrt.windows.media.control as mc

        if self._manager is None:
            self._manager = await mc.GlobalSystemMediaTransportControlsSessionManager \
                .request_async()
        return self._manager.get_current_session()

    async def _snapshot(self) -> MediaState:
        import winrt.windows.media.control as mc

        session = await self._session()
        if session is None:
            return MediaState()
        cached = self._props_cache
        if cached is None or cached[0] is not session or not cached[1]:
            props = await session.try_get_media_properties_async()
            art = await read_thumbnail(props.thumbnail)
            self._props_cache = (session, props.title or "", props.artist or "", art)
        _, title, artist, art = self._props_cache
        info = session.get_playback_info()
        status = mc.GlobalSystemMediaTransportControlsSessionPlaybackStatus
        playing = info.playback_status == status.PLAYING
        timeline = session.get_timeline_properties()
        duration = (timeline.end_time - timeline.start_time).total_seconds()
        position = current_position(timeline.position.total_seconds(), timeline.last_updated_time,
                                    playing, datetime.now(UTC))
        return MediaState(True, title, artist, session.source_app_user_model_id or "", playing,
                          min(position, duration) if duration > 0 else position, duration, art)

    async def _run(self) -> None:
        while True:
            try:
                state = await self._snapshot()
                self.error = None
            except Exception as exc:
                if self.error is None:
                    log.warning("Media session unavailable: %s", exc)
                self.error = str(exc)
                state = MediaState()
                self._manager = None
            if state != self._last:
                self._last = state
                self._on_change(state)
            await asyncio.sleep(POLL_SECONDS)

    def command(self, action: str) -> asyncio.Future:
        return asyncio.run_coroutine_threadsafe(self._command(action), self._loop)

    async def _command(self, action: str) -> bool:
        session = await self._session()
        if session is None:
            return False
        operations = {
            "play_pause": session.try_toggle_play_pause_async,
            "play": session.try_play_async,
            "pause": session.try_pause_async,
            "next": session.try_skip_next_async,
            "previous": session.try_skip_previous_async,
        }
        if action not in operations:
            raise ValueError(f"Unknown media action {action}")
        self._props_cache = None  # the track may change
        return bool(await operations[action]())

    @property
    def state(self) -> MediaState:
        return self._last
