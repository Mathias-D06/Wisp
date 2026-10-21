# Wisp — final report

Updated 2026-10-21 · Version 0.1.0 · 12 phases (0–11), then four briefs and two rounds of fixes
from real use. The first version of this report was written on 2026-10-13, at the end of phase 11.

## What was built

Wisp is a Windows 10/11 voice assistant built on the Gemini Live API:

- **Voice core:** push-to-talk, always-listening mode, barge-in, reconnecting sessions and typed
  questions.
- **Computer control:** 48 tools in 16 skill groups.
- **The Island:** one morphing surface at the top of the screen, with tabs for Today, Calendar
  (Google Calendar), Files & Share (a shelf, search and a phone link), Screen, clipboard history
  and system controls. It hides itself when idle.
- **Screen Assist and Watch mode:** answers about the window in front, with a privacy blocklist.
- **Discreet mode:** a quiet look, text-only answers, no sounds or pop-ups.
- **Also:** dictation, Circle to Ask, to-dos, persistent routines, memory, a loadout, stats and a
  safety layer.
- **Packaging:** a per-user installer, a frozen `--self-check`, `--mic-check`, and CI on
  GitHub that also publishes a release from a version tag. MIT licence.

There are about 24,000 lines of application code in 171 files and 10,800 lines of tests in 47
test files.
- `README.md` describes the project; `docs/USER_GUIDE.md` covers installing and using it.
- `PROGRESS.md` holds the evidence behind each requirement, and `DECISIONS.md` the 60 design
  decisions.
- `SOURCES.md` lists every API and document the code relies on.
- `MANUAL_TESTS.md` holds the 124 hands-on checks.

The code is at github.com/Mathias-D06/Wisp.

## Status of the requirements (PROGRESS.md)

| Status | Count | Meaning |
|---|---|---|
| `[x]` done | 136 | Implemented, with automated evidence (tests, a spike, or a build, install or CI run). |
| `[~]` implemented, needs a person | 21 | Acceptance needs a real API key, a microphone, an account, a phone or a second monitor. |
| `[ ]` open | 0 | |

The items that need a person, with the manual test for each:

| Item | Manual test |
|---|---|
| F1.A 30-minute conversation; F1.B network unplugged | MT-09; MT-07 |
| F2.A computer control on a clean Windows 11 | MT-11…MT-14 |
| F3.2, F3.6 dictation quality in Notepad, a browser and VS Code | MT-18, MT-19 |
| F4.6 multi-monitor and scaling for Circle to Ask | MT-23 |
| F7.2 Wi-Fi, Bluetooth, Night Light, dark mode, output device; F7.A everything without a key | MT-30; MT-29 |
| S.2, S.A what reaches Gemini, 10 phrases on the laptop mic | MT-50, MT-51 |
| U.5, U.A Mica and the polished screens on this PC | MT-57, MT-59, MT-62, MT-63 |
| I.3, I.9, I.A the Island's activities, window behaviour and one fluid shape | MT-66, MT-70, MT-71, MT-74, MT-77 |
| P4.2b reveal from the top edge; P4.3 Calendar; P4.4 Files & Share | MT-79…MT-81; MT-82…MT-89; MT-90…MT-97 |
| S.1 Screen Assist; S.2 Watch mode; S.3 Discreet mode | MT-98…MT-106; MT-104, MT-105; MT-107…MT-114 |

The fixes of 2026-10-16 and 2026-10-20 add MT-115 and MT-119…MT-124.

## Evidence summary

- **Automated tests:** 682 passed, 3 skipped on this PC (opt-in tests that touch the clipboard,
  the keyboard or the Recycle Bin). The suite exits cleanly on three runs in a row. Ruff reports
  no problems.
- **CI on GitHub** (`windows-latest`), run 39449959046 for commit 1fac972, passed every step:
  - lint, then 677 passed and 4 skipped (no audio devices on the runner);
  - the PyInstaller build, and the frozen `--self-check` with every required check ok;
  - the Inno Setup compile, and the app and installer uploaded as artefacts.
- **Frozen self-check:** 15 checks, including Screen Assist's whole path. The real Windows calls
  choose and capture a window. The real google-genai client then sends it to a stand-in for
  Gemini on 127.0.0.1, which answers "503" once, so the retry runs too.
- **Installer, tested on this PC on 2026-10-13:** a silent per-user install, start at sign-in,
  and an uninstall that removed everything and kept user data. The current build was compiled
  from the same script.

## Bugs found and fixed

### By the final audit (2026-10-13)

1. **The Stats tab broke whenever settings were saved.** A combo box named `metric` hid Qt's
   virtual `QWidget::metric()`.
2. **Clipboard monitors could outlive their database** and raise inside a Qt slot at quit.
3. **A scheduler test was timing-sensitive** under CPU load.
4. **Check boxes in tables and lists were unstyled.**

### In real use, with your key and hardware

5. **D-038:** an 81 ms tap of the talk key sent an empty turn, and Google closed the session.
6. **D-039:** silence was transcribed as invented foreign phrases. A speech gate and native-format
   capture of the 4-channel microphone array fixed it.
7. **D-054:** Screen Assist failed every time with "RuntimeError". A temporary `genai.Client` was
   garbage-collected and closed its HTTP client before the request went out.
8. **D-055, D-060:** the installed exe got only silence from the microphone. Wisp now detects
   it and names the Windows setting to check. Measured with `--mic-check` from source and from
   the exe: about −95 dBFS on all four channels of the AMD array with every privacy switch on.
   The input itself is silent, for any program.
9. **D-056:** an empty window rectangle (0,0,0,0) reached the screenshot code. The desktop, the
   taskbar and empty, cloaked or off-screen windows are now skipped, and rectangles clamped.
10. **D-057:** Gemini's 503 "high demand". The SDK now retries 429/503 with backoff, the card
    says so, and an optional fallback model can answer.
11. **D-058:** a hotkey press ended in nothing. The microphone opened on the UI thread (1.6 s),
    and the quick look then waited on an overloaded Gemini with no timeout.
12. **D-059, CI:**
    - the build crashed printing "→" to a cp1252 pipe;
    - the test process crashed in PySide6's shutdown on windows left by two tests.

## Reliance on undocumented behaviour

Each item below is isolated behind one function and fails gracefully, usually by offering the
matching Settings page.

- **D-009:** a mask key stops the Start menu opening after a Win hold.
- **D-016:** `AttachThreadInput` is used as a fallback for bringing a window to the front.
- **D-018:** Store apps are launched and their icons found through the `shell:AppsFolder` path.
- **D-030:**
  - Night Light is switched through its registry blob. The layout was verified only against
    this PC's blob, and Wisp refuses to write any other layout.
  - Dark mode is switched by writing registry values.
  - The default output device is switched through `IPolicyConfig`.
- **D-052:**
  - Private-browsing windows are recognised by the words browsers put in their titles; the
    list is editable.
  - `QScreen.name()` matches the monitor's device name on this PC.
- **D-055:** Windows' microphone privacy switches are read, never written, from the registry
  values behind the Settings page.

## Known limitations

- The anti-cheat guard (D-035) is a heuristic. It only refuses keys and clicks to a full-screen
  window while a known anti-cheat client is running.
- The installer and exe are not code-signed, so SmartScreen warns on first run.
- The Gemini model names (`gemini-3.8-live`, `gemini-3.8-flash`, `gemini-3.8-flash-tts`) were
  checked against Google's documentation. All can be changed in Settings → General.
- Gemini returned 503 "high demand" to every real Screen Assist probe during these builds. The
  request shapes are verified against the SDK and a local stand-in, and the live check is MT-98.
- Free-tier Gemini keys allow Google to use what you send to improve its products, and human
  reviewers may read it. Users in the EEA, UK and Switzerland must use a billing-enabled key.
- This PC's built-in microphone array ("Microphone Array (AMD Audio Device)") delivers almost
  no signal (D-060). Check its mute key or switch and the AMD audio driver, or choose the headset
  in Settings → Hotkeys and audio. `Wisp.exe --mic-check report.json` measures it again.

## What you need to do next

1. Run the **Core run** in `MANUAL_TESTS.md`, then the extended cases as you use the features.
   These need your API key and microphone; some also need a Google account, a phone on a Private
   Wi-Fi network or a second monitor. Report any failure with the matching lines from
   `%APPDATA%\Wisp\logs\wisp.log`.
2. Fix or replace the microphone input above, then repeat MT-116 and MT-51.
3. For the next version, raise `version` in `pyproject.toml` and `wisp/__init__.py`, add
   `docs/releases/v<version>.md`, and push the tag `v<version>`. CI builds, tests and publishes
   the release.
4. Optionally, sign the exe and installer to avoid the SmartScreen warning.

Build everything with `.venv\Scripts\python packaging\build.py`. This produces
`dist\Wisp\Wisp.exe` and `dist\WispSetup-0.1.0.exe`. CI builds the same on every push.
