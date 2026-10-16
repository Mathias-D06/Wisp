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
| Open or close the Island | hover it, click it, scroll down on it, or hold **Ctrl+Alt+I**; Esc closes it | Settings → Hotkeys and audio |
| Ask about the window in front (Screen Assist) | hold **Ctrl+Alt+Space** and ask, or tap it for a quick look | Settings → Hotkeys and audio |
| Watch mode on or off | hold **Ctrl+Alt+W** | Settings → Hotkeys and audio |
| Discreet mode on or off | hold **Ctrl+Alt+D** (or the Island's or the tray's menu) | Settings → Hotkeys and audio |
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
- "What's on my calendar tomorrow?", "add lunch with Ana on Friday at 1 pm"
- "Send this to my phone", "share the file I just downloaded"
- "What's on my screen?", "explain this", "check this", "keep an eye on my screen"
- "Go discreet", "back to normal"
- "Set my wallpaper to the mountain one"

**Settings** (tray → Settings…):

- **General:** API key, models, language, idle timeout, start with Windows, the Island (show
  it, which display it sits on, whether it hides when nothing is happening and after how long,
  and whether music keeps it visible), clipboard history size, typing speed (used for Stats).
- **Accounts:** Google Calendar (see [Google Calendar](#google-calendar)).
- **Loadout:** the voice (30 Gemini voices), personality (a preset or your own description),
  theme and accent colour, **Reduce motion**, the desktop wallpaper, and which skills Wisp may
  use. Wisp also turns its
  animations off when Windows' Animation effects setting is off.
- **Hotkeys and audio:** the four hold-to-use hotkeys (clashes are flagged as you type), hold
  time, microphone, speaker and always listening.
- **Safety:** see [Safety model](#safety-model).
- **Memories:** everything Wisp remembers. You can search, edit, pin and delete.
- **Routines:** scheduled tasks. You can switch them on or off, edit, run now and delete.
- **Action log:** every action Wisp took or refused.

## Google Calendar

The Island's Calendar tab shows today and the next 7 days (or a month), and you can ask Wisp
what's on and have it add events. It uses your own Google Cloud project, so nothing goes through
anyone else's servers:

1. Open [console.cloud.google.com](https://console.cloud.google.com/) and create a project.
2. APIs & Services → Library: enable the **Google Calendar API**.
3. Google Auth platform → Branding: give the app a name and your email. Audience: **External**,
   and add your own Google address under **Test users**.
4. Clients → Create client → **Desktop app** → Download JSON.
5. In Wisp: Settings → Accounts → **Import client JSON…**, then **Connect Google Calendar** and
   sign in in your browser. Google warns that it hasn't verified the app: it's your own, so
   continue.

Wisp asks only to *see* your calendars and events. To let it add events, tick **Let Wisp add
events** and connect again: Google then asks to let it create, change and delete events on
calendars you own (Wisp only ever adds them, and only after you click Allow on its card).

Wisp keeps a copy of the next six months so the tab works offline, and syncs every 5 minutes.
**Disconnect** revokes Wisp's access at Google and deletes the copy and the sign-in.

**Why it asks you to reconnect every week.** While your project's publishing status is
**Testing**, Google ends the sign-in after 7 days. Wisp then shows Reconnect in the Calendar
tab, and your events stay visible until you do. To avoid it:

- keep Testing and reconnect weekly (a click and a sign-in); or
- Google Auth platform → Audience → **Publish app** ("In production"). Sign-ins then don't
  expire after 7 days. Until Google verifies the app you'll see an "unverified app" warning
  when you sign in; see Google's help on publishing status and verification; or
- with a Google Workspace account, choose the **Internal** audience, which has no 7-day limit.

The heads-up in the Island (the next event's countdown, 10 minutes before by default) is set
in Settings → Accounts.

## Screen Assist and Watch mode

**Screen Assist** answers questions about what's on your screen. Hold **Ctrl+Alt+Space** over
any window and ask ("what does this error mean?"), or just tap it for a quick look: Wisp
explains what's shown and points out anything wrong, unclear or worth acting on. You can also
ask by voice: "what's on my screen?", "explain this", "check this", "what do you think?".

The answer opens in the Island's **Screen** tab and Wisp reads the gist aloud:

- the thumbnail shows exactly what was sent;
- **Explain**, **Review** (proofreading, bugs, numbers), **Summarise** and **Reply** ask again
  about the same screenshot. **Reply** drafts an answer to the email or message on screen, and
  **Insert** pastes it where you were reading. Wisp never sends anything;
- **More** gives the detailed version, **Copy** copies it, and code comes in a monospace block;
- follow-ups ("and the second one?") continue the conversation. Wisp takes a new screenshot
  only if the window changed.

**Watch mode** (off by default; **Ctrl+Alt+W**, "keep an eye on my screen", or the Watch
button on the Screen tab) looks at the window in front every 20 seconds. It speaks up only when
something is wrong: an error dialog, a failed build or test, an obvious typo. A look is sent to
Gemini only when the window has changed. While it's on, the Island shows "Watching" with the
time left (hover and click **Stop**), and the tray icon gets a dot. It stops by itself after 30
minutes. The Stats tab shows how much it used and an estimated cost.

**Privacy.**

- Screenshots stay in memory for the current question and are never saved. (The exception is
  Settings → Hotkeys and audio → "Save the audio and screenshots sent to Gemini", for
  troubleshooting.)
- Wisp **never looks at** password managers, private (Incognito/InPrivate) browser windows,
  or banking and payment pages. It says "I don't look at that window" instead, and on a
  whole-screen look it paints those windows over. Edit the list in Settings → Screen Assist.
- Text on screen is treated as data, never as instructions. Screen Assist can't click, type or
  send anything, and anything Wisp is asked to do afterwards needs your confirmation.
- Every capture is listed in Settings → Action log (window title and time, not the image).

## Discreet mode

For lectures, libraries and meetings. Wisp keeps working, but much less noticeably:

- the Island becomes a thin grey line (or a small dot), half see-through, with no glow or
  colour, at the top centre or in a top corner. It still slides away and comes back from the
  top edge above it;
- replies are **text only**: no speaking and no sounds. Answers appear on a small, quiet card
  under the line that fades after 12 seconds (it stays while you point at it). **Speak it**
  reads one aloud, and with headphones you can keep spoken replies on;
- notifications become a short pulse of the line; only errors and confirmations open up.
  Windows notifications are muted too;
- push-to-talk only: always listening pauses until you leave Discreet mode.

Turn it on from Settings → Discreet mode, the Island's or the tray's menu, **Ctrl+Alt+D**, or
say "go discreet". It can also turn itself on during Google Calendar events. Its settings are a
separate profile: turning it off brings back your normal Wisp exactly as before. Watch mode and
the phone link still show a small coloured dot, and Wisp's windows stay normal windows (screen
sharing and recording show them).

## Files & Share

The Island's **Files & Share** tab (where Apps used to be):

- **Search** apps and files in one box. Files come from the Windows Search index, so results
  are instant and small typos are forgiven.
- **The shelf:** drop files or folders on the Island to park them; drag them out again into
  Explorer, an email or a chat. The shelf keeps a link to the file, not a copy, and survives
  restarts.
- **Recent** files and your newest **Downloads**.
- **Right-click** a file to open it, show it in Explorer, copy it or its path, rename it, move
  it, share it, send it to your phone, or move it to the Recycle Bin. Wisp never deletes
  permanently.
- **Share…** opens the Windows share sheet: Nearby Sharing (switch it on in Settings → System →
  Nearby sharing, or System → Multitasking on newer builds), Mail and other apps.

**Phone link.** The phone button (or "send this to my phone") shows a QR code. Scan it with
your phone's camera and the phone can download what you sent and send files back.

- It only works on a **Private** network. If Windows treats your home Wi-Fi as Public, change
  it: Settings → Network & internet → Wi-Fi (or Ethernet) → your network → Network profile
  type → Private network.
- The first time, **Windows Firewall** asks whether to allow Wisp: tick Private networks and
  allow. If you said no, allow it later in Windows Security → Firewall & network protection →
  Allow an app through firewall.
- Every file from the phone needs your **Accept** in the Island. Files arrive in
  `Downloads\Wisp`. The size limit is in Settings → Safety.
- The link stops after **10 minutes** or when you click Stop. While it's open the Island
  shows "Phone link" with the time left.
- The link uses plain HTTP on your home network: someone able to watch your Wi-Fi traffic
  could see the files in transit. For anything sensitive use Nearby Sharing, a cable or a
  cloud drive.

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

Screen Assist and Watch mode send a screenshot of the window you ask about (or, in Watch
mode, of the window in front when it has changed) with your question to Gemini. Screenshots
aren't stored by Wisp.

If you connect Google Calendar, Wisp talks to Google's Calendar API directly with your own
project's sign-in. When you ask about your calendar, the events Wisp reads out also go to Gemini
as the tool's result.

Everything else stays in `%APPDATA%\Wisp`:

- `settings.json` holds your settings;
- `secrets.bin` holds the API key, encrypted;
- `google_client.bin` and `google_token.bin` hold your Google OAuth client and sign-in,
  encrypted, if you connect Google Calendar;
- `wisp.sqlite3` holds to-dos, memories, clipboard history, stats, the action log, routines,
  the copy of your calendar, the shelf (links to files, not the files) and Gemini usage counts
  (no content);
- `jobs.sqlite3` holds the schedules;
- `logs\` holds the logs, with API keys removed.

Clipboard history skips anything that password managers mark as private. Wisp's own dictation
pastes are kept out of both Windows clipboard history and Wisp's.

## Troubleshooting

- **"Can't reach Google… retrying".** Check your internet connection. Wisp reconnects by itself
  and keeps the conversation.
- **Key errors.** Use Settings → General → Save and test. The message says whether the key is
  wrong, has no access to the model, or needs billing.
- **"Wisp got only silence from the microphone".** The microphone delivered nothing at all, not
  even room noise, so Wisp sent nothing. If the notice names a switch, turn it on in Windows
  Settings → Privacy & security → Microphone. Otherwise check, in order: "Let desktop apps access
  your microphone" in that page; a mute key or switch on the laptop; the input chosen in Windows
  Settings → System → Sound → Input and in Wisp's Settings → Hotkeys and audio. Test microphone
  shows what Wisp hears. The log's "Mic levels" line shows each channel and the switches.
- **The Start menu opens after a hotkey,** or a hotkey clashes with another app. Choose a
  different chord in Settings → Hotkeys and audio.
- **Nothing happens in an administrator window.** Windows doesn't let normal apps control
  elevated apps. Use the app directly.
- **The Island disappeared.** When nothing is happening it slides up out of view: rest the
  pointer at the top edge of the screen above its centre to bring it back. It also hides while
  a full-screen app, video or game is in front. Check Settings → General → Show the Island.
- **The phone can't open the link.** The PC's network must be Private, the phone on the same
  Wi-Fi, and Wisp allowed through Windows Firewall on Private networks (see Files & Share).
  Some guest networks keep devices apart; use your main Wi-Fi.
- **Calendar says "Reconnect".** See [Google Calendar](#google-calendar): in Testing status Google
  ends the sign-in after 7 days.
- **Windows look wrong (blank or see-through areas).** Set the environment variable
  `WISP_NO_MICA=1` and restart Wisp. Wisp then uses a solid background instead of Mica.
- **Logs.** Open them from Settings → Action log → Open log folder (`%APPDATA%\Wisp\logs`).
- **Checking an installation.** Run `"%LOCALAPPDATA%\Programs\Wisp\Wisp.exe" --self-check
  report.json`. This tests all bundled components without touching your data, and `report.json`
  lists the result of each check. It includes Screen Assist's whole path, with a stand-in for
  Gemini on this PC: nothing is sent anywhere.

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
