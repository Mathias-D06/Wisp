# Wisp

Wisp is a voice assistant for Windows 10 and 11 built on Google's Gemini Live API. You hold a
key, talk, and it answers out loud. It can also act on your PC: it opens apps, switches and
closes windows, clicks buttons by name, searches the web, manages files, to-dos, reminders and
routines, controls volume and music, and remembers facts you tell it. It also adds:

- **Dictation.** Hold Ctrl+Win, speak, and release. Wisp types clean text (no "um", and
  self-corrections applied) into whatever text box has focus.
- **Circle to Ask.** Hold Ctrl+Shift, draw a loop around something on screen and ask about it.
- **The Island.** A black pill at the top centre of the screen, like the iPhone's Dynamic
  Island. It changes shape to show what Wisp is doing: listening (with your voice's waveform),
  thinking, speaking (the start of the reply), dictating, the music that's playing, a
  countdown to your next reminder, and short banners when something happens. Two things at
  once split it into a pill and a small circle. Hover over it (or click it) and it opens into
  a panel with the conversation and a text box (Chat), quick controls, the music player,
  to-dos, stats, clipboard history, an app launcher, wallpapers and power options. It never
  takes the keyboard from the app you're typing in, clicks beside it reach the app
  underneath, and it hides while a full-screen app or game is in front. When nothing is
  happening it slides up out of view after a few seconds (Settings → General); rest the pointer
  on the top edge of the screen above its spot to bring it back. The Island works without an
  API key.

Everything Wisp stores stays on your PC, in `%APPDATA%\Wisp`.

Recordings of the Island's transitions are in [docs/island](docs/island/README.md).
On Windows 11 22H2 or later, the console and Settings use the Mica backdrop. On Windows 10 they
use a solid background. Before-and-after screenshots of the UI are in
[docs/screenshots](docs/screenshots/README.md).

## Requirements

- Windows 10 version 1809 or later, or Windows 11, 64-bit.
- A microphone and speakers. Use headphones if you turn on always-listening mode, so Wisp
  doesn't hear itself.
- A Gemini API key for the voice and AI features (see below). Without a key, the Island, music
  controls, app launcher and clipboard history still work.

## Install

1. Run `WispSetup-<version>.exe`. It installs for your Windows account only and needs no
   administrator rights. It goes to `%LOCALAPPDATA%\Programs\Wisp`, adds a Start-menu
   shortcut, and by default starts Wisp when you sign in. You can untick that during setup or
   later in Settings → General.
2. The installer isn't code-signed, so Windows SmartScreen may say it "protected your PC".
   Choose **More info → Run anyway** only if you got the file from a source you trust.
3. Wisp starts in the system tray (the coloured orb). With no API key stored, Settings opens
   on the General tab.

**Uninstall:** Settings → Apps → Installed apps → Wisp → Uninstall. This removes the program,
its shortcuts and the start-at-sign-in entry. Then it asks whether to delete your data as well
(settings, API key, memories, to-dos, routines, clipboard history and logs). The default answer
is **no**.

## Your Gemini API key

1. Create a key at <https://aistudio.google.com/api-keys>.
2. In Wisp, open Settings → **General**, paste the key and click **Save and test**. Wisp makes
   two small test calls, one for each configured model. If both succeed you'll see "Key works…".
   If a test fails you'll see why, and you can still use **Save without test**.
3. Wisp encrypts the key with Windows DPAPI for your user account. It is never written to a log
   and the app only ever shows a masked version.

> **UK, EEA and Switzerland.** Google's Gemini API terms allow only *Paid Services* for users
> in the European Economic Area, Switzerland and the United Kingdom. Use a key from a Google
> Cloud project with billing enabled.
> On the free tier elsewhere, Google may use what you send to improve its products, and human
> reviewers may read it. With billing enabled, Google says it doesn't use your prompts or
> responses that way. See <https://ai.google.dev/gemini-api/terms>. You must be 18 or older to
> use the Gemini API.

## Using Wisp

| Action | Default | Change in |
|---|---|---|
| Talk (push-to-talk) | hold **Alt+Win**, or click the orb | Settings → Hotkeys and audio |
| Dictate into the focused text box | hold **Ctrl+Win** | Settings → Hotkeys and audio |
| Circle to Ask | hold **Ctrl+Shift** and draw a loop with the left mouse button | Settings → Hotkeys and audio |
| Open or close the Island | hover it, click it, scroll down on it, or hold **Ctrl+Alt+Space**; Esc closes it | Settings → Hotkeys and audio |
| Type instead of talking | the Island's Chat tab (or tray → Open console, or "Open in window") | — |
| Play or pause music | click the right half of the Island's music pill | — |
| Dismiss a banner | swipe or scroll up on it (clicking opens what it's about) | — |
| Always listening (no hotkey) | the ear icon in the Island, the tray or the console | Settings → Hotkeys and audio |
| Mute the microphone | right-click the Island, or tray → Mute microphone | — |

A hotkey only fires when you hold its keys on their own for 250 ms (adjustable). Normal
shortcuts that share those keys, such as Ctrl+Win+→ or Ctrl+Shift+T, keep working.

Things to try:

- "Open Spotify", "switch to Outlook", "close Notepad", "search YouTube for lofi beats"
- "What's on my screen?", "click the Display button", "type hello into the search box"
- "Add a to-do to call the bank at 3 pm", "what's on my to-do list?"
- "Every weekday at 9, open Outlook and Teams", "what routines do I have?"
- "Remember that my sister's birthday is the 3rd of May", "forget my sister's birthday"
- "Turn the volume down", "pause the music", "turn on Night Light", "lock the PC"

**Settings** (tray → Settings…):

- **General:** API key, models, language, idle timeout, start with Windows, the Island (show
  it, which display it sits on, and whether it shrinks to a thin line when idle), clipboard
  history size, typing speed (used for Stats).
- **Loadout:** the voice (30 Gemini voices), personality (a preset or your own description),
  theme and accent colour, **Reduce motion**, and which skills Wisp may use. Wisp also turns its
  animations off when Windows' Animation effects setting is off.
- **Hotkeys and audio:** the four hold-to-use hotkeys (clashes are flagged as you type), hold
  time, microphone, speaker and always listening.
- **Safety:** see [Safety model](#safety-model).
- **Memories:** everything Wisp remembers. You can search, edit, pin and delete.
- **Routines:** scheduled tasks. You can switch them on or off, edit, run now and delete.
- **Action log:** every action Wisp took or refused.

## Scheduled tasks

When you ask for something later or on a schedule ("search Amazon for gift wrap on
10 November at 11am", "every morning at 9 open Unity and Spotify"), Wisp turns your request into
a routine. The routine stores the exact actions Wisp worked out, and at run time it replays them
without asking the AI model again. A step that needs the model at run time ("summarise my
to-dos") is sent to Gemini then.

Routines survive restarts. If Wisp wasn't running at the scheduled time:

- A **one-off** task still runs when Wisp starts within **12 hours** of its time. Otherwise it
  is reported as missed and switched off.
- A **repeating** task runs once at start-up if its last run was missed by **less than an
  hour**. Older missed runs are skipped and reported.

You get a notification after every run, with ✓ or ✗ for each step. A step that needs
confirmation shows a card and waits up to 10 minutes for your click; otherwise it is skipped.
Both grace periods can be changed in `settings.json` → `scheduler`.

To-do reminders are separate from routines: they fire at the to-do's due time. Any you missed
while Wisp was closed fire once when it starts.

## Safety model

Every action goes through one checkpoint in code, the dispatcher. Its decisions don't depend
on what the AI model says.

- **Safe actions** run at once: opening apps, searching, reading the time, changing the volume
  and so on.
- **Confirm actions** need your spoken "yes" or a click on the card. These include closing
  windows, deleting files (to the Recycle Bin only; Wisp never deletes permanently), deleting
  to-dos and routines, sleep, restart and shut-down, turning Wi-Fi off, and clicking buttons
  named like *buy, pay, send, delete, install*. Wisp checks that the "yes" came from you, in
  your own words or with a click. The model can't confirm on your behalf.
- **Disabled actions** are off until you switch them on in Settings → Safety. These are
  terminal commands (PowerShell, every command needs your yes) and raw mouse and keyboard
  control (clicks at screen positions and risky keys need your yes).
- **Untrusted content.** Text from the screen, files, web pages, window titles and terminal
  output is treated as data, never as instructions. For 5 minutes after Wisp reads any of it,
  every risky action asks first, including ones you chose to auto-approve. This also covers
  remembering or forgetting facts, typing and opening links.
- **Auto-approval** (Settings → Safety) can skip the question only for closing a window,
  deleting a to-do or turning Wi-Fi off. It never applies to routines, to the untrusted-content
  window, or to terminal, raw input, file deletion, power, risky clicks, opening programs or
  scheduling.
- **Limits Wisp respects.** It never tries to get past UAC prompts, the lock screen or the
  Ctrl+Alt+Del screen. It doesn't control apps running as administrator, because Windows blocks
  that (UIPI). It won't send keys or clicks to a full-screen game while anti-cheat software is
  running. In each case it tells you why.
- **Action log.** Every action, the decision about it and its result is logged. Keys are removed
  from the log, and it is viewable in Settings → Action log.

## Privacy and data

These are sent to Google's Gemini API, and only while you use the matching feature:

- your voice while you hold the talk key (or all the time in always-listening mode) and text
  you type in the console;
- a screenshot when you ask about your screen;
- the area you circle with Circle to Ask;
- dictation audio;
- the results of actions Wisp performs, and up to 8 of your remembered facts at the start of
  each conversation.

The voice connection closes after 5 idle minutes.

Everything else stays in `%APPDATA%\Wisp`:

- `settings.json` holds your settings;
- `secrets.bin` holds the API key, encrypted;
- `wisp.sqlite3` holds to-dos, memories, clipboard history, stats, the action log and routines;
- `jobs.sqlite3` holds the schedules;
- `logs\` holds the logs, with API keys removed.

Clipboard history skips anything that password managers mark as private. Wisp's own dictation
pastes are kept out of both Windows clipboard history and Wisp's.

## Troubleshooting

- **"Can't reach Google… retrying".** Check your internet connection. Wisp reconnects by itself
  and keeps the conversation.
- **Key errors.** Use Settings → General → Save and test. The message says whether the key is
  wrong, has no access to the model, or needs billing.
- **The Start menu opens after a hotkey,** or a hotkey clashes with another app. Choose a
  different chord in Settings → Hotkeys and audio.
- **Nothing happens in an administrator window.** Windows doesn't let normal apps control
  elevated apps. Use the app directly.
- **The Island disappeared.** It hides while a full-screen app, video or game is in front, and
  comes back when you leave full screen. Check Settings → General → Show the Island.
- **Windows look wrong (blank or see-through areas).** Set the environment variable
  `WISP_NO_MICA=1` and restart Wisp. Wisp then uses a solid background instead of Mica.
- **Logs.** Open them from Settings → Action log → Open log folder (`%APPDATA%\Wisp\logs`).
- **Checking an installation.** Run `"%LOCALAPPDATA%\Programs\Wisp\Wisp.exe" --self-check
  report.json`. This tests all bundled components without touching your data, and `report.json`
  lists the result of each check.

## Building from source

Requirements: Windows, Python 3.12, and Inno Setup 6 for the installer.

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m wisp                     & rem run from source
.venv\Scripts\ruff check src tests packaging     & rem lint
.venv\Scripts\python -m pytest                   & rem tests
.venv\Scripts\python packaging\build.py          & rem dist\Wisp\Wisp.exe + dist\WispSetup-<version>.exe
```

`packaging\build.py` does the following:

1. Draws the icon and writes `THIRD_PARTY_NOTICES.txt` from the installed packages.
2. Generates the UI Automation wrapper.
3. Runs PyInstaller with `packaging\wisp.spec`, producing a windowed one-folder build.
4. Runs the built exe's `--self-check`.
5. Compiles `packaging\installer.iss` with Inno Setup, if `ISCC.exe` is found. Pass
   `--no-installer` to skip this step.

Some tests are opt-in because they touch your clipboard, keyboard or Recycle Bin. Enable them
with `WISP_CLIPBOARD_TEST=1`, `WISP_INPUT_TEST=1` and `WISP_RECYCLE_TEST=1`. The tests never
switch your Wi-Fi, Bluetooth, Night Light, theme, volume or output device.
`.github\workflows\ci.yml` runs lint, the tests and the build on `windows-latest`.

Project notes:

- `PROGRESS.md` tracks status and the evidence for each requirement.
- `DECISIONS.md` records design decisions and any reliance on undocumented Windows behaviour.
- `SOURCES.md` lists every API and document the code relies on.
- `MANUAL_TESTS.md` has the hands-on checks, about 20 minutes' worth.

## Third-party software

Wisp bundles Python and open-source packages. Their names, versions, licences and home pages are
in `THIRD_PARTY_NOTICES.txt` in the installation folder. Qt for Python (PySide6) is used under
the LGPL v3, as separate, replaceable libraries. The icons are from
[Lucide](https://lucide.dev) (ISC; the icons Lucide derived from Feather are also MIT). Their
licence texts are in the same file and next to the icons.
