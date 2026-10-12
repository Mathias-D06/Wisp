# Wisp — progress tracker

Resume rule: a fresh session reads this file, then `DECISIONS.md` and `SOURCES.md`, then continues at
"Next step". Commit after every phase.

Legend: `[x]` done with evidence · `[~]` implemented, automated evidence where possible, but the
acceptance step needs real hardware/API key and is listed in `MANUAL_TESTS.md` (not yet run) ·
`[ ]` not done.

## Status

- Current phase: 2 — audio, Live session, tool framework, safety layer
- Next step: verify sounddevice + Live docs details, then write `wisp/audio/*`, `wisp/live/*`,
  `wisp/tools/*` (registry, dispatcher, safety, confirmations)
- Environment: Windows 11, Python 3.12.10 venv in `.venv`, Git 2.55, Inno Setup 6.7.3 (per-user,
  `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`).
- Commands: `.venv\Scripts\python -m pytest`, `.venv\Scripts\ruff check src tests`,
  `.venv\Scripts\python -m wisp`.

## Phases

- [x] 0 Setup: docs read, tracking files, repo, venv, ruff, pytest (commit 8f65be6)
- [x] 1 Skeleton, tray, settings, secrets — `wisp/app.py`, `settings.py`, `keystore.py`,
  `logging_setup.py`, `db.py`, `startup.py`, `single_instance.py`, `ui/tray.py`, `ui/settings/*`;
  tests `test_settings.py`, `test_keystore.py`, `test_db_and_startup.py`, `test_settings_ui.py`
- [ ] 2 Audio + Live session + tool framework + safety layer
- [ ] 3 F2 computer-control tools
- [ ] 4 F3 dictation
- [ ] 5 F4 Circle to Ask
- [ ] 6 F5 to-dos + F6 scheduler
- [ ] 7 F7 Island
- [ ] 8 F8 memory, F9 loadout, F10 stats
- [ ] 9 F12 hardening
- [ ] 10 Packaging, installer, CI
- [ ] 11 Final audit

## Acceptance criteria

### F1 Voice core
- [ ] F1.1 Push-to-talk via configurable hotkey
- [ ] F1.2 Push-to-talk by clicking the orb
- [ ] F1.3 Optional always-listening mode using Live API voice activity detection
- [ ] F1.4 Answers aloud (24 kHz PCM playback)
- [ ] F1.5 Calls tools mid-conversation
- [ ] F1.6 Barge-in: playback stops immediately when interrupted
- [ ] F1.7 Context window compression enabled
- [ ] F1.8 Session resumption with latest handle
- [ ] F1.9 GoAway handled by transparent reconnect
- [ ] F1.10 Backoff on network errors with clear status
- [ ] F1.11 Idle sessions close after configurable timeout and reconnect on next use
- [ ] F1.12 Text console
- [ ] F1.13 Mic-mute toggle
- [ ] F1.A Accept: 30-minute conversation with tool calls never drops context
- [ ] F1.B Accept: network unplug shows clear status, then recovers

### F2 Computer-control tools
- [ ] F2.1 open_app with fuzzy match over Start Menu shortcuts + Store apps index
- [ ] F2.2 close / switch / minimise windows
- [ ] F2.3 web_search on Google, YouTube, Amazon in default browser
- [ ] F2.4 look_at_screen (screen or active window)
- [ ] F2.5 UI Automation: list elements, click by name, type into field, scroll
- [ ] F2.6 Open files/folders, find recent files
- [ ] F2.7 Delete goes to Recycle Bin only and requires confirmation
- [ ] F2.A Accept: "open Spotify", "search YouTube for lofi beats", "what's on my screen?",
  "click the Settings button" on clean Windows 11

### F3 Dictation
- [ ] F3.1 Hold Ctrl+Win (configurable) records; release sends audio to Gemini
- [ ] F3.2 Returns only clean intended text (fillers, false starts, self-corrections resolved)
- [ ] F3.3 Pastes into focused field and restores previous clipboard
- [ ] F3.4 Ctrl+Win does not open Start menu or trigger virtual-desktop shortcuts
- [ ] F3.5 Triggers only when no other key pressed and held > ~250 ms
- [ ] F3.6 Accept: works in Notepad, a browser text box and VS Code
- [ ] F3.7 Words dictated tracked for Stats

### F4 Circle to Ask
- [ ] F4.1 Hold Ctrl+Shift (configurable) shows full-screen transparent overlay
- [ ] F4.2 Freehand loop drawn while speaking
- [ ] F4.3 On release: crop loop bounding box, send image + question
- [ ] F4.4 Answer aloud plus short text bubble
- [ ] F4.5 No interference with normal Ctrl+Shift+key shortcuts
- [ ] F4.6 Works across multiple monitors and display scaling

### F5 To-do list
- [ ] F5.1 Add, complete, delete, list by voice
- [ ] F5.2 Add, complete, delete, list in UI
- [ ] F5.3 Optional due time with reminder toast
- [ ] F5.4 Shown in Island "Today" tab

### F6 Scheduled tasks and routines
- [ ] F6.1 One-off jobs
- [ ] F6.2 Recurring jobs
- [ ] F6.3 Model emits structured schedule_task; resolved tool calls stored and replayed without model
- [ ] F6.4 Jobs persist across restarts
- [ ] F6.5 Missed-job policy defined and documented
- [ ] F6.6 Toast after each run
- [ ] F6.7 List, edit, delete by voice
- [ ] F6.8 List, edit, delete in UI
- [ ] F6.9 Start with Windows setting

### F7 Island (works without API key)
- [ ] F7.1 Pill fixed top-centre, always on top, expands on hover or scroll
- [ ] F7.2 Controls tab: volume, output device, Wi-Fi, Bluetooth, Night Light, dark mode, brightness
- [ ] F7.3 Today tab (to-dos, upcoming jobs)
- [ ] F7.4 Stats tab
- [ ] F7.5 Clipboard tab
- [ ] F7.6 Apps tab
- [ ] F7.7 Wallpaper tab
- [ ] F7.8 Power tab (sleep/restart/shut down with confirmation)
- [ ] F7.9 Music strip: title, artist, progress, play/pause/next/previous
- [ ] F7.10 Clipboard history: last N text + image, searchable, re-copy, clear
- [ ] F7.11 Clipboard skips content marked excluded by password managers
- [ ] F7.A Accept: with no API key, Island, music strip, app launcher, clipboard history work and AI
  features show "add your key"

### F8 Memory
- [ ] F8.1 remember / recall / forget tools backed by SQLite
- [ ] F8.2 Only the few most relevant facts injected at session start
- [ ] F8.3 View, edit, delete all memories in Settings

### F9 Loadout
- [ ] F9.1 Voice slot (Gemini prebuilt voice)
- [ ] F9.2 Personality slot (presets + custom)
- [ ] F9.3 Appearance slot (theme + accent)
- [ ] F9.4 Skills slot (tool groups enabled)
- [ ] F9.5 Gap decision recorded

### F10 Stats
- [ ] F10.1 Words dictated, time saved (stated typing speed), commands run, routines executed — per
  day and per week

### F11 Settings and secrets
- [x] F11.1 API key stored with DPAPI, never logged or shown in full — tests
  `test_keystore.py::test_dpapi_round_trip`, `::test_mask_never_reveals_middle`,
  `::test_redacting_filter_removes_keys`, `::test_redacting_filter_cleans_tracebacks`; Settings shows
  only `mask(key)` (`ui/settings/general_page.py`)
- [ ] F11.2 Key validated with a test call on save
- [ ] F11.3 README note: UK/EEA/Swiss users need a billing-enabled key
- [ ] F11.4 Settings: hotkeys with conflict detection, mic + speaker device, idle timeout, start with
  Windows, risky-tool toggles, model name, language

### F12 Safety
- [ ] F12.1 Risk tiers enforced in dispatcher
- [ ] F12.2 Confirm tier needs spoken "yes" or a click
- [ ] F12.3 Terminal + raw mouse/keyboard disabled by default behind Settings toggle
- [ ] F12.4 Screen/web/file text is untrusted; confirm-tier after reading it always asks
- [ ] F12.5 Action log of every tool call, viewable in Settings
- [ ] F12.6 Never bypasses UAC, secure desktop, lock screen, anti-cheat; explains the limit

### Testing, packaging, definition of done
- [ ] T.1 Unit tests: dispatcher, safety tiers, scheduler parsing + persistence, memory, clipboard store,
  settings (Windows-only tests marked)
- [ ] T.2 Integration tests with fake Live session replaying scripted tool calls
- [ ] T.3 MANUAL_TESTS.md runnable in ~20 minutes
- [ ] T.4 GitHub Actions on windows-latest: lint + tests + PyInstaller exe
- [ ] D.1 Installer installs, launches at login, uninstalls cleanly
- [ ] D.2 Stub/placeholder grep returns nothing
- [ ] D.3 README complete
- [ ] D.4 Final report

## Log

- 2026-10-12: Phase 0 started. Installed Python 3.12.10 (py install manager), Git, Inno Setup (winget),
  with user approval. Project at `C:\Users\mathi\Documents\Wisp`.
