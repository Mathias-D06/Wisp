# Wisp — final report

Date: 2026-10-13 · Version 0.1.0 · 12 phases (0–11), one commit per phase.

## What was built

Wisp is a Windows 10/11 voice assistant built on the Gemini Live API:

- **Voice core:** push-to-talk, an orb you can click, always-listening mode, barge-in,
  reconnecting sessions and a text console.
- **Computer control:** 44 tools in 16 skill groups.
- **Dictation, Circle to Ask and the Island**, plus to-dos, persistent routines, memory,
  a loadout, stats and a safety layer.
- **Packaging:** a per-user installer and a CI workflow.

There are about 12,500 lines of application code and 4,800 lines of tests in 31 files. See
`README.md` for features and usage, `PROGRESS.md` for the evidence behind each requirement,
`DECISIONS.md` for the 37 design decisions, and `SOURCES.md` for every API and document the
code relies on.

## Status of the requirements (PROGRESS.md)

| Status | Count | Meaning |
|---|---|---|
| `[x]` done | 91 | Implemented, with automated evidence (tests, a spike, or a build or install run on this PC). |
| `[~]` implemented, needs a person | 9 | Acceptance needs a real API key, a microphone, other hardware or GitHub (listed below). |
| `[ ]` open | 0 | |

The items that need a person all sit in the **Core run** of `MANUAL_TESTS.md` (14 steps, about
20 minutes):

| Item | Why it can't be automated here | Manual test |
|---|---|---|
| F1.A 30-minute conversation | needs a key and real speech; simulated with 4 connections, 2 GoAways, a network blip and 6 tool calls | MT-09 |
| F1.B network unplugged | real network drop | MT-07 |
| F2.A computer control on a clean Windows 11 | real apps, voice and model | MT-11…MT-14 |
| F3.2, F3.6 dictation quality in Notepad, a browser and VS Code | model output quality | MT-18, MT-19 |
| F4.6 multi-monitor and scaling for Circle to Ask | second monitor | MT-23 (mapping unit-tested at 100–200 %) |
| F7.2 Wi-Fi, Bluetooth, Night Light, dark mode and output device changes | tests never change this PC's settings | MT-30 |
| F7.A everything works with no key | end-to-end check by eye | MT-29 |
| T.4 GitHub Actions | the repository has no remote yet; every step passed in a fresh venv and a fresh `git clone` | push |

## Evidence summary

- **Automated tests:** 312 passed, 3 skipped. The skipped ones are opt-in because they touch the
  clipboard, the keyboard or the Recycle Bin, and each was run once and passed. The suite passed
  3 times on an idle machine and 2 times with every CPU core busy. Ruff reports no problems.
- **Fresh `git clone` of the last commit:** pip install, lint, tests, PyInstaller build, the
  frozen `--self-check` (12/12 checks) and the Inno Setup compile all succeeded.
- **Installer, tested on this PC:**
  - A silent per-user install created the files, the Start-menu shortcut, the uninstall entry
    and the start-at-sign-in Run value.
  - The Run-key command started Wisp with no errors in its log.
  - The uninstaller removed everything, including a Run value written later by the app's own
    setting, and kept user data.
  - The machine's state before and after was recorded and matches.
- **Reference audit:** every test, file, manual-test ID and decision cited in PROGRESS exists.
  Every pinned dependency equals the installed version and its SOURCES entry.

## Bugs found and fixed by the final audit

1. **The Stats tab broke whenever settings were saved.** `StatsTab.metric` (a combo box) hid
   Qt's virtual `QWidget::metric()`. Every time the stylesheet was applied again, which happens
   on every settings save, Qt's call landed on the combo box and raised `TypeError` inside the
   Qt event loop. Fixed, with a regression test that fails on the old code.
2. **Clipboard monitors could outlive their database.** `ClipboardMonitor` connected to the
   global clipboard signal through a lambda, so a monitor was never released. A clipboard change
   after its database closed raised an exception inside a Qt slot. This happened in tests, and
   in the app it could happen at quit. Fixed with a bound-method connection, a `close()` that the
   app calls on quit, and a guarded store write. Regression tests added.
3. **A scheduler test was timing-sensitive.** It failed under CPU load; it now has margins safe
   for a slow CI runner.
4. **Check boxes in tables and lists were unstyled.** They now match the regular check boxes.

## Reliance on undocumented behaviour

Each item below is isolated behind one function and fails gracefully, usually by offering the
matching Settings page.

- **D-009:** a mask key stops the Start menu opening after a Win hold.
- **D-016:** `AttachThreadInput` is used as a fallback for bringing a window to the front.
- **D-018:** Store apps are launched and their icons found through the `shell:AppsFolder`
  path.
- **D-030:**
  - Night Light is switched through its registry blob. The layout was verified only against
    this PC's blob, and Wisp refuses to write any other layout.
  - Dark mode is switched by writing registry values.
  - The default output device is switched through `IPolicyConfig`.

## Known limitations

- The anti-cheat guard (D-035) is a heuristic. It only refuses keys and clicks to a full-screen
  window while a known anti-cheat client is running.
- The installer and exe are not code-signed, so SmartScreen warns on first run.
- The Gemini model names (`gemini-3.8-live`, `gemini-3.8-flash`) and voice names were checked
  against Google's documentation on 2026-10-12. Both models can be changed in Settings →
  General.
- When voice, personality or skills change, Wisp reconnects with the conversation's resumption
  handle. If the server refuses to resume with the new setup, Wisp starts a fresh session with
  the remembered facts (MT-36).
- Free-tier Gemini keys allow Google to use what you send to improve its products, and human
  reviewers may read it. Users in the EEA, UK and Switzerland must use a billing-enabled key
  (README).

## What you need to do next

1. Run the **Core run** in `MANUAL_TESTS.md` (about 20 minutes, needs your API key and a
   microphone). Report any failure with the matching lines from `%APPDATA%\Wisp\logs\wisp.log`.
2. Push the repository to GitHub so `.github/workflows/ci.yml` runs on `windows-latest`. Its
   desktop tests haven't been run on a hosted runner yet.
3. Choose a licence for Wisp. None has been chosen; third-party licences are listed in
   `THIRD_PARTY_NOTICES.txt`.
4. Optionally, sign the exe and installer to avoid the SmartScreen warning.

Build everything with `.venv\Scripts\python packaging\build.py`. This produces
`dist\Wisp\Wisp.exe` and `dist\WispSetup-0.1.0.exe`.
