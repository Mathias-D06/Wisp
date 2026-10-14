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
*Updated by D-045: notifications are island banners; the tray toast is the fallback when the island is off or hidden by a full-screen app.*
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
*Updated by D-045: dictation reports to the island; this HUD is the fallback when the island is off.*
A small "HUD" pill near the bottom of the active screen shows Dictating / Transcribing / Inserted.
It never takes focus or mouse input (`WindowDoesNotAcceptFocus`, `WA_ShowWithoutActivating`,
`WindowTransparentForInput`), so the caret stays in the target field.

## D-027 UIA integration tests run the client in a child process
An in-process UIA client (worker thread) driving a Qt window of the same process crashed the test
run intermittently (0xC0000005 inside Qt's provider). Wisp never automates its own windows
(`target_window` excludes its own PID), so tests now mirror production: `tests/uia_client_probe.py`
runs in a separate process on an MTA worker thread. pytest's faulthandler still logs a handled
first-chance COM error (0x8001010d) raised inside Qt's provider while it serves that call; the
run passes with exit code 0 (5 consecutive full runs on 2026-10-12).

## D-028 Circle to Ask mechanics
*Updated by D-045: the answer plays in the island and ends as an "Answer" banner; the bubble beside the loop is the fallback when the island is off.*
Gap: how the gesture, the question and the image reach the model. Decisions:
* One overlay per QScreen, showing that screen's frozen `grabWindow(0)` screenshot (taken before
  any overlay appears, so the crop is exactly what the user circled). Crop rect = logical bbox ×
  (pixmap size ÷ screen geometry) on that screen — independent of DPI and monitor layout.
* The user must draw a loop (left-drag) while holding the chord; releasing without a loop cancels.
* Push-to-talk mode: the question streams live inside activity_start/activity_end; on release the
  JPEG crop is sent as a realtime frame and activity_end follows 300 ms later (realtime streams
  are concurrent, so the image gets a head start). Always-listening mode: the live mic stream is
  paused and the question is buffered, then replayed after the image, followed by
  audio_stream_end (otherwise server VAD might answer before the image arrives).
* The system instruction tells the model that such an image is the circled area. The answer is
  spoken and shown in a bubble beside the loop (output transcription), hidden 12 s after the turn.
* Overlays never take keyboard focus (`WindowDoesNotAcceptFocus`), so a cancelled gesture
  (Ctrl+Shift+T etc.) still reaches the user's app.

## D-029 Scheduled tasks: stored resolved tool calls, missed-run policy
* The model converts speech into one structured `schedule_task` call: title, timing
  (`when` ISO 8601 local, `repeat` none/daily/weekdays/weekly/monthly/hourly, `time`, `days`,
  `day_of_month`) and `steps`, each a concrete tool call (`tool` + `args_json`). Steps are
  validated against the real tool schemas when created and replayed later through the dispatcher
  with `Origin.SCHEDULE` — no model call. A `prompt` step exists for work that needs the model at
  run time. Gap: tool arguments vary per tool, and the documented schema subset has no free-form
  objects, so step arguments travel as a JSON string.
* A routine containing a confirm-tier step needs confirmation when it is created, and that step
  still needs a click on the card each time it runs (scheduled steps never use auto-approval;
  unanswered cards skip the step after 10 minutes).
* Missed-run policy: one-off tasks run late if Wisp starts within 12 h of the time, else they are
  reported ("Missed while Wisp was closed") and switched off; repeating tasks run once if the
  last occurrence was missed by < 60 min (APScheduler coalescing), older ones are skipped and
  reported. Both values are in settings.json → scheduler. After every run a notification lists
  each step with ✓/✗.
* To-do reminders use a 20-second timer instead of APScheduler (they are rows, not jobs);
  overdue reminders fire once at start-up.
* APScheduler 3.x (not 4.x pre-release) with SQLAlchemyJobStore in `jobs.sqlite3`; the job
  stores only `wisp.scheduling.runner:run_scheduled_task(task_id)`. On start the job store is
  synced with the `tasks` table (missing jobs re-created).

## D-022 Secure desktop / lock screen detection
`OpenInputDesktop(DESKTOP_SWITCHDESKTOP)` fails while the UAC secure desktop, Ctrl+Alt+Del screen
or lock screen is the input desktop. Wisp uses that only to explain why it cannot act; it never
tries to interact with those screens. Elevated windows are detected with `TokenElevation` and
reported as a UIPI limit rather than worked around.

## D-030 UNDOCUMENTED system controls in the Island (F7.2)
Microsoft documents no API for these, so each is isolated in `system/controls.py`, raises
`ControlUnavailable(page)` on failure, and the tool/UI then offers the matching `ms-settings:` page.
* Night Light: rewrites the CloudStore registry blob
  `…\bluelightreduction.bluelightreductionstate\…\Data` — byte 18 is 0x15 (on) / 0x13 (off),
  "on" inserts `10 00` at offset 23, bytes 10–14 are a base-128 varint Unix timestamp that is
  refreshed. Layout verified only against this PC's blob (41 bytes, off); any other layout is
  refused (`parse_night_light` raises) instead of being written. Verify with MT-30.
* Dark mode: writes `AppsUseLightTheme` / `SystemUsesLightTheme` under
  `HKCU\…\Themes\Personalize` and broadcasts `WM_SETTINGCHANGE("ImmersiveColorSet")`. Reading
  those values is common practice; that writing them switches the theme is not documented.
* Output device: pycaw's `SetDefaultDevice` uses the undocumented `IPolicyConfig` COM interface.
* App icons for Store apps use the parsing name `shell:AppsFolder\<AUMID>` (same undocumented
  path as D-018); the icon call itself (`IShellItemImageFactory::GetImage`) is documented.
* Switching windows still relies on D-016 (AttachThreadInput).
Documented and used as such: volume (Core Audio via pycaw), brightness (WMI
`WmiMonitorBrightness(Methods)`, built-in panels only), Wi-Fi/Bluetooth
(`Windows.Devices.Radios`), media (`GlobalSystemMediaTransportControlsSessionManager`), sleep
(`SetSuspendState` + `SE_SHUTDOWN_NAME`), restart/shut down (`shutdown /r|/s /t 0`), lock
(`LockWorkStation`), wallpaper (`SystemParametersInfoW`).

## D-031 Island behaviour
*Superseded by D-045…D-047 (the Dynamic Island-style island). The tab, media and clipboard details below still hold.*
Gap: the brief gives the tabs but not the interaction details. Decisions:
* The pill (340×56) sits top-centre of the primary screen's work area, frameless, always on top,
  `Tool` window (no taskbar button) shown without activation. Hover for 140 ms or a wheel
  scroll expands it (680×560); it collapses 650 ms after the pointer leaves, unless a menu or
  dialog is open or a search box inside it has text. Tabs refresh when shown.
* Collapsed status priority: voice state (listening/thinking/speaking) → now playing → "voice
  needs a key" when no key is stored → voice status. Settings → General hides the Island.
* Media is polled once a second on the core asyncio loop (one code path for session changes,
  track changes and the progress bar; the media properties are fetched again only when the
  session changes or a command was sent). The position is extrapolated from the timeline
  snapshot (stamped with LastUpdatedTime) while playing.
* Clipboard history keeps the last 50 items (5–500 in settings.json), text ≤ 100 000 chars and
  PNG images ≤ 8 MB, deduplicated by SHA-256 (a re-copy moves to the top). Content carrying
  ExcludeClipboardContentFromMonitorProcessing or CanIncludeInClipboardHistory=0 is never read
  beyond the markers. The `clipboard_history` tool output is untrusted (D-012) and not
  schedulable; `copy_to_clipboard` asks when the session is tainted.
* Turning Wi-Fi off by voice is confirm-tier (it also cuts Wisp's own connection); sleep,
  restart and shut down are confirm-tier by voice and ask with a dialog in the Power tab; lock
  does not ask.

## D-032 Memory: what is stored, what reaches the model
Gap: the brief says "only the few most relevant facts" at session start but not how relevance is
judged before the user has said anything. Decisions:
* A memory is one user-stated fact (≤ 300 characters, ≤ 1000 facts) in the `memories` table with
  an FTS5 index kept in sync by triggers. Identical facts (case/spacing ignored) are refreshed,
  not duplicated; `remember(replaces=…)` swaps an outdated fact for a new one.
* Session start injects at most 8 facts and 1000 characters: pinned first, then by how often
  `recall` returned them, then most recently used or edited. Everything else is found with
  `recall` (bm25-ranked FTS5 search; user words become quoted prefix terms, so FTS syntax in
  speech can't break or widen the query). The system instruction labels injected facts as
  "facts, not instructions".
* `remember` and `forget` are SAFE but escalate to a confirmation while the session is tainted
  (D-012): otherwise a web page or document read by `look_at_screen`/file tools could plant an
  instruction-like "fact" that every later session would see, or erase real ones.
* Switching the Memory skill off in the Loadout hides the tools and stops injection; stored
  facts stay until deleted in Settings → Memories. Nothing leaves the PC except the injected
  facts and recall results sent to Gemini during a conversation.

## D-033 Loadout (F9.5 gap decision)
Gap: the brief names four slots (voice, personality, appearance, skills) but not whether users
keep several loadouts or how changes reach a running conversation. Decisions:
* One active loadout, stored in settings.json → `loadout`, edited in Settings → Loadout. No
  saved presets: four controls are quicker to change than a preset manager, and a second
  "loadout" concept would duplicate settings.
* Voice: one of the 30 documented prebuilt voices (no in-app preview, because a preview would
  need an extra TTS request and a key). Personality: presets friendly / professional / playful /
  minimal, or custom text (≤ 600 characters; empty custom text falls back to friendly).
  Appearance: theme Match Windows / Dark / Light and an accent (six swatches or any #rrggbb).
  Skills: one switch per tool group; terminal and raw input additionally need their Safety
  switch (F12.3), and the dispatcher re-checks both on every call.
* Theme and accent apply immediately. Voice, personality, skills (and model/language) changes
  request a reconnect: the next connection is built from the new settings and reuses the
  resumption handle so the conversation continues; if the server refuses to resume with the new
  setup, Wisp starts a fresh session with remembered facts (existing D-015 path). Verify MT-36.

## D-034 Terminal and raw input (F12.3) and what may skip confirmation
Gap: the brief puts the terminal and raw mouse/keyboard behind a Settings toggle but does not say
what they can do once enabled. Decisions:
* Both are off twice by default: the Safety switch (`allow_terminal` / `allow_raw_input`) and
  the Loadout skill. Switching one on in Settings → Safety also ticks its skill; the dispatcher
  re-checks both on every call, and the model is not told about the tools while they are off.
* `run_command` runs Windows PowerShell 5.1 (`powershell.exe -NoLogo -NoProfile
  -NonInteractive -Command`, present on every Windows 10/11) as the signed-in user, never
  elevated, no window, stdin closed, the user's execution policy untouched, 60 s default limit
  (max 300 s; the process tree is ended with `taskkill /T /F`), output capped at 4000
  characters and treated as untrusted (D-012). Every command asks first.
* Raw input: `mouse_click` (pixels of the latest `look_at_screen` image, mapped back to the
  monitor; refused if that image is older than 2 minutes) always asks. `press_keys` asks for
  Enter, Delete, any Win combination and Alt+F4 / Ctrl+W / Ctrl+Q / Ctrl+S / Ctrl+P / Ctrl+D /
  Shift+Delete / Ctrl+Enter; `type_text` asks when the text contains a line break; otherwise
  they are SAFE but ask while tainted. `mouse_scroll` is SAFE. Typing is limited to 2000
  characters. `mouse_click` is not schedulable (coordinates go stale).
* Auto-approval (Settings → Safety) applies only to requests made by voice/console, never while
  tainted, never in routines, and never to `NEVER_AUTO_APPROVE`: terminal, raw input, Recycle
  Bin deletion, power, risky clicks/typing in apps, opening executables, scheduling and deleting
  routines. That leaves closing a window, deleting a to-do and switching Wi-Fi off. The rule is
  enforced in `SafetyPolicy`, rejected by settings validation and filtered out by the page.

## D-035 Anti-cheat (F12.6)
Gap: "never bypasses anti-cheat" needs a concrete behaviour; Wisp cannot know whether a game
protects itself. Decision: Wisp never hides its input (every injected event is a normal
SendInput event carrying Wisp's signature) and the system instruction tells the model it can't
get past anti-cheat. In addition, raw-input tools refuse to act on a window that fills its
monitor while a known anti-cheat client is running (Easy Anti-Cheat, BattlEye, Riot Vanguard,
FACEIT, EA Javelin, PunkBuster, nProtect GameGuard, XIGNCODE3, Anti-Cheat Expert — process names
from a Tool Help snapshot), because the user's game account could be penalised. This is a
heuristic: a windowed game is not detected, and a full-screen non-game window is refused while
such a client runs; the message tells the user to act themselves.

## D-036 Settings coverage and hardening details (F11.4, F12.5)
* Settings → Hotkeys and audio edits the three hold-chords (live parse/conflict feedback; the
  same `find_conflicts` runs again on save), the hold time, microphone, speaker and always
  listening. A stored device that is not connected stays selected as "(not connected)" and the
  default device is used meanwhile (`audio/devices.resolve`).
* Always listening is switched in one place: the voice controller reacts to the saved setting,
  whether it came from the tray, the console or the Settings window.
* Settings → Action log shows the newest 500 entries with a filter, "only problems" and
  details; the store keeps the newest 5000 (pruned every 100 writes). Arguments and results are
  redacted and capped at 2000 characters each.
* Uncaught exceptions on any thread go to the redacted log (`sys.excepthook`,
  `threading.excepthook`), since the packaged app has no console.

## D-037 Packaging, installer and CI (phase 10)
* **PyInstaller one-folder, windowed** (`packaging/wisp.spec`, `dist/Wisp`). One-folder rather
  than one-file because it starts faster and needs no unpacking to %TEMP%. It also keeps
  Qt/PySide6 as separate, replaceable DLLs, which the LGPL relies on. The spec collects every
  `wisp` module (APScheduler reaches the job function by name), the pywinrt projections, the
  pre-generated comtypes UI Automation wrapper (generated by `build.py`, so the app never
  writes generated code) and the APScheduler/google-genai metadata. It drops what the app
  doesn't use: Qt's software OpenGL DLL, Qt translations, and PortAudio builds for other
  platforms. The result is about 165 MB on disk and a 54 MB installer.
* **`--self-check`** (`wisp/selfcheck.py`) runs inside the built exe and checks:
  - every module imports, plus the Qt image plugins;
  - SQLite FTS5 and DPAPI work;
  - PortAudio, WinRT, UI Automation and shell icons work;
  - the APScheduler SQLite store works, along with the Gemini config, all tool declarations
    and the CA bundle.

  It needs no network and doesn't touch the user's data. `build.py` fails the build if a
  required check fails. Audio devices are optional, because CI machines have none.
* **Inno Setup, per-user** (`PrivilegesRequired=lowest`; `{autopf}` maps to `{userpf}`, which
  is `%LOCALAPPDATA%\Programs`), so no UAC prompt is needed:
  - It adds a Start-menu shortcut and an optional desktop shortcut.
  - The "Start Wisp when I sign in" task is ticked by default. It writes the same HKCU Run
    value and command line (`"…\Wisp.exe" --background`) that the app's own setting writes.
  - `AppMutex` uses the app's single-instance mutex.
* **Uninstall** removes the program, the shortcuts and the Run value, including a value the
  app's own setting wrote after installation, and comtypes' empty %TEMP% cache folder. It then
  asks whether to delete `%APPDATA%\Wisp`. The default is **no**, so silent uninstalls keep
  the user's data.
* The installer and exe are **not code-signed** (no certificate is available). The README tells
  users about the SmartScreen prompt.
* **CI** (`.github/workflows/ci.yml`, windows-latest, Python 3.12): pip install from
  pyproject, ruff, pytest, Inno Setup through Chocolatey, then `build.py` (including the
  self-check). The app folder and installer are uploaded as artefacts. The repository has no
  remote yet, so the workflow has not run on GitHub. Its steps were run locally in a fresh
  virtual environment instead (PROGRESS log).

## D-038 Short push-to-talk turns (found during the first real test, 2026-10-13)
Gap: the Live API documentation doesn't say what happens to an activity that contains no audio.
A probe with a real key showed the answer: `activity_start` followed by `activity_end` with no
audio in between makes the server close the session with 1007 "Precondition check failed".
A single 32 ms chunk is enough to avoid it. The first real test hit this with an 81 ms tap.
Decisions:
* A push-to-talk turn sends `activity_start` only once 0.2 s of audio has been captured, and
  then sends the held-back audio in order. A shorter tap sends nothing and shows "Hold the talk
  key while you speak". Barge-in still stops playback locally the moment the key is pressed.
* A turn that carries an image (Circle to Ask) is always sent, even if it is short.
* Safety net in the sender: before any `activity_end` whose activity carried no audio (for
  example after a cancel or a reconnect), Wisp sends 32 ms of silence.
* A connection the server closes now shows its reason (the close reason, or "no reason given")
  instead of "None".

## D-039 What reaches Gemini: microphone format, speech gate, pre-roll, debug audio
Problem (first real test, 2026-10-13): "what time is it" appeared as "¿Qué?" and "我才没睡。", and
Wisp answered in those languages. Investigation:
* The pipeline sent correctly labelled audio: int16, mono, 16 kHz, `audio/pcm;rate=16000`,
  through MME. But the turns were very short. The microphone was open for 221 ms (the orb treated
  a double-click as two clicks) and 81 ms (a quick click on "Hold to talk").
* A probe through Wisp's own session with the user's key showed the cause. 4 s of silence was
  transcribed as "¿Qué tal?" and faint hiss as "¿Qué?", with a Spanish reply. The same session
  transcribed 10 clear English phrases perfectly. Gemini's transcriber invents short
  foreign-language phrases when given silence or near-silence.
* The user's microphone is a 4-channel array ("Microphone Array (AMD Audio Device)", 44.1 kHz
  shared format). Wisp had asked Windows to downmix it to mono. Silent or reference channels in
  such arrays lower the level, which makes near-silence more likely.

Decisions:
* **Capture in the device's native format** (rate, up to 8 channels, float32) when the device
  supports it, and convert in Wisp (`audio/convert.py`):
  - average only the *active* channels (within 10 dB of the loudest, using smoothed power);
  - apply a Blackman windowed-sinc low-pass at 7 kHz;
  - interpolate to 16 kHz, keeping filter and interpolation state between chunks;
  - convert float to int16 with clipping.

  If the native format is refused, Wisp falls back to asking Windows for 16 kHz mono int16
  (D-007). The format used is logged, and after 1 s of audio so is the level of each channel.
* **Speech gate.** A push-to-talk turn opens only once a 32 ms frame reaches −45 dBFS (quiet
  rooms sit around −60) and 0.2 s of audio has arrived. Everything held back is then sent in
  order.
  - A turn with no speech is dropped with "Wisp didn't hear any speech…".
  - A tap is dropped with "too short…".
  - Silent dictation is never sent.
  - A turn carrying an image (Circle to Ask) is always sent.
* **Pre-roll.** The chord machine now reports `arm` (keys down) and `disarm` (it won't fire).
  On `arm` the push-to-talk hotkey opens the microphone, and on `press` it sends the last
  300 ms, so the first word spoken during the 250 ms hold isn't lost. Only push-to-talk does
  this: Ctrl+Win and Ctrl+Shift are part of common shortcuts, and opening the mic for them would
  flash Windows' microphone indicator constantly.
* **Clicks.**
  - The console's Talk button works as hold-to-talk, or click to start and click again to send.
    A press shorter than 350 ms counts as a click.
  - The orb ignores Qt's double-click event and debounces toggles within 400 ms.
* **Debug audio.** Settings → Hotkeys and audio → "Save the audio sent to Gemini" writes the
  exact bytes of each voice turn, recorded where they are sent and including any safety
  silence, plus each dictation clip. The files are WAVs in `%APPDATA%\Wisp\debug`, and the newest
  20 are kept.
* **Test microphone** in the same page records 3 s, reports level, peak, device format,
  per-channel levels and whether speech was heard, and saves the clip.

## D-040 Language lock
* The docs (live-api/capabilities) say native-audio models "automatically choose the
  appropriate language and don't support explicitly setting the language code". The supported
  control is the system instruction.
* Wisp's instruction now says: the user speaks <language>; always understand and reply in it,
  even if the audio is unclear (then ask, in that language, to repeat); switch only when the user
  explicitly asks.
* The API reference documents `AudioTranscriptionConfig.languageCodes` as "BCP-47 language codes
  providing hints about the languages present in the audio". Wisp sends the code (e.g. `en-GB`)
  for input and output transcription. The capabilities page adds that the transcription language
  is inferred from the model's response, so locking the reply language also steadies the
  transcript.
* The setting's default is **English (UK)**, and the list offers English (UK), English (US) and
  16 other languages with codes. A free-text language gets the instruction only.
* Saved settings with the old plain "English" (the only English option before) load as English
  (UK).
* Dictation is told that the speaker normally speaks <language> and to use its spelling, but to
  keep another language if one is clearly spoken.

## D-041 Voice errors and the transcript
* **Error text.** A closed connection's reason (`APIError.details` for WebSocket closes) is used
  for classification and shown to the user. A bad key gives "Google rejected this API key…";
  anything else gives "Gemini closed the voice session (<reason>)…". The log line has the
  exception type, code, status, message and details.
* **Retry.** After a voice error the console shows a Retry button. Nothing silently switches to
  another mode.
* **Transcript.** The user's words for a turn are one row keyed by the turn number, updated in
  place even when transcription chunks arrive after Wisp has started answering. Typed text is
  its own row. Confirmation evidence (`user_final`, D-011) is unchanged.

## D-042 Window chrome: Mica, title bar, corners (brief of 2026-10-13, part 2)
* **Windows 11 22H2 and later (build 22621+).** The console and Settings get Mica through the
  whole window. The two calls are:
  * `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_MAINWINDOW = 2)`. The docs say
    this draws "the backdrop material effect corresponding to a long-lived window behind the
    entire window bounds", which is Mica on Windows 11.
  * `DwmExtendFrameIntoClientArea` with −1 margins, the documented "sheet of glass".

  The Qt window keeps a transparent background (`WA_TranslucentBackground`), and the panels
  paint on the material.
* **Windows 11 (build 22000+).** The title bar follows the theme
  (`DWMWA_USE_IMMERSIVE_DARK_MODE` = 20), and corners are rounded
  (`DWMWA_WINDOW_CORNER_PREFERENCE` = 33, `DWMWCP_ROUND` = 2).
* **Windows 10 and older builds.** Wisp sets none of these attributes, so the window gets the
  solid theme background. The build is checked before each call. Failures are logged and
  ignored, never raised.
* **Why not MicaController.** Microsoft's Win32 Mica article (apply-mica-win32) uses the
  Windows App SDK `MicaController`. Wisp doesn't take that dependency: it would need the
  WinAppSDK runtime, a DispatcherQueue and composition interop with Qt's HWND. The DWM attribute
  is the documented per-window backdrop switch. On this PC (build 26200) DWM accepts all three
  attributes and the frame extension (each returns S_OK). Microsoft says Mica falls back to a
  neutral colour while the app is inactive, and a capture taken from a background process is of
  an inactive window. So the on-screen capture (`docs/screenshots/after/onscreen`) shows the
  title bar and corners, and seeing Mica itself is manual test MT-57.
* **`WISP_NO_MICA=1`** forces the solid fallback, for troubleshooting and off-screen renders.
* **Popups.** The Island, HUD, answer bubble and confirmation card are frameless translucent
  windows with their own token surfaces and a soft shadow. They don't use Mica: they have no
  frame to extend, and Acrylic would need the same WinAppSDK path.
* **Theme changes.** The chrome is re-applied through a child QObject of the window, so the
  connection dies with the window. Every other theme hook (IconButton, ToggleSwitch, Chip,
  TranscriptView) is also a bound method rather than a lambda. Test:
  `test_ui_design.py::test_theme_change_after_widgets_are_deleted`.

## D-043 Design system (brief of 2026-10-13, part 2)
* **One token module.** `ui/theme.py` holds the palette, type, spacing, radii, shadow and icon
  sizes; `ui/motion.py` holds durations and easing. Every window uses them. No hex colour
  appears outside the theme; `test_no_hard_coded_colours_outside_the_theme` enforces this, with
  settings defaults and the self-check exempt as data.
* **Colour.**
  * Near-black, slightly cool dark mode: bg `#0e0f13`, surface `#16181d`, surface2 `#1f2128`.
    Light mode mirrors it.
  * Three text levels: text, secondary and muted.
  * The accent is used sparingly: focus ring, checked states, the primary button, sliders and
    the orb.
  * Contrast uses WCAG 2.x relative luminance and (L1 + 0.05) / (L2 + 0.05). Every text level
    and status colour is at least 4.5:1 on every surface, including hover, in both modes. The
    worst cases are 4.91:1 (dark) and 4.81:1 (light).
  * `accent_pair` darkens the fill or switches to dark text until accent buttons reach 4.5:1,
    for any accent. Tested with the presets and 200 random colours.
* **Type.**
  * Segoe UI Variable, falling back to Segoe UI, on the brief's 12/13/15/20 px scale.
  * The optical cut follows Microsoft's Windows type ramp: Small for 12 px captions, Text for
    body, Display from 20 px.
  * Two weights. Microsoft's guidance is Regular for most text and Semibold for titles, with
    minimums of 12 px Regular and 14 px Semibold. So Semibold is used only at 15 px and above
    (headings and the stats figure). Buttons, card titles and captions are Regular.
  * Sentence case everywhere. The Island's 11 px uppercase section labels became 12 px
    sentence case.
  * Transcript line height is 145 %.
  * Test: `test_type_follows_the_windows_minimums`.
* **Spacing and shape.** A 4/8 grid (4, 8, 12, 16, 24); radius 8 px for controls and 12 px for
  panels, as the brief asks. That is one step softer than Windows 11's own 4 px controls and
  8 px windows (geometry page). 1 px hairline borders. One soft shadow (24 px blur, 4 px down), used only by the
  Island.
* **Icons.**
  * Lucide 1.56.0 (ISC; icons Lucide derived from Feather are also MIT). 42 SVGs, behind 43
    icon names, ship in `wisp/assets/icons` with the licence file, which holds both texts.
    `packaging/notices.py` copies it into THIRD_PARTY_NOTICES.txt. They replace the Segoe Fluent Icons font glyphs.
  * Lucide was chosen over Fluent UI System Icons (MIT): it is one consistent line style that
    covers every glyph Wisp needs, with one plain SVG per icon.
  * A `QIconEngine` renders each SVG at the exact device-pixel size, so icons are sharp at any
    scale. It tints by replacing `currentColor` and keeps the stroke at 1.5 device-independent
    px at any icon size.
  * Stylesheet images (the check mark and chevrons) are tinted SVGs cached in
    `%APPDATA%\Wisp\cache\icons`.
* **App and tray icon.** The same painter as the live orb draws it at 16, 20, 24, 32, 40, 48,
  64, 128 and 256 px. Sizes up to 24 px get a larger core and less glow, so the icon still reads
  in the tray. `packaging/wisp.ico` is regenerated from it.
* **Console.**
  * Header: the orb (44 px), status and hint text, and a Retry button that appears only after a
    voice error.
  * Icon toggles for "Always listening" and "Mute" replace the two check boxes.
  * The transcript is message rows: a role label; partial text in the secondary colour with
    " …"; notices with an info icon.
  * Composer: the input, Talk (click or hold) and a primary Send button.
  * Scrollbars everywhere are thin and appear only on hover.
* **Settings, Island and popups.**
  * Settings: tabs in document mode, group boxes as cards, a toggle switch for "Reduce motion",
    and OK as the primary button.
  * Island: tinted icon buttons and chips; checked chips use a soft accent.
  * The HUD, answer bubble, confirmation card and the circle-to-ask hint pill use token
    surfaces.
* **Native toasts.** Windows notifications (`QSystemTrayIcon.showMessage`) are drawn by
  Windows and can't be styled. Wisp's own popups were restyled instead.
* Found while restyling: the circle overlay's new hint pill left its brush set, so the user's
  loop was filled. `_paint_hint` now saves and restores the painter. Regression test:
  `test_circle.py::test_overlay_loop_is_outlined_not_filled`.

## D-044 Motion and idle cost (brief of 2026-10-13, part 2)
* **Motion only on state changes.**
  * Windows and popups fade in, and the HUD also fades out.
  * The Island resizes when it expands or collapses, and its contents appear afterwards.
  * Tabs cross-fade, the toggle knob slides, and new transcript rows fade in.
  * Durations are 120, 180 and 250 ms with OutCubic easing. Nothing loops except the orb.
* **The orb is the one living element.**
  * Ready: a slow glow on a 4.5 s cycle, drawn at 8 fps.
  * Listening: grows with the microphone level.
  * Thinking: a soft pulse on a 1.4 s cycle.
  * Speaking: follows the output level.
  * Listening, thinking and speaking redraw every 16 ms (about 60 fps). Error and offline are
    still.
  * The timer runs only while the orb is visible and its state moves.
* **Off switch.** Motion is off when Windows "Animation effects" is off
  (`SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION)`, read each time motion is checked, so a
  change applies at once) or when Settings → Loadout → "Reduce motion" is on. Every helper then jumps to the end
  state, and the orb is drawn once per state change.
* **Idle cost.**
  * The voice controller emits its visual state only when the state or text changes, or when
    the level moves by at least 0.02.
  * The Island sets its status text only when it changes.
  * Idle CPU is measured by `spikes/idle_cpu.py`: Island visible, no key, 60 s, whole process
    tree. The numbers are in PROGRESS.md.
* **Tests.** Tests pin motion off (conftest) unless they test motion itself. Island animation
  tests park the hover timers, because the real pointer may rest where the Island appears.

## D-045 The island replaces the pop-ups (brief of 2026-10-13, part 3)
* **One surface.** A black, Dynamic Island-style shape at the top centre replaces the console
  window, the old Island pill, the dictation HUD, the Circle to Ask answer bubble and Wisp's
  tray notifications. It has six presentations:
  * **idle:** a 180×32 pill with a small orb;
  * **sliver:** a thin 120×5 line, used only when auto-hide is on;
  * **activity:** a wider pill showing one live thing;
  * **split:** the activity pill plus a detached 36 px circle for a second activity;
  * **banner:** a 400×76 card for an event;
  * **expanded:** a 720×580 panel.

  The island is black in either theme, so its content uses the dark palette
  (`theme.palette_for`).
* **Activities.** Each activity shows one thing at a glance:
  * listening: orb plus the live mic waveform;
  * thinking: orb pulse plus "Thinking…";
  * speaking: orb, the first words of the reply, and output level bars;
  * dictation: mic icon, "Dictating…" and a level meter;
  * Circle to Ask: its prompt, in the dictation style;
  * a short status, such as "Inserted 12 words";
  * music: album art plus an equaliser driven by the real output peak meter
    (IAudioMeterInformation);
  * countdown: the next reminder or routine due within 10 minutes, as m:ss.
* **Priority, defined once** (`ui/island/machine.py`, `TIERS`): active voice > banner > timer >
  music > idle.
  * Active voice covers listening, thinking, speaking, dictation and Circle to Ask.
  * When two live activities run at once, the higher one takes the pill and the next one goes
    in the split circle.
  * Banners wait in a queue while voice is active and show one at a time. Each holds 3 s, longer
    while hovered, and gets another 1.5 s after the pointer leaves.
  * The same title and line already queued is refreshed, not repeated. The queue keeps the
    newest 5, and banners older than 30 s are dropped.
  * A banner that active voice interrupts goes back to the front of the queue and starts again
    afterwards.
  * The user's own actions win over everything: an expanded island stays expanded (banners
    wait), and a full-screen app hides the island.
* **Services send events.**
  * Voice: orb state, transcript and notices. Errors become a red "Voice problem" banner that
    retries on click.
  * Dictation and Circle to Ask use `IslandFeedback` (the HUD's interface) and `IslandBubble`
    (the answer becomes an "Answer" banner that opens the Chat tab).
  * Media: now playing and album art.
  * The reminder timer: the countdown.
  * `app.notify`: banners with an icon and a tab to open (Reminder → Today, Routine done →
    Today).
  * When the island is switched off (Settings → General), or hidden by a full-screen app,
    everything falls back to the old HUD, the bubble and Windows notifications, so nothing is
    lost.
* **Expanded panel.** It holds:
  * a header: orb, status, API-key prompt, Retry, always listening, mute, "Open in window" and
    Settings;
  * now playing with controls;
  * the tabs: **Chat** first (the transcript and a text box, replacing the console), then
    Controls, Today, Stats, Clipboard, Apps, Wallpaper and Power.

  The console window stays as a fallback: "Open in window", the tray menu, and when the island
  is off. Both views share `ui/chat.py`.
* **Interaction.**
  * Hover grows the pill 4 %. Hovering for 300 ms, clicking or scrolling down expands it.
  * Scrolling up on the island's top band collapses it, or dismisses a banner.
  * In the expanded state, the island collapses 0.5 s after the pointer leaves (unless a text
    box holds unsent text or a menu is open), on Esc, or on a click outside. Clicks outside are
    detected with GetAsyncKeyState, polled every 50 ms only while the island is expanded and
    the pointer is outside.
  * Clicks on the compact pill:
    * the orb: talk;
    * the right half of the music pill: play/pause, without expanding;
    * a banner: its action, then it is dismissed;
    * anywhere else: expand.
  * Swiping up on a banner dismisses it.
  * Right-click opens a menu: Settings…, Mute microphone, Open in window, Quit Wisp.
  * A hold hotkey (default Ctrl+Alt+Space, Settings → Hotkeys and audio) toggles the expanded
    panel.
  * Esc is reported by the keyboard hook while the island is expanded. It is never swallowed.
* **What stays separate.** The confirmation card (D-011) stays its own window. It is a safety
  prompt that must not be queued behind banners or time out with them, and it sits below the
  compact island. The circle overlay is an input surface, not a pop-up.
* **Settings.**
  * General: show the island; which display it uses ("Main display" or "The display with the
    pointer", followed while idle); and shrinking to a sliver after 10 s idle (off by
    default).
  * Hotkeys and audio: the island hotkey.
* **Tokens.** Every island size, spring constant and timing is in `theme.ISLAND`
  (IslandTokens).
* **Recordings.** `docs/island/` holds GIFs rendered from the real widget by
  `spikes/island_record.py`:
  * the real Island in a real WispApp with sample data;
  * driven through its own handlers on a simulated clock at 50 fps;
  * rendered with QWidget.render while its windows never reach the screen.

  This was chosen over a screen recording, which would also capture whatever is around the
  island on this PC's screen. MT-77 asks for a real screen recording of your own if you want
  one.
* Supersedes the parts of D-013, D-026, D-028 and D-031 that described the tray toasts, the
  HUD, the answer bubble and the old pill. Those remain as the fallbacks above.

## D-046 Island window behaviour on Windows
* **Window.**
  * The window is `Qt::Tool | FramelessWindowHint | WindowStaysOnTopHint` with
    `WA_TranslucentBackground` and `WA_ShowWithoutActivating`.
  * WS_EX_NOACTIVATE is set with SetWindowLongPtrW after creation. Per the docs, clicking such a
    window never makes it the foreground window, and its tool-window style keeps it out of the
    taskbar and Alt+Tab.
  * Qt's own `WindowDoesNotAcceptFocus` sets the same style, but Qt then refuses to activate the
    window (`QWindow::requestActivate`), and the text box must be able to take focus.
  * The probes confirm WS_EX_NOACTIVATE | TOOLWINDOW | TOPMOST | LAYERED, and that showing the
    window never changes the foreground window.
* **Focus.**
  * The one exception is a click into a text box: the island calls SetForegroundWindow. That is
    allowed because the calling process received the last input event.
  * The app that was in front is remembered and gets the foreground back when the island
    collapses.
  * The test process itself is refused SetForegroundWindow (it never received input), so the
    real check is manual: MT-70.
* **Canvas.** A fixed transparent canvas sized for the largest state plus overshoot and shadow
  (829×649 logical px). The native window is never resized while the shape morphs, so there is
  no resize flicker. The shape is a QPainterPath (antialiased rounded rect, plus an ellipse for
  the split) filled pure black, with a 1 px inner highlight that fades from the top edge.
* **Click-through.**
  * The input region is the visible shape, grown 1 px for the antialiased edge. It is set with
    `QWindow::setMask`, documented as an input hint and implemented with SetWindowRgn.
  * It is updated whenever the shape moves by half a pixel, which costs 0.4 ms per call on this
    PC.
  * Layered windows already let alpha-0 pixels through (Window Features docs). The explicit
    region also covers antialiased pixels and stays exact during morphs.
  * A probe and a test confirm with WindowFromPoint that points beside and below the pill
    belong to other windows, and points inside belong to the island.
* **Shadow.**
  * A window region also clips drawing, so the soft shadow lives in a second click-through
    window (`WindowTransparentForInput` → WS_EX_TRANSPARENT).
  * It is placed directly behind the island with SetWindowPos(…, SWP_NOACTIVATE).
  * It draws a nine-slice of one pre-blurred rounded square (Pillow GaussianBlur). Strength
    rises with the shape's height, so compact pills have none.
* **Placement.**
  * Top centre of the chosen display's work area (below a top-docked taskbar).
  * On a monitor change, `QWindow::setScreen` and a fresh input region at the new device pixel
    ratio. Qt handles per-monitor DPI.
* **Full-screen hiding** (`winapi/fullscreen.py`, polled once a second while the island is on).
  The island hides when either:
  * SHQueryUserNotificationState reports QUNS_RUNNING_D3D_FULL_SCREEN or
    QUNS_PRESENTATION_MODE; or
  * the foreground window covers the island's whole monitor. That means:
    * its DWM extended frame bounds cover MONITORINFO.rcMonitor of the monitor
      MonitorFromWindow gives;
    * it is not maximized (IsZoomed: a maximized window covers the monitor when the taskbar
      auto-hides);
    * it is not the desktop, the taskbar or Wisp.

  QUNS_BUSY alone isn't used: the docs don't say which monitor it refers to.

## D-047 Island motion and cost
* **Springs.**
  * Width, height and the split circle (diameter and gap) are unit-mass damped springs, stepped
    with the exact closed-form solution, so the motion is the same at any frame rate.
  * Retargeting keeps position and velocity, so an interrupted morph turns smoothly from where
    it is.
  * Constants: growing uses k=450, ζ=0.82 (about 1 % overshoot, a few pixels). Shrinking uses
    k=600, ζ=1.0, clamped at the target so it never overshoots. Changes under 60 px use k=700,
    ζ=0.9.
  * The corner radius is not a spring: it is min(height/2, 26), so compact shapes are always
    perfect capsules and the expanded panel settles at 26 px.
  * Measured: a 548 px expand settles in about 0.45 s, and small morphs in about 0.15 s.
* **Content.**
  * Compact content is painted with QPainter, so it can fade and scale while the shape morphs.
    Outgoing content fades over 120 ms while shrinking to 0.96. Incoming content starts 40 ms
    later and fades in over 180 ms while growing from 0.96.
  * The expanded panel morphs as a snapshot (QWidget.grab), whose rows fade in 20 ms apart. The
    live panel appears once the shape has settled.
  * Nothing loops while idle except the orb's slow glow.
* **Motion off** (Windows "Animation effects" off, or Reduce motion): the shape jumps to its
  target and content crossfades in 100 ms with no scaling. Meters rest at a neutral height.
* **One frame timer**, at a rate that matches what is moving:
  * 16 ms while springs or fades run;
  * 33 ms for voice meters;
  * 50 ms for the music equaliser;
  * 250 ms for a countdown;
  * 125 ms for the idle orb glow (none with motion off);
  * stopped while the live panel shows or the island is hidden.

  Each frame repaints only the area that changed.
* **Measured on this PC.** Frame rate is from `spikes/island_fps.py`, idle CPU from
  `spikes/idle_cpu.py`; both are logged in PROGRESS.md.
  * Morphs run at 62 fps, with p95 frame time ≤ 18 ms and a paint of 1–2 ms.
* Idle CPU, measured the same way for both (`spikes/island_idle_cpu.py`: in-process, island visible, 30 s warm-up, then 60 s): the old island (commit 2d0f99c) used 5.99 % of one core; the new one uses 0.44 % with the orb's glow and 0.42 % with Reduce motion, so the glow costs almost nothing. Hidden behind a full-screen app (`spikes/idle_cpu.py`, a separate process): 0.21 %.

## D-048 The application font is sized in points (brief of 2026-10-13, part 4)
* **The bug.** `python -m wisp` printed "QFont::setPointSize: Point size <= 0 (-1), must be
  greater than 0".
  * The application default font was pixel-sized (`ui_font`), and Qt documents that pointSize()
    "returns -1 if the font size was specified in pixels".
  * The Today tab's due-time field has a calendar popup (QDateTimeEdit.setCalendarPopup), and
    its QCalendarWidget copies the default font's point size.
  * Found by a probe that prints the Python stack for every Qt font warning while it starts Wisp
    and opens every island tab, the console, every Settings page and the menu.
* **The fix.** `theme.app_font()` sets the default font with setPointSizeF.
  * The point size is the pixel token × 72 / the screen's logical DPI. QScreen documents that
    logical DPI "is used to convert font point sizes to pixel sizes".
  * On this PC the logical DPI is 96 at 100, 125, 150 and 200 % scaling, and the 9.75 pt font
    renders at exactly 13 px with the same line height as before.
* **Pixel-sized fonts stay** for widgets and painters that set their own (`ui_font`: the
  island's content, the HUD, the overlay). No code copies a point size from them.

## D-049 Auto-hide and the top-centre reveal (brief of 2026-10-13, part 4)
* **Replaces the sliver** from D-045. When nothing is going on for a while, the idle island
  slides up out of view and fades (springs `lift` and `vis` on the same frame loop). Once it
  has settled out of view, its window is hidden, so nothing at the top of the screen (browser
  tabs, title bars) is blocked.
* **Settings → General.**
  * "Hide the Island when nothing is happening" (default on), after 3–15 s (default 6).
  * "Keep it visible while music plays" (default on).
* **When hiding is allowed** (`IslandStateMachine.hideable`, one place). Only when auto-hide is
  on and none of these holds:
  * voice, dictation, Circle to Ask or a short status is active;
  * a banner is showing or queued;
  * a countdown is shown;
  * a confirmation card is waiting;
  * the island is expanded or under the pointer;
  * music is playing (unless "keep visible" is off).

  The delay counts from when the last of these ended. It restarts when the pointer leaves the
  island and after a reveal.
* **What brings it back.**
  * Anything that isn't idle shows at once, because it's a new presentation: voice, dictation,
    banners, reminders, countdowns, the island hotkey (expands it), a waiting confirmation.
  * The pointer resting in the reveal zone for 150 ms. The zone is the idle pill's width plus
    40 px on each side, and the top 3 px of the display's full geometry (the very edge, even
    over a top taskbar). The dwell keeps a pointer passing over browser tabs from revealing it.
* **Pointer detection.**
  * `QCursor.pos()` against `QScreen.geometry()`, polled at about 30 Hz only while the island is
    slid away. Qt reads the cursor with GetCursorPos and maps both to device-independent pixels
    per display. On this PC, at 175 %, GetCursorPos (2244, 991) reads as Qt (1282, 566).
    So the zone is the same size on screen at every scaling and on every display.
  * In "display with the pointer" mode, the zone is on whichever display the pointer is on,
    and the island is placed there before it reappears.
  * A low-level mouse hook (WH_MOUSE_LL) would run on every mouse move system-wide the whole
    time. A poll that runs only while hidden is lighter.
  * GetDpiForMonitor isn't used: Microsoft says it "should not be used if the calling thread is
    per-monitor DPI aware".
* **Full screen.** While a full-screen app is in front the island stays hidden; the zone isn't
  polled (D-046). If it had slid away before, it returns straight to away afterwards instead
  of reappearing.
* **Motion off.** The island disappears and reappears at once.
* **Idle CPU, measured on this PC** (`spikes/island_idle_cpu.py`): 0.52 % of one core while slid away (the ~30 Hz reveal poll) against 0.36 % while visible and idle, with or without the orb's glow (in-process, 30 s warm-up, 60 s).

## D-050 Google Calendar in the island (brief of 2026-10-13, part 4)
* **Calendar replaces the Wallpaper tab.** The wallpaper picker moves to Settings → Loadout →
  Appearance (a Wallpaper row; "Change…" opens the same picker in a dialog). There was no
  wallpaper voice tool, so one was added: `wallpaper` (group "system") says which picture is
  current, lists the pictures the picker shows, and sets one by name. It matches the name
  fuzzily (rapidfuzz WRatio ≥ 70) and only ever picks from that list, never a path from the
  model.
* **The user's own Google Cloud project and a Desktop app client.** Settings → Accounts walks
  through it: create a project, enable the Calendar API, set up the consent screen (External,
  with yourself as a test user), create a Desktop app client and import its JSON. Only
  "installed" (Desktop app) clients are accepted; a "web" client is refused with a message.
  Wisp ships no client of its own: a shared one would need Google's verification and would put
  every user under one quota.
* **Sign-in: loopback redirect with PKCE**, through google-auth-oauthlib's
  `InstalledAppFlow.run_local_server(host="127.0.0.1", port=0)`. That is a one-shot listener on
  a random free port on 127.0.0.1, with the system browser and a 5-minute timeout. Google
  recommends the loopback redirect for Windows desktop apps. The library (1.5.0) adds an S256
  `code_challenge` and `access_type=offline` itself. `prompt=consent` makes every connect return
  a refresh token. It runs on a thread while the UI says it's waiting for the browser.
* **Scopes, narrowest first.**
  * Reading: `calendar.calendarlist.readonly` (which calendars, their colours and time zones)
    plus `calendar.events.readonly` (their events). Not `calendar.readonly`.
  * Adding events, only when "Let Wisp add events" is ticked: `calendar.events.owned`, "create,
    change, and delete events on calendars you own". It is the narrowest scope events.insert
    accepts. The others are `calendar.events` (every calendar you can edit) and `calendar`
    (everything, including sharing and deleting calendars); `calendar.app.created` only covers
    calendars the app created. So Wisp adds events only to calendars whose access role is
    "owner"; a calendar merely shared with write access is refused before Google is asked.
  * Google doesn't support incremental authorization for installed apps. Switching event
    creation on therefore means connecting again; the Accounts page and the voice tool say so.
* **Tokens.** The OAuth client and the tokens are kept like the API key: DPAPI
  (CryptProtectData, current user), each file with its own entropy (`google_client.bin`,
  `google_token.bin` in `%APPDATA%\Wisp`). They are never logged; log lines carry exception
  class names only. Access tokens that google-auth refreshes during a sync are saved back.
* **Reconnect and Disconnect.**
  * A failed refresh (`RefreshError`: expired or revoked) or a 401 switches to "reconnect":
    the Calendar tab and Settings → Accounts show Reconnect, and the cache stays readable.
  * Disconnect deletes the token and the cached calendar at once, then revokes the token at
    `https://oauth2.googleapis.com/revoke` on a thread. Revoking the refresh token also ends its
    access tokens.
* **Testing status means 7-day refresh tokens.** Google issues a refresh token "expiring in 7
  days" to an External app whose publishing status is Testing (unless it asks only for basic
  profile scopes). A personal project left in Testing therefore asks to reconnect about once a
  week. The README lists the ways round it.
* **Sync**, per calendar the user can read (calendarList roles reader, writer,
  writerWithoutPrivateAccess and owner; freeBusyReader has no events):
  * Full sync: `events.list` from 7 days back to 180 days ahead (timeMin/timeMax), with
    `singleEvents=true` (recurring events as instances), `showDeleted=true` and
    `maxResults=2500`, page by page. The last page's `nextSyncToken` is saved.
  * Incremental sync: the same parameters with `syncToken` instead of the time window
    (events.list doesn't combine them). Cancelled events are removed from the cache.
  * 410 Gone: that calendar's cache and token are dropped and it gets a full sync. Google: "a
    full wipe of the client's store and a new full sync".
  * Once a week a full sync moves the window forward.
  * When: every 5 minutes, when the Calendar tab opens (if the last sync is over a minute old),
    and with its Sync button. After a failure it waits 5, 10, 20, 40, then 60 minutes.
* **Offline cache.** SQLite tables `gcal_calendars` and `gcal_events` in `wisp.sqlite3`, and
  `gcal_last_synced` in `meta`. The tab, the voice tools and the island read only the cache, so
  they work offline and say when it was last synced.
* **Several calendars.** Each keeps its Google colour (`backgroundColor`). New calendars are
  shown when Google shows them (`selected`) or are the primary one; the user's choice in
  Settings → Accounts is kept across syncs.
* **Time zones and daylight saving.** Times are shown in the primary calendar's time zone
  (Europe/London here), or the PC's if there is none, using zoneinfo.
  * Timed events are converted from their UTC offset. All-day events are plain dates with an
    exclusive end, so a 2-day event is on 2 days whatever the zone.
  * A wall time for a new event takes the first of two repeated times (01:30 on 25 Oct 2026 is
    BST), and a skipped time moves forward (01:30 on 29 Mar 2026 becomes 02:30 BST).
  * Durations are elapsed time: 2 hours from 00:30 on 25 Oct ends at 01:30 GMT.
  * events.insert bodies carry an explicit offset and the IANA `timeZone`.
* **The tab.**
  * Agenda: today and the next 7 days, all-day events first, then by start time; multi-day
    events on each of their days.
  * Month: six weeks from Monday, up to three colour dots per day; click a day for its events.
  * Each row: the calendar's colour, the time ("09:30–09:45", "All day", "from 22:00", "until
    02:00") and the title. A click opens the event in Google Calendar in the browser.
* **Island heads-up.** The next timed event on a shown calendar, within the heads-up time
  (Settings → Accounts; default 10 minutes, 0 is off), becomes the island's countdown. It shares
  the countdown with reminders and routines; the earliest wins.
* **Voice.**
  * `calendar_list` (start today, tomorrow or a date; 1–31 days) reads the cache and says when
    it last synced.
  * `calendar_create` is confirm-tier. The card reads, for example, "add “Dentist” to Me, Wed
    14 Oct 15:00–15:30". It can't be scheduled: a routine shouldn't add events unseen.
  * Skill group "calendar" in Settings → Loadout. It starts switched on once for existing users
    (`known_skills`), and stays off if they switch it off.
* **Packaging.** google-api-python-client's discovery cache holds 605 documents (112 MB). Wisp
  builds the client with `static_discovery=True`, which reads only `calendar.v3.json`, so the
  spec keeps just that one. The self-check builds the client offline from it.

## D-051 Files & Share in the island (brief of 2026-10-13, part 4)
* **Files & Share replaces the Apps tab.** One search box finds apps (the app index, as before;
  apps can still be pinned from the right-click menu) and files. Voice "open X" is unchanged
  (the apps tools). Under the search box: the shelf, then Recent and Downloads.
* **File search: the Windows Search index first.** Microsoft documents several ways to query
  the index: Windows Search SQL through its OLE DB provider (directly or through ADO),
  ISearchQueryHelper (which turns Advanced Query Syntax into that SQL), and the search-ms
  protocol (which opens File Explorer, so it can't fill a list in the island).
  * Wisp sends Windows Search SQL through ADO (pywin32, already a dependency), with the
    documented connection string `Provider=Search.CollatorDSO;Extended
    Properties='Application=Windows';`.
  * `SELECT TOP 200 System.ItemPathDisplay, System.DateModified FROM SystemIndex WHERE
    SCOPE='file:<the user's profile>' AND System.FileName LIKE '%word%' …`, newest first.
    Quotes in what the person typed are doubled, and `%`, `_` and `[` are put in brackets so
    they match literally (both rules from the Windows Search SQL reference).
  * Results are ranked with rapidfuzz (WRatio on the name, plus a little for recent files), so
    word order and small typos are forgiven. When the exact query finds few files, a looser one
    (the first three letters of each word) feeds the same ranking. Two letters at least,
    180 ms after the last key.
  * On this PC a query answers in tens of milliseconds, where walking the folders takes
    seconds. If the index can't be queried (the Windows Search service is off), Wisp walks
    the main folders as the `search_files` tool always did, and says so.
* **The shelf.**
  * Files or folders dropped anywhere on the island (compact or open) are parked: the island
    opens on Files & Share as soon as a drag with files enters it, and counts as hovered for
    the drag, so it can't slide away mid-drag.
  * The shelf keeps references, not copies, in SQLite (newest first, at most 50), so it
    survives restarts. Items that were moved or deleted elsewhere show as missing. Renaming or
    moving from Wisp keeps them on the shelf.
  * Dragging out of the shelf or the lists carries file URLs, which Qt turns into CF_HDROP,
    so Explorer, mail and chat apps take them as files.
  * Thumbnails come from IShellItemImageFactory::GetImage without SIIGBF_ICONONLY, which
    returns the thumbnail and falls back to the icon. This runs on worker threads, as the docs
    require.
* **Recent and Downloads.** Recent is the Recent Items folder (as the `find_recent_files`
  tool). Downloads is FOLDERID_Downloads (SHGetKnownFolderPath, so a moved Downloads folder is
  found), newest first, without unfinished downloads (.crdownload, .part …) or desktop.ini.
* **Quick actions** (right-click): open, show in Explorer, copy (files on the clipboard as
  CF_HDROP), copy path, rename, move to…, share, send to phone, add to or remove from the
  shelf, and move to the Recycle Bin.
  * The Recycle Bin is the only delete. It asks first, uses SHFileOperation with FOF_ALLOWUNDO
    as the existing delete tool does, and refuses Windows and program folders and the
    personal top-level folders.
  * Rename and move never overwrite; they say what's in the way. Windows' naming rules are
    checked before renaming.
* **The Windows share sheet: IDataTransferManagerInterop.** A desktop app gets the
  DataTransferManager for its window with `GetForWindow`, fills the DataPackage in the
  DataRequested event, and opens the sheet with `ShowShareUIForWindow`. Nearby Sharing appears
  there when it's on in Windows.
  * PyWinRT doesn't project that interop interface, and its objects can't be built from a raw
    pointer (`_from` only casts between projected objects). So `wisp/winapi/winrt_abi.py`
    makes the calls itself with ctypes: HSTRINGs, RoGetActivationFactory, calls through vtable
    slots, polling IAsyncInfo for StorageFile.GetFileFromPathAsync, and small COM objects
    written in Python (the TypedEventHandler delegate, IIterable/IIterator<IStorageItem>).
    Exceptions in them return E_FAIL instead of a silent success.
  * Vtable slots and interface GUIDs were read from Windows' own metadata
    (C:\Windows\System32\WinMetadata, what the SDK headers are generated from) with
    `spikes/winmd_dump.py`. IIDs of generic instances use the WinRT type system's documented
    algorithm (a version 5 UUID of the type signature). It reproduces the published
    IIterable<String> IID, and the real IAsyncOperation<StorageFile> accepts the computed
    IID.
  * `spikes/share_probe.py --show` on this PC: the sheet opened for a real window and the
    DataRequested handler filled the package (S_OK).
  * The sheet is attached to the island's window and runs on the UI thread. The package is the
    file(s), read-only, titled with the file name.
* **Phone link: a short-lived web page on the home network, opened with a QR code.** Every rule
  from the brief, and where it is enforced:
  * *Private networks only.* The Network List Manager gives each connection's adapter,
    whether it is connected, and its network's category (Public 0, Private 1, Domain 2).
    WinRT `NetworkInformation.GetHostNames` gives each local IP with its adapter ID.
    The server binds to the IPv4 address (a private range, not loopback) of a connected
    adapter on a **Private** network, never 0.0.0.0, on a random free port.
    On a Public network it refuses and says how to make a home network Private. It isn't used
    on work (domain) networks either. This PC's own network is Public, so the link refuses
    here, as it should; the tests use 127.0.0.1.
  * *A long random one-time token.* `secrets.token_urlsafe(32)` (256 bits, the amount the
    Python docs call sufficient) starts every URL, compared with `hmac.compare_digest`.
    Anything else gets a bare 404. A new token per start, dead when the link stops.
    The first device to use it owns the link; another address gets 403.
  * *Stops after 10 minutes or when closed:* a timer, the Stop button, the
    `stop_phone_link` tool, quitting Wisp, or switching the island off.
  * *Every upload needs a click on the PC.*
    * The phone first asks with the name and size (`POST ask`). Accept/Decline appear in the
      tab, which opens by itself. No answer in 2 minutes counts as no.
    * Only then may the file be sent (`PUT upload/<id>`): once, from the same device, with
      exactly the size asked for, within a minute.
    * The body is never read before Accept. Three questions may wait at a time.
  * *Size limit setting:* Settings → Safety → Phone link (default 2048 MB, 1–20480). It is
    checked on the phone, at the ask, and against the upload's length.
  * *Safe names:* only the last component of the name is kept. Reserved and control
    characters are removed, device names (CON, NUL.txt, COM¹ …) get an underscore, and the
    name can't end in a space or period. Existing files are never overwritten
    ("name (2).ext"). Data goes to a hidden `.part` file, renamed only when complete; a short
    upload leaves nothing.
  * *Received files* go to Downloads\Wisp, followed by a banner.
  * *A clear indicator:* while the link runs, the island shows "Phone link" with the time
    left, and it can't auto-hide. The tab shows the QR code, the address, the countdown and
    Stop. Without the island (switched off) the link won't start.
  * *Nothing logged with the token:* request lines are never logged. The page sends
    `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, `X-Content-Type-Options:
    nosniff` and a Content-Security-Policy with a per-link script nonce. File names on the
    page are HTML-escaped. The download header's name is percent-encoded, so no CR/LF can
    reach a header.
  * *Python's http.server* is "not recommended for production" and "only implements basic
    security checks". Wisp uses BaseHTTPRequestHandler only, for three routes behind the
    token. It never uses SimpleHTTPRequestHandler (no directory listing or file paths from the
    phone), and serves only files the person offered, by number.
* **Windows Firewall prompt.**
  * The first time Wisp listens on the network, Windows Defender Firewall asks whether to allow
    it (Microsoft: a dialog "the first time the app … tries to communicate in the network"). Tick
    **Private networks** and allow.
  * If someone answers No, cancels, or isn't an administrator, Windows creates block rules and
    the phone can't connect. Allowing Wisp in Windows Security → Firewall & network protection →
    Allow an app through firewall fixes it.
  * Wisp never changes firewall rules itself: it installs per user, without administrator
    rights.
  * When run from source the prompt names python.exe.
* **Plain HTTP, and why.** A phone can't trust a certificate for an address on a home network:
  no public certificate authority issues one, and a self-signed one shows a full-page warning
  that teaches people to click through. So the link is plain HTTP, made safe enough for a few
  minutes on a home network by the rules above.
  * The trade-off: someone who can watch traffic on that Wi-Fi could see the files in
    transit and the address.
  * For anything sensitive, use the share sheet (Nearby Sharing), a cable, or a cloud drive.
    The README says so.
* **Voice.**
  * `share_file` opens the share sheet. It's safe tier: the person picks the destination.
  * `send_to_phone` is confirm-tier: the card says what the phone will be able to download.
    It can't be scheduled.
  * `stop_phone_link`.
  * "This" is the selection in the File Explorer window in front (Shell.Application.Windows(),
    the window's HWND, Document.SelectedItems(), FolderItem.Path), else the newest file on the
    shelf. "The file I just downloaded" is the newest finished file in Downloads. A name has
    to be a clear search match, otherwise Wisp asks which.
* **Packaging.** New dependencies: segno 1.6.6 (QR codes, BSD) and winrt-Windows.Networking
  and winrt-Windows.Networking.Connectivity 3.2.1. The Network List type library's comtypes
  wrapper is generated at build time, like UI Automation's. Self-check `files_share` covers
  a QR code, the network list (counts only), a StorageFile and the interop factory.
