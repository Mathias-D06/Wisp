# Manual tests

Run on a real Windows 10/11 PC with a microphone and speakers or headphones. Record pass/fail
per step and report any failure with the matching lines from `%APPDATA%\Wisp\logs\wisp.log`.

## Core run (about 25–30 minutes)

These steps check, on real hardware, what automated tests can't: the acceptance items marked
`[~]` in PROGRESS.md, plus install and uninstall. Do them in this order; the timers started in
step 4 run while you do the rest. Each step points to a case in the catalogue below.

| # | Case | What it checks | ~min |
|---|---|---|---|
| 1 | MT-46 | Install with `WispSetup-<version>.exe` (or run `.venv\Scripts\python -m wisp`). | 1 |
| 2 | MT-29 | Island, music strip, app launcher and clipboard history work with **no key** (F7.A). | 3 |
| 3 | — | Settings → General: paste your key, **Save and test** → "Key works…" (F11.2). | 1 |
| 4 | MT-25, MT-26 | Start a to-do reminder and a routine for 2–3 minutes from now; check them in step 11. | 1 |
| 5 | MT-50, MT-01, MT-03, MT-05 | Microphone test (speech heard, WAV sounds right); push-to-talk, barge-in, typed text (F1, D-039). | 3 |
| 6 | MT-11, MT-12, MT-14, MT-15 | Open apps, describe the screen, click by name, close with confirmation (F2.A). | 4 |
| 7 | MT-18, MT-20, MT-10 | Dictation into Notepad, not in Win+V history, Start menu stays shut (F3.2, F3.6). | 2 |
| 8 | MT-22 | Circle to Ask; on a second or scaled monitor if you have one (MT-23, F4.6). | 1 |
| 9 | MT-30 (volume, output, Night Light, dark mode) | System controls really change Windows (F7.2). | 1.5 |
| 10 | MT-07 | Network drop and recovery (F1.B). | 1.5 |
| 11 | MT-25, MT-26 (results) | The reminder and routine fired with notifications. | 0.5 |
| 12 | MT-35 | A memory survives a restart. | 1.5 |
| 13 | MT-40, MT-55 | Terminal is off by default (F12.3); a bad key shows a clear error and Retry (D-041). | 1.5 |
| 14 | MT-57, MT-58, MT-60 | The polished console, the orb's states and Reduce motion (D-042…D-044). | 2 |
| 15 | MT-65, MT-66, MT-67, MT-70, MT-71 | The island: one fluid voice flow, the split, a banner that leaves by itself, typing elsewhere never interrupted, clicks beside it reach the app (D-045…D-047). | 4 |
| 16 | MT-49 (answer **No**) | Uninstall is clean and keeps your data (D.1). | 1 |

**Extended (optional):** every other case below. MT-09 is the 30-minute conversation (F1.A); run
it in the background during the extended cases. MT-47 needs a sign-out and sign-in.

## Catalogue

## F1 Voice core

| ID | Steps | Expected |
|---|---|---|
| MT-01 | Hold **Alt+Win**, say "What time is it?", release. | The island turns into a green listening pill while held; Wisp answers aloud; the island's Chat tab shows both lines. Start menu does not open. |
| MT-02 | Open the console (tray → Open console). Click the orb, say "Hello", click the orb again. | Same as MT-01. |
| MT-03 | Ask "Tell me a long story about a lighthouse". While it speaks, hold Alt+Win. | Speech stops immediately (within ~0.1 s). Release with a new question; it answers that. |
| MT-04 | Headphones on. Hover the island until it opens (or open the console) → turn on **Always listening** (the ear icon). Ask a question without any key, then talk over the answer. | It answers when you stop talking; talking over it stops playback. Untick afterwards. |
| MT-05 | Hover the island until it opens; in the Chat tab click the text box, type "What is 12 times 7?" and press Enter. | Spoken and written answer "84". |
| MT-06 | Tray → **Mute microphone**, then hold Alt+Win. | Note "Microphone is muted in Wisp."; orb tooltip "Mic muted". Unmute afterwards. |
| MT-07 | Ask "Remember the code word is pineapple" (no tool needed). Turn Wi-Fi off for 20 s, then ask anything. Turn Wi-Fi on. | The island (banner) and tray show "Can't reach Google… Retrying in N s"; after Wi-Fi returns status shows Ready without restarting Wisp. Ask "What was the code word?" → "pineapple". |
| MT-08 | Settings → General → idle timeout 1 min. Ask "My favourite colour is teal." Wait 90 s. Ask "What's my favourite colour?" | Log shows "Idle — will reconnect when you talk"; the answer is teal (session resumed). |
| MT-09 | (background, 30 min) Every ~5 min ask "What time is it?" and once "open Notepad". At the end ask "What was the first thing I asked you today?" | Correct answer; log shows several "GoAway received" followed by "Live state ready" with no "error" state. |

## F2 Computer control (clean Windows 11)

| ID | Steps | Expected |
|---|---|---|
| MT-11 | Say "open Spotify" (install it first if needed); then "open notepad". | Spotify opens; Notepad opens. Saying "open visual studio" with two VS apps installed makes Wisp ask which one. |
| MT-12 | With a web page visible, say "What's on my screen?" | A correct one-or-two-sentence description of the page. |
| MT-13 | Say "search YouTube for lofi beats". | Default browser opens YouTube results for "lofi beats". |
| MT-14 | Open Windows Settings → System. Say "click the Display button" ("click the Settings button" in an app that has one). | The named element is clicked. |
| MT-15 | In Notepad with unsaved text say "close Notepad". | Confirmation card appears; say "yes" → Notepad asks to save (Wisp never discards work). Say "no" instead → nothing happens. |
| MT-16 | Create `Desktop\wisp-test.txt`, say "delete wisp-test.txt from my desktop". | Card asks first; after "yes" the file is in the Recycle Bin (restorable). |
| MT-17 | Run Task Manager as administrator, say "click the Processes tab in Task Manager". | Wisp explains that Windows blocks controlling admin windows; nothing is clicked. |

## F3 Dictation (copy something first, e.g. the word "clipboard-check")

| ID | Steps | Expected |
|---|---|---|
| MT-18 | Click into Notepad. Hold **Ctrl+Win**, say "um so let's meet at nine... no, ten tomorrow", release. | Pill shows Dictating → Transcribing → Inserted; Notepad gets "So let's meet at 10 tomorrow." (or similar, no "um", no "nine"). Start menu does not open. Press Ctrl+V: "clipboard-check" is pasted (clipboard restored). |
| MT-19 | Repeat MT-18 in a browser text box (e.g. a search field) and in VS Code. | Same result in both. |
| MT-20 | Win+V (clipboard history). | The dictated text is **not** in Windows clipboard history. |
| MT-21 | Hold Ctrl+Win briefly (< 0.2 s) and release; then press Ctrl+Win+D. | Nothing is recorded for the tap; Ctrl+Win+D creates a virtual desktop as usual (remove it with Ctrl+Win+F4). |

## F4 Circle to Ask

| ID | Steps | Expected |
|---|---|---|
| MT-22 | Open a web page with a chart or a word you don't know. Hold **Ctrl+Shift**, drag a loop around it with the left mouse button while asking "what is this?", release. | Screen dims with your loop drawn; after release Wisp answers aloud while the island shows the speaking state; when it finishes an "Answer" banner shows its first sentence (click it → the Chat tab with the whole answer). With the island switched off, a bubble beside the loop shows the answer instead. |
| MT-23 | With two monitors (or Settings → Display scale 150 %), repeat MT-22 on the second monitor. | The answer is about the circled content (correct crop on that monitor). |
| MT-24 | In a browser hold Ctrl+Shift for half a second, then press T (reopen tab). | The overlay disappears and the closed tab reopens; nothing is sent. |

## F5/F6 To-dos and routines

| ID | Steps | Expected |
|---|---|---|
| MT-25 | Say "add a to-do to call the bank in 2 minutes". Wait 2 minutes. | Wisp confirms; a "Reminder" notification appears at the time; the to-do shows in the Island's Today tab. Say "mark call the bank as done" → it disappears from Today. |
| MT-26 | Say "every day at <time two minutes from now>, open Notepad and Calculator". | Settings → Routines lists it with the next run; at the time both apps open and a "Routine done" notification lists two ✓ steps. |
| MT-27 | Say "search Amazon for gift wraps on 10 November at 11am", then "what routines do I have?", then "move the gift wrap search to 3pm", then "delete the gift wrap search" (say yes). | Each step is reflected in Settings → Routines; delete asks first. |
| MT-28 | Create a routine for 2 minutes from now, quit Wisp (tray → Quit), wait 3 minutes, start Wisp. | The routine runs once on start ("ran late" within the 12 h grace) and a notification says what was done. |

## F7 Island (run MT-29 first, before adding a key — or remove it in Settings temporarily)

| ID | Steps | Expected |
|---|---|---|
| MT-29 | With **no API key** stored, start Wisp. Hover the pill at the top of the screen; open Apps, search "calc", press Enter; copy two bits of text, open Clipboard; play a song in Spotify or a YouTube tab. Hold Alt+Win. | The idle pill shows a grey orb; hovering opens the panel with **Add your API key** in its header. Apps launches Calculator; Clipboard lists both items (click one → pasting gives it back); music strip shows title, artist, moving progress, and ⏮ ⏯ ⏭ work. Alt+Win shows a banner "Add your Gemini API key…". |
| MT-30 | Controls tab: drag volume, mute/unmute, pick another output device, toggle Wi-Fi, Bluetooth, Night Light, Dark mode; on a laptop drag brightness. | Each change happens in Windows (check the quick-settings flyout). If Night Light/Dark mode/output can't be switched, the chip opens the matching Settings page instead. Restore your settings afterwards. |
| MT-31 | Say "turn Wi-Fi off". | A confirmation card warns it disconnects Wisp; say "no" → nothing changes. |
| MT-32 | Open a password manager (e.g. Bitwarden, 1Password, KeePassXC), copy a password; then open the Clipboard tab and search for it. | The password is **not** in the list. Search finds normal items; "Clear all" asks first and empties the list. |
| MT-33 | Today tab: add "test to-do" with a due time; tick it; add another and delete it. Say "what's on my to-do list?" | Changes show at once; the voice answer matches the tab. "Coming up" lists routines from Settings → Routines. |
| MT-34 | Power tab: click Restart and choose **No**; click Lock. Settings → Loadout → Wallpaper → **Change…**: click a thumbnail. | No restart; the PC locks (unlock again); the wallpaper changes (set it back afterwards). |

## F8–F10 Memory, loadout, stats

| ID | Steps | Expected |
|---|---|---|
| MT-35 | Say "remember that my sister Hana's birthday is the 3rd of May". Tray → Quit, start Wisp again, ask "when is Hana's birthday?" | Wisp confirms it remembered; after the restart it answers 3 May. Settings → Memories lists the fact; edit it to 4 May, ask again → 4 May. Say "forget Hana's birthday" → the row disappears. |
| MT-36 | Settings → Loadout: voice **Puck**, personality **Minimal**, accent teal, Apply. Ask "what did I just ask you?" | The Island/console turn teal at once; the next reply uses the new voice and is very short, and it still knows the previous question (or, if resumption is refused, the log shows a fresh session). |
| MT-37 | Loadout → untick **Music and video controls**, Apply. Say "pause the music". | Wisp says it can't do that (skill switched off); the Island's music buttons still work. Tick it again afterwards. |
| MT-38 | Dictate one sentence (MT-18) and run one voice command. Island → Stats. | Today and This week show the words, a time-saved figure and 1 command; the 7-day chart has today's bar. |

## F11/F12 Settings and safety

| ID | Steps | Expected |
|---|---|---|
| MT-39 | Settings → Hotkeys and audio: set Dictation to `alt+win` (same as push-to-talk). Then set it to `ctrl+alt+d`, pick your headset microphone, Apply. Hold Ctrl+Alt+D in Notepad and dictate. | The clash is shown at once and Apply refuses it; after the change dictation works with the new chord and the headset mic. Set it back to `ctrl+win` afterwards. |
| MT-40 | Say "run the command get-date". | Wisp says terminal commands are switched off (Settings → Safety). |
| MT-41 | Settings → Safety: tick **Allow terminal commands**, Apply (Loadout → "Run terminal commands" is now ticked). Say "use PowerShell to list the files in my Downloads folder". | A card shows the exact command; after "yes" Wisp summarises the list. Settings → Action log shows the call with "allow (confirmed…)". Untick the switch afterwards. |
| MT-42 | Settings → Safety: tick **Allow raw mouse and keyboard control**. Open Notepad and say "look at my screen, then press control N", then "type hello world", then "click the File menu at its position on the screenshot". | Ctrl+N opens a new tab without asking; the text is typed; the click asks first and then hits File. Untick the switch afterwards. |
| MT-43 | Run Task Manager as administrator and focus it. With raw input allowed, say "press F5". | Wisp explains that Windows blocks controlling administrator windows; nothing happens. |
| MT-44 | Open Notepad and say "in 2 minutes, click the File menu in Notepad". Lock the PC (Win+L) before it runs; unlock after 3 minutes. | The routine's notification shows ✗ with "Windows is showing a secure screen…"; Wisp did not interact with the lock screen. |
| MT-45 | Settings → Safety → tick "Close a window…", Apply. Say "close Notepad" (with unsaved text). Then say "what's on my screen?" followed by "close Calculator". | The first close happens without a card (Notepad still asks to save); the second asks first because the screen was just read. |

## Installer

| ID | Steps | Expected |
|---|---|---|
| MT-46 | Run `WispSetup-<version>.exe` and keep the defaults. | No administrator prompt. Wisp installs to `%LOCALAPPDATA%\Programs\Wisp`, appears in the Start menu, and starts with Settings → General open (no key yet). |
| MT-47 | Sign out of Windows and sign back in. | The Wisp orb appears in the tray and the Island at the top, with no window opening. |
| MT-48 | With Wisp running, run the installer again. | Setup asks you to close Wisp first, then upgrades in place; settings and memories are kept. |
| MT-49 | Settings → Apps → Wisp → Uninstall; answer **Yes** to "Also delete your Wisp data". Reinstall, set a key, uninstall again and answer **No**. | First time: `%LOCALAPPDATA%\Programs\Wisp`, the Start-menu entry, the start-at-sign-in entry (Task Manager → Startup apps) and `%APPDATA%\Wisp` are gone. Second time: the program is gone but `%APPDATA%\Wisp` remains. |

## Speech recognition (D-039…D-041)

| ID | Steps | Expected |
|---|---|---|
| MT-50 | Settings → Hotkeys and audio → **Test microphone**; say a short sentence during the 3 s. Click **Open folder** and play the newest `mic-test-….wav`. | The result starts "Speech heard" and shows a level around −20 to −35 dBFS, the device format and per-channel levels. The WAV sounds like you: normal speed and pitch, not chipmunked, slowed down or noisy. |
| MT-51 | Tick **Save the audio sent to Gemini**, Apply. Hold **Alt+Win** and say, one turn each: "What time is it?", "Open Spotify", "Search YouTube for lofi beats", "Add a to-do to call the bank at 3 pm", "What's on my to-do list?", "Turn the volume down a little", "Pause the music", "Remember that my sister's birthday is the 3rd of May", "What's the weather like for a walk today?", "Close Notepad". | 10/10 appear in the console as one "You:" line each, in English, and are answered in English. Each `voice-….wav` in the debug folder sounds normal. Untick the setting afterwards. |
| MT-52 | Press **Alt+Win** and start saying "what time is it" at the same moment, without waiting. Open the newest `voice-….wav`. | The recording starts with "what"; the first word isn't cut off. |
| MT-53 | Tap Alt+Win quickly; in the island's Chat tab (or the console) click **Talk** once, say "what time is it", click **Talk** again; then double-click the orb, speak, click the orb once. | The tap sends nothing (no hint either, because a quick chord tap never fires). The Talk click starts listening ("click Talk again to send") and the second click sends. The double-click starts listening only once (it doesn't start and stop at once). |
| MT-54 | Mute the microphone with your laptop's mute key (or cover it and stay silent), hold Alt+Win for 2 s and release. | "Wisp didn't hear any speech, so nothing was sent…" appears; no "¿Qué?"-style reply. Unmute afterwards. |
| MT-55 | Settings → General: note your key, paste `AIzaInvalidKeyForTesting0000000000000000`, click **Save without test**. Hold Alt+Win and speak. Then put your real key back with **Save and test**. | A red "Voice problem" banner says "Google rejected this API key…" (never "None"); clicking it retries. The island's panel and the console show a **Retry** button. The log has a line with the exception type, code and reason. After restoring the key, Retry or talking works again. |
| MT-56 | Say "from now on please answer in French", then "what time is it", then "switch back to English". | Wisp switches to French only when asked, and back when asked. |

## UI polish (D-042…D-044)

| ID | Steps | Expected |
|---|---|---|
| MT-57 | Open the console from the tray. Hover the two icons at the top right, click each, then click them again. Send a typed message and scroll the transcript. | On Windows 11 22H2 or later the background is Mica: while the window is active a faint tint of your wallpaper shows through (when you click elsewhere it turns a plain neutral colour, as Windows intends), the title bar matches the theme and the corners are rounded. The icons have tooltips ("Always listening …", "Mute microphone") and turn the accent colour while on. Messages are rows labelled "You" and "Wisp", one per turn. The scrollbar shows only while the pointer is over the transcript. Text and icons are crisp. |
| MT-58 | Watch the orb in the console header: leave it idle, then hold **Alt+Win** and speak, release, and let Wisp answer. | Idle: a slow, gentle glow. Listening: green, growing with your voice. Thinking: a soft amber pulse. Speaking: your accent colour, moving with Wisp's voice. Nothing else on screen moves while idle. |
| MT-59 | Hover the Island until it opens, switch between its tabs, then move the pointer away. Start dictation (hold **Ctrl+Win**) and Circle to Ask once. | The Island grows smoothly (about a fifth of a second), its contents appear once it has opened, tabs cross-fade quickly, and it shrinks back when you leave. Dictation shows in the island ("Dictating…" with a level meter, then "Inserted N words"); the circle hint is a small pill at the top of the dimmed screen and your loop is drawn as an outline. No flicker or jumps. |
| MT-60 | Settings → Loadout → turn on **Reduce motion**, Apply; repeat MT-59 and watch the orb. Turn it off. Then Windows Settings → Accessibility → Visual effects → turn off **Animation effects** (Windows 10: Ease of Access → Display → **Show animations in Windows**) and repeat. Turn it back on. | With either switch off, the island changes shape at once (no spring) and its content just crossfades, nothing else fades, toggles snap, and the orb is still (it still changes colour with its state). Everything animates again once both are back on. |
| MT-61 | Settings → Loadout → Theme **Light**, Apply; look at the console, Settings, Island and a confirmation card (ask Wisp to close Notepad). Switch back to Dark. | Every window turns light at once, including the title bar; all text is easy to read, and buttons in the accent colour have readable text. The island stays black, like a hardware notch. |
| MT-62 | Windows Settings → System → Display → Scale: 125 %, then 150 %; open the console, Settings and the Island at each. Put the scale back afterwards. | Text, icons and the orb stay sharp (no blurry or pixelated icons), nothing is clipped and the Island fits at the top of the screen. |
| MT-63 | Look at the tray icon, the console's taskbar button and Alt+Tab entry, and `Wisp.exe` in Explorer with Large icons. If you have Windows 10 (or set the environment variable `WISP_NO_MICA=1` and restart Wisp), open the console there too. | The orb is crisp and recognisable at every size. Without Mica the console has a solid near-black background (light in Light theme) and looks otherwise the same. |

## Island (D-045…D-047)

| ID | Steps | Expected |
|---|---|---|
| MT-64 | Look at the top centre of the screen. Hover the black pill, keep the pointer still for a moment, then move it away. Click the pill; press **Esc**. Scroll down on the pill; scroll up on its top edge. Press **Alt+Tab** and look at the taskbar. | Idle: a small black capsule with an orb. Hover makes it grow slightly; after about 0.3 s it flows open into the panel (Chat first) and closes about half a second after you leave. Click, Esc and scrolling open and close it. It is one continuous shape: no flicker, no window frame, no taskbar button, not in Alt+Tab. |
| MT-65 | Hold **Alt+Win**, ask "what time is it?", release, and let Wisp answer. | One fluid shape: idle → a green listening pill whose waveform follows your voice → an amber "Thinking…" pulse → the first words of the reply with level bars while it speaks → back to idle. No jumps or flashes between states. |
| MT-66 | Play music in Spotify or a YouTube tab. Click the right half of the island once, then again. Then hold **Alt+Win** and ask something while the music plays. | The pill shows the album art (or a music icon), the title and bars that move with the music. Clicking its right half pauses and resumes without opening the island. While you talk, the island splits: the listening pill plus a small circle with the album art beside it; afterwards they merge back into the music pill. |
| MT-67 | Say "remind me in one minute to stretch" (or run a routine with Run now in Settings → Routines). Wait. When the next banner appears, hover it for a while; for another, swipe up on it. | At the time (reminders are checked every 20 s), the island drops down into a card with an icon, a title and one line, stays about 3 s (longer while the pointer is on it), then shrinks back to idle by itself. Clicking a reminder opens the Today tab; swiping or scrolling up dismisses it. |
| MT-68 | Add a to-do with a reminder 8 minutes from now. Wait up to 20 s. | The island shows a calendar icon, the to-do and a countdown (7:59 … ) that ticks every second; at 0:00 the reminder banner takes over. |
| MT-69 | Dictate a sentence into Notepad (hold **Ctrl+Win**). Then use Circle to Ask once (MT-22). | Dictation appears in the island: "Dictating…" with a level meter, "Transcribing…", then "Inserted N words" for a moment. The circle answer plays in the island's speaking state, then an "Answer" banner; clicking it opens Chat with the answer. |
| MT-70 | Open Word (or Notepad) and keep typing while you (a) hold Alt+Win and ask something, (b) let a banner appear (MT-67), (c) hover the island until it opens and move away. Then click into the island's Chat text box, type "what is 2 + 2" and press Enter; press **Esc**. | Every key you type lands in Word; the caret never leaves it, whatever the island does. Clicking the island's text box (and only that) takes the keyboard; after Esc the island closes and Word has the keyboard again. |
| MT-71 | Put a window under the top centre (a browser's tab strip works). Click 5–10 px to the left, right and just below the idle pill; repeat while a banner shows. | Every click reaches the app underneath (a tab is selected, the window activates). Clicks on the shape itself go to the island. |
| MT-72 | Right-click the island; try each item. Hold **Ctrl+Alt+Space**, then again. Change the island hotkey in Settings → Hotkeys and audio. | The menu has Settings…, Mute microphone, Open in window and Quit Wisp, and each works. The hotkey opens and closes the island; a changed hotkey works at once. |
| MT-73 | Play a YouTube video full screen (press F), then leave full screen. Press F11 in a browser, then F11 again. Maximize a normal window. If you have a game, start it full screen. | The island disappears within about a second of going full screen and comes back after. A maximized window doesn't hide it. Reminders that fire meanwhile come as Windows notifications. |
| MT-74 | With two displays at different scaling (for example 100 % and 150 %): Settings → General → Island on **The display with the pointer**, Apply. Move the pointer to the other display and wait two seconds; hover and open the island there. Set it back to **Main display**. | The island moves to the display with the pointer while idle, is sharp and the right size at that display's scaling, and opens and closes normally there. Back on Main display it stays on the main display. |
| MT-75 | Settings → General: check **Hide the Island when nothing is happening** is ticked, set **Hide after** to 3 s, Apply; then set it back to 6 s. Untick **Keep it visible while music plays** and play music; tick it again. | At 3 s the idle island slides up and fades sooner; back at 6 s it waits longer. With the box unticked, playing music no longer keeps it on screen; ticked, the music pill stays. |
| MT-76 | Open the island; click **Open in window**. Then Settings → General → untick **Show the Island**, Apply; dictate once, use Circle to Ask once, click the tray icon. Tick it again. | The console opens with the same conversation. With the island off, dictation uses the small bottom pill, the circle answer appears in a bubble beside the loop, notifications come from Windows and the tray click opens the console. |
| MT-77 | Optional: record the screen while doing MT-65 and MT-67 (Win+Shift+R starts Snipping Tool's screen recording). | Your recording matches the GIFs in `docs/island` (those are rendered from the same widget off-screen). |

## Brief of 2026-10-13, part 4

| ID | Steps | Expected |
|---|---|---|
| MT-78 | In a terminal: `.venv\Scripts\python -m wisp`. Open the island's Today tab, tick the due-time icon and open the date's calendar; open every Settings page. Do it at 100 % and 150 % display scaling. | The terminal shows no "QFont::setPointSize" warning. Text looks the same size as before at both scalings. |
| MT-79 | Leave Wisp idle (no music, nothing happening) with a browser maximized. Wait 6 s. Then click the browser tabs and the window's title bar near the top centre. | The island slides up out of view and fades. While it's hidden, every tab and the title bar right under where it was work normally. |
| MT-80 | With the island hidden: move the pointer quickly across the top edge of the screen (over browser tabs); then move it to the very top edge above the screen's centre and leave it there. Hover the island when it appears, then move away. Repeat at 125 %, 150 % or 175 % scaling, and with two displays (Settings → General → Island on **The display with the pointer**). | A quick pass does nothing. Resting at the top-centre edge for a moment brings the island back down smoothly. It stays while the pointer is on it, and slides away about 6 s after you leave. It works the same at every scaling and on whichever display the pointer is on. |
| MT-81 | With the island hidden: hold **Alt+Win** and ask something; let a reminder fire; hold **Ctrl+Alt+Space**; ask Wisp to close Notepad (a confirmation card); play a YouTube video full screen and leave full screen. | Voice, the reminder banner and the hotkey bring it back at once; it stays while the confirmation card waits. In full screen it stays hidden, and after leaving full screen it stays hidden (it doesn't pop back up). |

## Google Calendar (D-050)

Needs a Google account and about 10 minutes for MT-82 the first time.

| ID | Steps | Expected |
|---|---|---|
| MT-82 | Connect Google Calendar. (1) Open https://console.cloud.google.com/ and create a project, for example "Wisp". (2) APIs & Services → Library → **Google Calendar API** → Enable. (3) Google Auth platform → Branding: app name "Wisp", your email as support and developer contact. Audience: **External**; under Test users add your own Google address. (4) Clients → Create client → **Desktop app** → Create → **Download JSON**. (5) In Wisp: Settings → Accounts → **Import client JSON…** and pick the file. (6) Click **Connect Google Calendar**, sign in in the browser, accept ("Google hasn't verified this app" → Continue, because it's your own app in Testing). | After importing, the client shows as the start of its client ID followed by "…apps.googleusercontent.com", and Connect is enabled. The browser ends on "Wisp is connected…" and you can close it. Settings shows "Connected · N calendars · read-only" with your calendars ticked as in Google Calendar. Importing a "Web application" client instead shows an error asking for a Desktop app client. |
| MT-83 | Open the island → **Calendar**. Compare with calendar.google.com. Switch to **Month**, click a day, use the arrows. Click an event. In Settings → Accounts untick a calendar. | The agenda lists today and the next 7 days with the right times (UK time, summer or winter), all-day events first, each with its calendar's colour. The month shows dots on days with events; a click lists that day. Clicking an event opens it in Google Calendar in the browser. An unticked calendar's events disappear from the tab. |
| MT-84 | Add an event in Google Calendar on the web, 2 minutes from now. In Wisp's Calendar tab click the sync button (or wait 5 minutes). Then disconnect the PC from the internet, restart Wisp and open the tab. Reconnect the internet. | The new event appears after the sync. Offline, the tab still shows everything with "Last synced …" (or "Offline · synced …" after a failed attempt). Back online it syncs again within 5 minutes. |
| MT-85 | Settings → Accounts → heads-up **10 min**, Apply. Create an event 12 minutes from now on a shown calendar and sync. Wait. | About 10 minutes before the event the island shows its title with a countdown, like a reminder. At 0 the countdown goes. Set heads-up to Off: no countdown for events. |
| MT-86 | Hold **Alt+Win**: "what's on my calendar tomorrow?" Then: "add dentist to my calendar tomorrow at 3 pm for half an hour". | Wisp reads tomorrow's events from the calendar. Adding an event says Wisp isn't allowed to add events yet (read-only connection). |
| MT-87 | Settings → Accounts → tick **Let Wisp add events**, click **Reconnect** and accept the extra permission in the browser. Ask again: "add dentist to my calendar tomorrow at 3 pm for half an hour". Click **Allow** on the card. Then ask to add something to a calendar someone else shared with you. | The status reads "can add events". The card says “add “Dentist” to <your calendar>, <day> 15:00–15:30”; after Allow the event is in Google Calendar and in the tab at once. A calendar you don't own is refused with a message; nothing is added. |
| MT-88 | Go to https://myaccount.google.com/permissions and remove Wisp's access. In Wisp click the Calendar tab's sync button. Then click **Reconnect** and sign in. Finally Settings → Accounts → **Disconnect**. | After removing access the tab shows "Google sign-in expired or was revoked…" with a Reconnect button, and the cached events stay visible. Reconnect restores syncing. Disconnect shows "Not connected.", the tab asks to connect, and Wisp no longer appears on the Google permissions page (refresh it). |
| MT-89 | Settings → Loadout → Appearance → Wallpaper → **Change…**, pick a picture. Then hold **Alt+Win**: "what wallpapers do I have?", "set my wallpaper to <one of them>". | The Island has no Wallpaper tab. The dialog changes the desktop picture and the row shows the new file name. By voice, Wisp lists the pictures and sets the one you named. |

## Hotkeys

| ID | Steps | Expected |
|---|---|---|
| MT-10 | In Notepad press Ctrl+Win+Right then Ctrl+Win+Left (switch virtual desktops). Then hold Ctrl+Win for 1 s and release. | Desktop switching works normally. The 1 s hold starts dictation (after phase 4) and the Start menu does **not** open. |
