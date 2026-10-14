# The island

Recordings of the island's transitions and tabs (D-045…D-051). Each GIF is rendered from the real Island
widget, inside a real Wisp with a throwaway data folder and sample content, by
`spikes/island_record.py`:

* the island is driven through its own event handlers on a simulated clock and rendered frame
  by frame with `QWidget.render`, at 50 fps (20 ms is the shortest frame delay GIF viewers
  honour);
* its windows never appear on screen, so no pointer can disturb a recording and nothing from
  this PC's screen ends up in an image;
* the backdrop is a plain gradient standing in for a wallpaper.

A real screen recording of your own is manual test MT-77.

| File | What it shows |
|---|---|
| `voice_flow.gif` | idle → listening (the waveform follows the voice) → thinking → speaking (the first words of the reply, output level bars) → idle, as one continuous shape |
| `split_music_and_voice.gif` | music (album art and an equaliser), then voice while the music plays: the island splits into the listening pill and a small circle with the album art, and merges back afterwards |
| `banner_routine_done.gif` | a routine finishes: the island drops into a banner, holds it about 3 s, then returns to idle by itself |
| `expand_and_collapse.gif` | hover (a slight grow), then the panel springs open with a small overshoot and its rows fade in one after another; then it collapses without overshooting |
| `interrupted_expand.gif` | a collapse that interrupts an expansion half-way: the shape keeps its momentum for a moment and turns smoothly, with no jump |
| `autohide_and_reveal.gif` | idle for 3 s (the shortest setting), the island slides up and fades away; the pointer (drawn) moves to the top-centre edge and rests in the reveal zone (dashed), and the island slides back down |
| `calendar_tab.gif` | the Calendar tab with a made-up calendar (`spikes/sample_calendar.py`, never a real account): the agenda (all-day events on top, each calendar's colour), the month view with colour dots, a day picked, back to the agenda |
| `files_and_share.gif` | the Files & Share tab with made-up files (`spikes/sample_files.py`; no files, apps or network of this PC): a file dropped on the island lands on the shelf, Downloads, a search, then the phone link with its QR code and a file from the phone waiting for Accept, and the collapsed island showing "Phone link" with the time left |
| `stills/` | each state at rest: idle, listening, thinking, speaking, music, split, countdown, dictation, banner and expanded |

Regenerate the recordings and the stills with:

```bat
.venv\Scripts\python spikes\island_record.py docs\island
.venv\Scripts\python spikes\island_record.py docs\island\stills --stills
```
