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

## Hotkeys

| ID | Steps | Expected |
|---|---|---|
| MT-10 | In Notepad press Ctrl+Win+Right then Ctrl+Win+Left (switch virtual desktops). Then hold Ctrl+Win for 1 s and release. | Desktop switching works normally. The 1 s hold starts dictation (after phase 4) and the Start menu does **not** open. |
