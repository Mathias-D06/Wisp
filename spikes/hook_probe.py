"""Spike: prove the WH_KEYBOARD_LL hook installs, sees injected keys, and ignores Wisp's own
signed injections. Uses VK 0x97 (documented "Unassigned"), so nothing happens on screen.

Run: .venv\\Scripts\\python spikes\\hook_probe.py
Expected: "seen: [(151, True), (151, False)]" — only the unsigned pair.
"""

import ctypes
import time

from wisp.hotkeys.hook import KeyboardHook
from wisp.winapi import input as winput


class Recorder:
    def __init__(self):
        self.seen = []

    def key_event(self, vk, down):
        if vk == 0x97:
            self.seen.append((vk, down))
        return False


hook = KeyboardHook(emit=lambda name, kind: None)
recorder = Recorder()
hook._machine = recorder
assert hook.start(), hook.error

unsigned = []
for up in (False, True):
    item = winput.INPUT(type=winput.INPUT_KEYBOARD)
    item.ki = winput.KEYBDINPUT(wVk=0x97, wScan=0, dwFlags=winput.KEYEVENTF_KEYUP if up else 0,
                                time=0, dwExtraInfo=0)
    unsigned.append(item)
array = (winput.INPUT * 2)(*unsigned)
sent = ctypes.windll.user32.SendInput(2, array, ctypes.sizeof(winput.INPUT))
signed = winput.tap(0x97)
time.sleep(0.3)
hook.stop()
print("INPUT size:", ctypes.sizeof(winput.INPUT), "sent unsigned:", sent, "signed:", signed)
print("seen:", recorder.seen)
