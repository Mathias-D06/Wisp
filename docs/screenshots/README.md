# Screenshots

Before and after the UI polish (brief of 2026-10-13, part 2; D-042…D-044). Every file in
`before/` has a partner with the same name in `after/`.

| Folder | What it shows | How it was made |
|---|---|---|
| `before/` | The UI at commit 48bdfe8, before the polish | `spikes/render_ui.py` as it was at that commit |
| `after/` | The same screens after the polish, at this PC's scale (200 %) | `spikes/render_ui.py --docs --out docs/screenshots/after` |
| `after/scale-100`, `scale-125`, `scale-150` | The same screens rendered at 100 %, 125 % and 150 % display scale, to check sharpness | `spikes/render_ui.py --dpr 1.25 --docs --out …` |
| `after/onscreen/` | The console captured from the real screen: themed title bar and rounded corners. The window was inactive, so Mica shows its neutral fallback colour (Microsoft: Mica falls back to a neutral colour when the app is inactive) | `spikes/capture_onscreen.py docs/screenshots/after/onscreen` |

Notes:

* The renders are off-screen grabs. They set `WISP_NO_MICA=1` (an off-screen grab of a
  transparent Mica window has nothing behind it) and turn motion off, so each image shows the
  finished state rather than a frame of a fade.
* The on-screen capture saves a window only if nothing else covers it, and masks everything
  outside the window's rounded shape, so no other app's content ends up in the image. Settings
  was covered when this capture was taken, so it was skipped.
* All renders use a throwaway data folder with sample content. The Apps and Wallpaper tabs are
  left out because they would show this PC's installed apps and wallpaper.
* `--dpr` makes the render process per-monitor DPI aware and sets `QT_SCALE_FACTOR` so the
  output really is at the requested scale. Sizes at 100/125/150 %: the console is 560×520,
  700×650 and 840×780 pixels.
