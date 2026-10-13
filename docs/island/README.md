# The island

Recordings of the island's transitions (D-045…D-047). Each GIF is rendered from the real Island
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
| `stills/` | each state at rest: idle, listening, thinking, speaking, music, split, countdown, dictation, banner and expanded |

Regenerate the recordings and the stills with:

```bat
.venv\Scripts\python spikes\island_record.py docs\island
.venv\Scripts\python spikes\island_record.py docs\island\stills --stills
```
