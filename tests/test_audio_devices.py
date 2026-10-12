"""Windows-only checks against the real audio stack. Silent: plays zeros, records nothing."""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.windows


def _has_output() -> bool:
    from wisp.audio.devices import output_devices

    return bool(output_devices())


def test_device_lists_are_named():
    from wisp.audio.devices import input_devices, output_devices, resolve

    for device in input_devices() + output_devices():
        assert device.name and device.index >= 0
    assert resolve("", "output") is None
    assert resolve("No Such Device 123", "input") is None


@pytest.mark.skipif(not _has_output(), reason="no audio output device")
def test_player_opens_24khz_and_clears_instantly():
    from wisp.audio.playback import Player

    player = Player(lambda: "")
    try:
        player.feed(b"\x00\x00" * 24000)  # one second of silence
        assert player.is_playing()
        time.sleep(0.2)
        player.clear()  # barge-in
        assert not player.is_playing()
    finally:
        player.close()
