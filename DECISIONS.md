# Decisions

Format: Gap/Decision/Source for gaps in the brief; UNDOCUMENTED marks reliance on behaviour Microsoft
or Google do not document (each is isolated behind an interface and fails gracefully).

## D-001 Project location and toolchain
Decision: project at `C:\Users\mathi\Documents\Wisp` (user choice). Python 3.12.10 installed with the
Python install manager, Git and Inno Setup 6 via winget (user approved).

## D-002 Live model name lives in settings
Decision: default `gemini-3.8-live` (documented stable default Live model), editable in Settings.
Source: https://ai.google.dev/gemini-api/docs/models

## D-003 PySide6-Essentials instead of full PySide6
Gap: brief says PySide6. Decision: the Essentials wheel (QtCore/QtGui/QtWidgets/QtSvg/QtNetwork) is
the same LGPL Qt without WebEngine/Addons, keeping the installer small. Source: PyPI PySide6-Essentials.

## D-004 Keyboard hook via ctypes, not pynput
Decision: own `SetWindowsHookExW(WH_KEYBOARD_LL)` hook. pynput is LGPLv3 and adds no needed
feature; a direct hook gives exact control over modifier-only holds and suppression.

## D-005 UI Automation via comtypes, not the `uiautomation`/`pywinauto` wrappers
Decision: call the documented UIA COM API (`CUIAutomation`, `IUIAutomationElement`, patterns)
through comtypes (actively maintained). Both wrappers have had no release for 14+ months.

## D-006 Console text uses `send_realtime_input(text=…)`
Gap: brief does not specify. Decision: all user input (audio, images, typed text) goes through
realtime input, because the SDK docstring warns against interleaving `send_client_content` with
`send_realtime_input`. Typed text is sent without activity markers even in push-to-talk mode.
Source: SDK `live.py` docstring; google-gemini/gemini-skills `gemini-live-api-dev/SKILL.md`
("use send_realtime_input for all real-time streaming user input"); lead only:
googleapis/python-genai issue #1720 (text inside activity markers triggers an immediate reply and
`activity_end` afterwards closed the socket). Confirm with manual test MT-05.

## D-007 Audio through the default host API (MME)
Gap: device/host-API choice. Decision: open streams on the default host API (MME), which accepts
16 kHz input and 24 kHz output directly because Windows resamples; WASAPI/WDM-KS reject those
rates. If a device refuses, capture/play at its native rate through `audio/resample.py`.
Source: `spikes/audio_formats.py` on this PC; sounddevice stream docs.

## D-008 Push-to-talk default: hold Alt+Win
Gap: the brief makes the PTT hotkey configurable but gives no default. Decision: Alt+Win (hold
250 ms), which has no Windows meaning on its own and does not clash with the dictation (Ctrl+Win)
or Circle to Ask (Ctrl+Shift) chords. Clicking the orb toggles talking.

## D-009 UNDOCUMENTED: mask key stops Start menu / menu bar / layout switch after a hold
Windows opens Start when Win is released without another key, activates the menu bar after a
lone Alt, and may switch keyboard layout after Ctrl+Shift / Alt+Shift. When a hold-chord
activates, Wisp taps VK 0xE8 (documented as "Unassigned" in the virtual-key table) so the shell
sees a combination. That the shell then skips Start is not documented by Microsoft (it is the
technique AutoHotkey uses). Isolated in `winapi/input.send_mask_key`, called only via
`ChordMachine.on_activate`. Failure mode: the Start menu may open after a dictation; nothing
else breaks. Verify with MT-10.

## D-010 Tool-call behaviour per Live model
Decision: on `gemini-3.8-live` declarations omit `behavior` (documented default: the model waits
for the tool response). On `*-extended-thinking` models every declaration is `NON_BLOCKING` and
responses carry `scheduling=WHEN_IDLE`, because blocking mode returns an error there.
Sources: ai.google.dev/gemini-api/docs/live-api/tools; gemini-skills SKILL.md.

## D-011 Confirmation protocol (F12.2)
Gap: how a spoken "yes" is verified in code. Decision: a confirm-tier call returns
`needs_confirmation` with an id and shows a Yes/No card. Evidence is the user's own words (Live
input transcription or console text, short explicit replies only; any "no/cancel/wait" wins) or a
click. The model then calls `confirm_action(id)`; the dispatcher refuses unless evidence exists.
If the model forgets, the dispatcher runs the approved action after 6 s and tells the model. A
click runs it at once. Scheduled routines need a click (card waits 10 min, then the step is
skipped). Pending confirmations expire after 2 minutes.

## D-012 Taint window for untrusted content (F12.4)
Decision: reading screen/file/web content marks the session tainted for 5 minutes (setting).
While tainted, every confirm-tier call asks (auto-approve is ignored) and some SAFE tools that act
on the UI (typing, clicking by name, opening URLs) also ask.

## D-013 Toasts via the tray icon
Gap: the stack lists pywinrt toasts, which need an AppUserModelID registered through a Start-menu
shortcut for unpackaged apps. Decision: `QSystemTrayIcon.showMessage`, which Windows displays as a
notification without extra registration. Source: doc.qt.io/qt-6/qsystemtrayicon.html.

## D-014 Settings in JSON, data in SQLite
Decision: user preferences in `%APPDATA%\Wisp\settings.json` (readable, forgiving loader); all
data (to-dos, memories, clipboard, logs, stats, app index, tasks) in `wisp.sqlite3`; APScheduler
jobs in `jobs.sqlite3`.

## D-015 Session continuity details
* Idle timeout default 5 minutes; the handle is kept, so the next turn resumes (handles live 2 h).
  After that, or if a resume is rejected, a fresh session starts with remembered facts.
* Tool results that finish after the connection changed are sent to the new connection as a
  `[Wisp notice]` text, because the new connection does not know the old call ids.
* Model audio that arrives while the user holds push-to-talk is dropped (barge-in).
* Always-listening mode: an idle session is woken by mic level and the last 0.5 s of audio is
  replayed. Headphones are recommended (documented echo/self-interruption gotcha).
