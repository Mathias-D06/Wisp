# Manual tests

Run on a real Windows 10/11 PC with a microphone and speakers or headphones. Target: about 20
minutes (MT-09 runs in the background while you do the others). Record pass/fail per step and
report any failure with the matching lines from `%APPDATA%\Wisp\logs\wisp.log`.

Setup: install with `WispSetup.exe` (or run `.venv\Scripts\python -m wisp`), open Settings →
General, paste your key and click **Save and test** (expect "Key works…").

## F1 Voice core

| ID | Steps | Expected |
|---|---|---|
| MT-01 | Hold **Alt+Win**, say "What time is it?", release. | Orb/tray turn green while held; Wisp answers aloud; console shows both lines. Start menu does not open. |
| MT-02 | Open the console (tray → Open console). Click the orb, say "Hello", click the orb again. | Same as MT-01. |
| MT-03 | Ask "Tell me a long story about a lighthouse". While it speaks, hold Alt+Win. | Speech stops immediately (within ~0.1 s). Release with a new question; it answers that. |
| MT-04 | Headphones on. Console → tick **Always listening**. Ask a question without any key, then talk over the answer. | It answers when you stop talking; talking over it stops playback. Untick afterwards. |
| MT-05 | In the console type "What is 12 times 7?" and press Enter. | Spoken and written answer "84". |
| MT-06 | Tray → **Mute microphone**, then hold Alt+Win. | Note "Microphone is muted in Wisp."; orb tooltip "Mic muted". Unmute afterwards. |
| MT-07 | Ask "Remember the code word is pineapple" (no tool needed). Turn Wi-Fi off for 20 s, then ask anything. Turn Wi-Fi on. | Console/tray show "Can't reach Google… Retrying in N s"; after Wi-Fi returns status shows Ready without restarting Wisp. Ask "What was the code word?" → "pineapple". |
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
| MT-22 | Open a web page with a chart or a word you don't know. Hold **Ctrl+Shift**, drag a loop around it with the left mouse button while asking "what is this?", release. | Screen dims with your loop drawn; after release Wisp answers aloud and a bubble with the same text appears beside the loop. |
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
| MT-29 | With **no API key** stored, start Wisp. Hover the pill at the top of the screen; open Apps, search "calc", press Enter; copy two bits of text, open Clipboard; play a song in Spotify or a YouTube tab. Hold Alt+Win. | Pill reads "Island ready · voice needs a key" with an **Add your API key** button. Apps launches Calculator; Clipboard lists both items (click one → pasting gives it back); music strip shows title, artist, moving progress, and ⏮ ⏯ ⏭ work. Alt+Win shows "Add your Gemini API key…". |
| MT-30 | Controls tab: drag volume, mute/unmute, pick another output device, toggle Wi-Fi, Bluetooth, Night Light, Dark mode; on a laptop drag brightness. | Each change happens in Windows (check the quick-settings flyout). If Night Light/Dark mode/output can't be switched, the chip opens the matching Settings page instead. Restore your settings afterwards. |
| MT-31 | Say "turn Wi-Fi off". | A confirmation card warns it disconnects Wisp; say "no" → nothing changes. |
| MT-32 | Open a password manager (e.g. Bitwarden, 1Password, KeePassXC), copy a password; then open the Clipboard tab and search for it. | The password is **not** in the list. Search finds normal items; "Clear all" asks first and empties the list. |
| MT-33 | Today tab: add "test to-do" with a due time; tick it; add another and delete it. Say "what's on my to-do list?" | Changes show at once; the voice answer matches the tab. "Coming up" lists routines from Settings → Routines. |
| MT-34 | Power tab: click Restart and choose **No**; click Lock. Wallpaper tab: click a thumbnail. | No restart; the PC locks (unlock again); the wallpaper changes (set it back afterwards). |

## Hotkeys

| ID | Steps | Expected |
|---|---|---|
| MT-10 | In Notepad press Ctrl+Win+Right then Ctrl+Win+Left (switch virtual desktops). Then hold Ctrl+Win for 1 s and release. | Desktop switching works normally. The 1 s hold starts dictation (after phase 4) and the Start menu does **not** open. |
