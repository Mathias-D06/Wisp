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

## D-016 UNDOCUMENTED: AttachThreadInput fallback for switching windows
`SetForegroundWindow` is restricted (documented conditions). If it fails, Wisp briefly attaches
its thread input to the foreground thread and retries; that this lifts the restriction is not
documented. Isolated in `winapi/windows.activate`. Failure mode: Windows flashes the taskbar
button and the tool reports that it could not bring the window forward.

## D-017 Screenshots reach the model as a realtime video frame
Gap: the Live docs do not document images inside function responses (only generateContent
does). Decision: `look_at_screen` captures the monitor (or active window) with mss, downscales
to ≤1280 px JPEG q72, sends it with `send_realtime_input(video=…)` (documented, "JPEG ≤1 fps"),
waits 0.3 s, then returns a short text result. `turnCoverage` defaults to including all video on
Gemini 3.1+ models (ai.google.dev/api/live). Verify with MT-12.

## D-018 App index = Apps folder + Start Menu shortcuts
Decision: enumerate `shell:::{4234d49b-0245-4df3-b780-3893943456e1}` through Shell.Application
(documented on learn.microsoft.com "Find the AUMID"), plus `.lnk` files under both Start Menu
Programs folders; launch with the item's default verb (`FolderItem.InvokeVerb`). Fallback when
ParseName fails: `os.startfile("shell:AppsFolder\<AUMID>")`, which relies on the UNDOCUMENTED
`shell:AppsFolder` launch path. Matching uses rapidfuzz; only an exact name skips the
"which one did you mean?" question.

## D-019 What counts as untrusted text
Window titles, UI element names, recent/search file names and screenshots are untrusted (any web
page or document can set them), so those tools taint the session (D-012).

## D-020 Risky clicks and typing escalate in code
`click_element` becomes confirm-tier when the target's name contains words such as send, submit,
buy, pay, order, delete, post, OK, yes, allow, install, sign out (list in `tools/builtin/ui.py`);
`type_into_field` with `submit=true` is confirm-tier; opening executables/scripts/shortcuts is
confirm-tier. Purchases are therefore never one step from a model decision.

## D-021 comtypes must be imported on the main thread
comtypes calls CoInitializeEx(STA) on import in the importing thread; importing first in an MTA
worker raises RPC_E_CHANGED_MODE. `winapi/uia.py` imports it at start-up (main thread); tool
workers initialise COM as MTA (UIA docs recommend non-UI threads for clients).

## D-023 Dictation through generateContent, not the Live session or Interactions
Gap: the brief says "send the audio to Gemini". Decision: one stateless `generate_content` call
on the text model (default `gemini-3.8-flash`) with inline WAV and `thinking_level=low`. The
Interactions API stores inputs server-side by default (up to 55 days) — not acceptable for
private dictation — and the Live session would mix dictation into the conversation. If a model
rejects `thinking_level`, the call is retried without it.
Sources: ai.google.dev/gemini-api/docs/audio, /thinking, /interactions, api/generate-content.

## D-024 Paste and clipboard restore
Decision: snapshot every memory-based clipboard format byte-for-byte (GDI-handle and
synthesized formats skipped, 64 MB cap), put the text on the clipboard marked with
ExcludeClipboardContentFromMonitorProcessing + CanIncludeInClipboardHistory=0 +
CanUploadToCloudClipboard=0 (so neither Windows nor Wisp history keeps it), wait until Ctrl/Win/
Alt/Shift are physically released (else Ctrl+V becomes Win+V), re-activate the original window if
focus moved, send Ctrl+V, and restore the snapshot after 600 ms only if the clipboard sequence
number is still ours (the user did not copy something new). Clipboard writes happen on the Qt
thread with a hidden native window as owner (EmptyClipboard: a NULL owner makes
SetClipboardData fail; WM_DESTROYCLIPBOARD is sent to the owner, so it must pump messages).

## D-025 Dictation into admin windows
UIPI silently drops SendInput aimed at elevated windows. If the target window is elevated, Wisp
leaves the text on the clipboard and asks the user to press Ctrl+V.

## D-026 Dictation feedback
A small "HUD" pill near the bottom of the active screen shows Dictating / Transcribing / Inserted.
It never takes focus or mouse input (`WindowDoesNotAcceptFocus`, `WA_ShowWithoutActivating`,
`WindowTransparentForInput`), so the caret stays in the target field.

## D-022 Secure desktop / lock screen detection
`OpenInputDesktop(DESKTOP_SWITCHDESKTOP)` fails while the UAC secure desktop, Ctrl+Alt+Del screen
or lock screen is the input desktop. Wisp uses that only to explain why it cannot act; it never
tries to interact with those screens. Elevated windows are detected with `TokenElevation` and
reported as a UIPI limit rather than worked around.
