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

## Hotkeys

| ID | Steps | Expected |
|---|---|---|
| MT-10 | In Notepad press Ctrl+Win+Right then Ctrl+Win+Left (switch virtual desktops). Then hold Ctrl+Win for 1 s and release. | Desktop switching works normally. The 1 s hold starts dictation (after phase 4) and the Start menu does **not** open. |
