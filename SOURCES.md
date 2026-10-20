# Sources

Every external API, library function, Windows API or config field the code relies on, with what the
source confirmed. "SDK source" means the installed package's code (official repo/PyPI artefact), read
from `.venv`. Dates are when checked.

## Gemini / google-genai

| URL | Confirmed | Checked |
|---|---|---|
| https://ai.google.dev/gemini-api/docs/live | Live input: raw 16-bit PCM, 16 kHz, little-endian; output: raw 16-bit PCM, 24 kHz, little-endian; images JPEG ≤ 1 FPS | 2026-10-12 |
| https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk | `client.aio.live.connect(model=, config=)`; `send_realtime_input(audio=types.Blob(data=, mime_type="audio/pcm;rate=16000"))`; `send_realtime_input(video=types.Blob(..., "image/jpeg"))`; `send_realtime_input(text=)`; receive loop reading `server_content.model_turn.parts[].inline_data.data`; `input_transcription` / `output_transcription`; `tool_call.function_calls` → `send_tool_response(function_responses=[types.FunctionResponse(id=, name=, response=)])`; model `gemini-3.8-live`; `response_modalities: ["AUDIO"]` | 2026-10-12 |
| https://ai.google.dev/gemini-api/docs/live-api/tools | `tools=[{"function_declarations": [...]}]` in config; `behavior: "NON_BLOCKING"` and `scheduling` INTERRUPT/WHEN_IDLE/SILENT; model does not respond until the tool response is sent (blocking default) | 2026-10-12 |
| https://ai.google.dev/gemini-api/docs/live-api/session-management | `ContextWindowCompressionConfig(sliding_window=SlidingWindow())`; `SessionResumptionConfig(handle=)`; `session_resumption_update.new_handle/.resumable`; `go_away.time_left`; `generation_complete`; connection lifetime ~10 min; handles valid 2 h after last termination; audio-only session 15 min without compression, unlimited with compression | 2026-10-12 |
| https://ai.google.dev/gemini-api/docs/live-api/capabilities | `speech_config.voice_config.prebuilt_voice_config.voice_name`; native audio models pick language automatically and do not support `language_code` (restrict via system instruction); `realtime_input_config.automatic_activity_detection` fields (`disabled`, sensitivities, `prefix_padding_ms`, `silence_duration_ms`, 500–800 ms recommended); `activity_start` / `activity_end` only with automatic VAD disabled; `audio_stream_end`; `server_content.interrupted` → stop playback and clear queue; `input_audio_transcription: {}`, `output_audio_transcription: {}` | 2026-10-12 |
| https://ai.google.dev/api/live | realtime audio/video/text are concurrent streams (no cross-stream ordering); `audioStreamEnd` only with automatic VAD enabled; `activityHandling` default = START_OF_ACTIVITY_INTERRUPTS (barge-in); `turnCoverage` default for Gemini 3.1+ = TURN_INCLUDES_AUDIO_ACTIVITY_AND_ALL_VIDEO; compression `triggerTokens` default 80 % of context, `targetTokens` default trigger/2; `resumable=false` while generating or running function calls; GoAway `timeLeft`; client content interrupts generation and mixing with realtime input has no guarantees | 2026-10-12 |
| probe with the user's key, 2026-10-13 (`gemini-3.8-live`, push-to-talk config) | an activity with no audio closes the session: WebSocket 1007, reason "Precondition check failed."; 32 ms, 96 ms and 1 s of audio are fine; after the fix, the app's own LiveSessionManager handled a tap (nothing sent), an image-only short turn (answered) and a 1 s turn (answered) with no error | 2026-10-13 |
| https://ai.google.dev/gemini-api/docs/models | Live models: `gemini-3.8-live` (stable, default Live model), `gemini-3.8-live-extended-thinking`; legacy `gemini-3.1-flash-live-preview`. General: `gemini-3.8-flash` (stable), `gemini-3.5-flash-lite` | 2026-10-12 |
| https://ai.google.dev/gemini-api/docs/speech-generation | 30 prebuilt voice names (Zephyr, Puck, Charon, Kore, Fenrir, Leda, Orus, Aoede, Callirrhoe, Autonoe, Enceladus, Iapetus, Umbriel, Algieba, Despina, Erinome, Algenib, Rasalgethi, Laomedeia, Achernar, Alnilam, Schedar, Gacrux, Pulcherrima, Achird, Zubenelgenubi, Vindemiatrix, Sadachbia, Sadaltager, Sulafat) | 2026-10-12 |
| https://ai.google.dev/gemini-api/docs/function-calling | `parameters` uses an OpenAPI subset (`type`, `properties`, `required`, `enum`, `items`); multimodal function responses documented for Gemini 3 generateContent only — not for Live | 2026-10-12 |
| SDK source `google/genai/live.py` (google-genai 2.29.0) | `AsyncSession.receive()` stops after each complete turn (must be re-entered in a loop); `send_realtime_input` accepts exactly one of media/audio/audio_stream_end/video/text/activity_start/activity_end; `send_tool_response` requires `id`; `ConnectionClosed` is re-raised as `errors.APIError` with the close code; docstring warns against interleaving `send_client_content` with `send_realtime_input` | 2026-10-12 |
| SDK `google.genai.types` introspection (spike: `spikes/genai_types.py`) | Field names of `LiveConnectConfig`, `LiveServerMessage`, `LiveServerContent` (`interrupted`, `turn_complete`, `input_transcription`, `output_transcription`, `generation_complete`), `LiveServerToolCallCancellation.ids`, `LiveServerGoAway.time_left`, `LiveServerSessionResumptionUpdate.new_handle/resumable`, `ContextWindowCompressionConfig.trigger_tokens/sliding_window`, `SlidingWindow.target_tokens`, `AutomaticActivityDetection` fields, `FunctionDeclaration.parameters/behavior`, `FunctionCall.id/args/name` | 2026-10-12 |

## Windows, Qt and Python (phase 1)

| URL | Confirmed | Checked |
|---|---|---|
| https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata | DPAPI user scope (same user, same PC), optional entropy must match on decrypt, `CRYPTPROTECT_UI_FORBIDDEN`, prompt struct deprecated (we pass None) | 2026-10-12 |
| https://mhammond.github.io/pywin32/win32crypt__CryptProtectData_meth.html | `CryptProtectData(DataIn, DataDescr, OptionalEntropy, Reserved, PromptStruct, Flags) -> bytes` | 2026-10-12 |
| spike `spikes/dpapi_roundtrip.py` | `CryptUnprotectData` returns `(description, data)`; wrong entropy raises `pywintypes.error` 13 | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/setupapi/run-and-runonce-registry-keys | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, value = command line ≤ 260 chars, runs at each logon | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw | named mutex + `ERROR_ALREADY_EXISTS` for single instance | 2026-10-12 |
| https://doc.qt.io/qt-6/qsystemtrayicon.html | `showMessage(title, msg, icon, msecs)` shows a Windows notification; `activated` with `Trigger`/`Context`; `setContextMenu` does not take ownership | 2026-10-12 |
| spike `spikes/sqlite_fts5.py` | bundled SQLite 3.49.1 has FTS5 and `bm25()` | 2026-10-12 |
| SDK source `google/genai/errors.py`, `models.py` | `APIError.code/.status/.message`; `ClientError`, `ServerError`; `models.get(model=)`, `models.generate_content(model=, contents=, config=)` | 2026-10-12 |
| https://docs.python.org/3/library/logging.handlers.html#rotatingfilehandler | `RotatingFileHandler(maxBytes, backupCount, encoding)` | 2026-10-12 |

## Audio, Live session, hotkeys (phase 2)

| URL | Confirmed | Checked |
|---|---|---|
| https://python-sounddevice.readthedocs.io/en/latest/api/streams.html | stream parameters; callbacks run at real-time priority and must not block; output callback must fill all of `outdata` (zeros if empty) | 2026-10-12 |
| spike `spikes/audio_formats.py` | MME/DirectSound default devices accept 16 kHz mono int16 in and 24 kHz out; WASAPI/WDM-KS reject them (PaErrorCode -9997) | 2026-10-12 |
| https://raw.githubusercontent.com/google-gemini/gemini-skills/main/skills/gemini-live-api-dev/SKILL.md | official Google repo: realtime input for all user input incl. text; extended-thinking Live model requires NON_BLOCKING; compression for sessions > 15 min; clear playback on interruption; headphones to avoid echo | 2026-10-12 |
| https://github.com/googleapis/python-genai/issues/1720 | lead only (not relied on alone): text sent inside manual activity markers triggers a reply immediately | 2026-10-12 |
| spike `spikes/live_config_build.py` | lower-case OpenAPI types in dict declarations parse to `Type.OBJECT`, etc.; the SDK maps compression, resumption, VAD, transcription, tools into the `setup` message | 2026-10-12 |
| SDK `types.LiveServerMessage._from_response` (introspection) | `go_away.time_left` is a duration string such as `"12.5s"`; base64 audio decoded to bytes; `Transcription.finished` bool | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelkeyboardproc | return nonzero to block a key; call `CallNextHookEx` otherwise; hook runs on the installing thread, which needs a message loop; exceeding `LowLevelHooksTimeout` (max 1000 ms) silently removes the hook (Win 7+) | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-kbdllhookstruct | fields vkCode, scanCode, flags, time, dwExtraInfo; `LLKHF_INJECTED` = 0x10 | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowshookexw | WH_KEYBOARD_LL = 13 is global only; pass a module handle (NULL hMod with thread 0 may fail); call `UnhookWindowsHookEx` before exit | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput | `SendInput(cInputs, pInputs, cbSize)`; UIPI silently blocks input to higher-integrity windows; keyboard state is not reset | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes | all VK values used; 0xE8 is "Unassigned" | 2026-10-12 |
| spike `spikes/hook_probe.py` | on this PC the hook installs, sees injected keys, ignores keys tagged with Wisp's dwExtraInfo signature; `sizeof(INPUT)` = 40 on x64 | 2026-10-12 |

## Computer-control tools (phase 3)

| URL | Confirmed | Checked |
|---|---|---|
| https://learn.microsoft.com/en-us/powershell/module/startlayout/get-startapps | Start-menu apps have Name + AppID (AUMID) | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/configuration/store/find-aumid | Apps folder `shell:::{4234d49b-0245-4df3-b780-3893943456e1}` via Shell.Application; item `path` = AUMID | 2026-10-12 |
| spike `spikes/apps_folder.py` | 195 apps (53 Store) in 1.3 s; `Folder.ParseName(AUMID)` round-trips; verbs include Open | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow | foreground restrictions; failing call flashes the taskbar | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute | `DWMWA_EXTENDED_FRAME_BOUNDS` (9, screen-space RECT), `DWMWA_CLOAKED` (14) | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_elevation | `TokenIsElevated` | 2026-10-12 |
| https://doc.qt.io/qt-6/highdpi.html | Qt 6 is Per-Monitor DPI Aware V2 by default; QScreen geometry is device-independent; QImage/QPixmap physical; screens can form "islands" | 2026-10-12 |
| https://github.com/BoboTiG/python-mss + installed `mss/windows/gdi.py` | MIT; `MSS().grab(dict)` → `.rgb`, `.size`; mss calls `SetProcessDpiAwareness(2)` itself | 2026-10-12 |
| spike `spikes/uia_probe.py` | comtypes generates `UIAutomationClient` from UIAutomationCore.dll; works from an MTA worker; pattern/property/control-type constants (e.g. `UIA_IsControlElementPropertyId` = 30016) | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-shfileopstructw | FO_DELETE + FOF_ALLOWUNDO recycles only with fully qualified paths; FOF_WANTNUKEWARNING warns before permanent deletion | 2026-10-12 |
| https://mhammond.github.io/pywin32/shell__SHFileOperation_meth.html and /SHFILEOPSTRUCT.html | `SHFileOperation((hwnd, wFunc, From, To, flags, NameMappings, ProgressTitle)) -> (result, aborted)` | 2026-10-12 |
| https://docs.python.org/3/library/webbrowser.html | `webbrowser.open` uses the default browser | 2026-10-12 |
| test `test_win_integration.py` | real UIA click (Invoke) + type (ValuePattern) on a Qt window; window bounds, minimise/restore; mss capture → JPEG | 2026-10-12 |
| test `test_f2_tools.py::test_real_recycle` (opt-in, run once) | item lands in the Recycle Bin (`NameSpace(10)`) | 2026-10-12 |

## Dictation (phase 4)

| URL | Confirmed | Checked |
|---|---|---|
| https://ai.google.dev/gemini-api/docs/audio | audio/wav (and others) accepted inline; 20 MB request limit; 32 tokens per second; recommended model gemini-3.8-flash | 2026-10-12 |
| https://ai.google.dev/gemini-api/docs/thinking | gemini-3.8-flash thinking levels low/medium/high (default medium); cannot be switched off | 2026-10-12 |
| https://ai.google.dev/gemini-api/docs/interactions | Interactions API GA; generateContent "remains fully supported"; Interactions store inputs by default (store=true, 55 days paid) | 2026-10-12 |
| https://ai.google.dev/api/generate-content | `client.models.generate_content(model=, contents=, config=GenerateContentConfig(system_instruction=…))`, `response.text` | 2026-10-12 |
| SDK introspection | `types.Part.from_bytes(*, data, mime_type)`; `GenerateContentConfig.thinking_config`; `ThinkingLevel.LOW` | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/dataxchg/clipboard-formats | ExcludeClipboardContentFromMonitorProcessing (any data), CanIncludeInClipboardHistory (DWORD 0/1), CanUploadToCloudClipboard (DWORD 0/1) | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-emptyclipboard | NULL owner on OpenClipboard → EmptyClipboard sets owner NULL → SetClipboardData fails | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/dataxchg/wm-destroyclipboard | sent to the clipboard owner's window procedure when emptied | 2026-10-12 |
| https://mhammond.github.io/pywin32/win32clipboard__SetClipboardData_meth.html, __GetClipboardDataHandle_meth.html | SetClipboardData copies a buffer into new global memory; GetClipboardDataHandle returns the data handle (read with GetGlobalMemory) | 2026-10-12 |
| tests `test_dictation.py::test_real_clipboard_round_trip`, `::test_real_paste_into_focused_field` (opt-in, run 2026-10-12) | byte-exact restore incl. a custom format; exclusion markers detected; real Ctrl+V pastes into a focused field | 2026-10-12 |

## Circle to Ask (phase 5)

| URL | Confirmed | Checked |
|---|---|---|
| https://doc.qt.io/qt-6/qscreen.html | `grabWindow(0)` grabs the entire screen; returned pixmap may be larger than requested on high-DPI screens; coordinates in device-independent pixels | 2026-10-12 |
| https://doc.qt.io/qt-6/highdpi.html | (see phase 3) per-monitor V2, logical screen geometry, islands of screens | 2026-10-12 |
| test `test_circle.py::test_real_screens_grab_at_physical_resolution` | on this PC every screen's grab is geometry × devicePixelRatio | 2026-10-12 |
| test `test_circle.py::test_map_to_pixmap_*` | mapping at 100/125/150/200 % and for a monitor left of the primary | 2026-10-12 |

## To-dos and scheduler (phase 6)

| URL | Confirmed | Checked |
|---|---|---|
| https://apscheduler.readthedocs.io/en/3.x/userguide.html | BackgroundScheduler; SQLAlchemyJobStore(url=); explicit job id + replace_existing for persistent stores; picklable args; misfire_grace_time + coalesce semantics; job stores must not be shared between schedulers; add_listener | 2026-10-12 |
| https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html | CronTrigger fields; day_of_week 0/mon = Monday in 3.x | 2026-10-12 |
| installed `apscheduler/schedulers/base.py`, `executors/base.py`, `events.py` | `add_job` accepts "package.module:callable"; missed runs raise `JobExecutionEvent(EVENT_JOB_MISSED, …, scheduled_run_time)`; `misfire_grace_time` must be positive or None | 2026-10-12 |
| spike `spikes/apscheduler_persistence.py` | with SQLAlchemy 2.1: jobs survive restart; within grace → runs late; beyond grace → EVENT_JOB_MISSED | 2026-10-12 |
| tests `test_scheduler.py` | same behaviour through `TaskScheduler` (late run, missed report, sync after job loss) | 2026-10-12 |

## Dependencies (PyPI JSON API, checked 2026-10-12)

| Package | Version | Released | Licence | Note |
|---|---|---|---|---|
| google-genai | 2.29.0 | 2026-10-07 | Apache-2.0 | official Gemini SDK |
| PySide6-Essentials | 6.12.0 | 2026-10-08 | LGPL-3.0 | used dynamically linked (PyInstaller onedir) |
| sounddevice | 0.5.6 | 2026-08-17 | MIT | |
| numpy | 2.5.4 | 2026-10-10 | BSD-3 | |
| mss | 10.2.0 | 2026-04-23 | MIT | |
| comtypes | 1.4.17 | 2026-09-21 | MIT | UI Automation + Core Audio COM |
| pycaw | 20260927 | 2026-09-26 | MIT | volume |
| pywin32 | 312 | 2026-06-04 | PSF | DPAPI, Win32 |
| winrt-runtime / -Windows.Foundation / -Windows.Foundation.Collections / -Windows.Media.Control / -Windows.Devices.Radios | 3.2.1 | 2025-06-06 | MIT | pywinrt; only Python projection of WinRT; last release 16 months old — acceptable, isolated behind interfaces |
| APScheduler | 3.11.3 | 2026-06-28 | MIT | 3.x API (4.x not used) |
| SQLAlchemy | 2.1.4 | 2026-10-07 | MIT | APScheduler SQLAlchemyJobStore |
| rapidfuzz | 3.14.6 | 2026-08-30 | MIT | fuzzy app matching |
| Pillow | 12.3.0 | 2026-07-01 | MIT-CMU | image crop/scale/JPEG |
| lucide-static (npm, bundled SVG files) | 1.56.0 | 2026-10-13 | ISC; Feather-derived icons also MIT | 42 icon SVGs copied into `wisp/assets/icons` with `LICENSE-lucide.txt`; static files, no code (registry.npmjs.org/lucide-static, files from unpkg.com/lucide-static@1.56.0) |
| winrt-Windows.Storage.Streams | 3.2.1 | 2025-06-06 | MIT | album art for the island (DataReader over the media thumbnail); same pywinrt release as the other projections |
| pyinstaller | 6.22.3 | 2026-09-12 | GPLv2+ with bootloader exception | build tool only |
| ruff 0.17.0, pytest 9.1.1, pytest-asyncio 1.4.0, pytest-qt 4.5.0 | | | MIT / Apache-2.0 | dev only |
| Not used: pynput (LGPLv3; replaced by ctypes hook), uiautomation (last release 2025-08; replaced by comtypes + documented UIA COM API), pywinauto (last release 2025-01) | | | | |

## Island and system controls (phase 7)

| URL | Confirmed | Checked |
|---|---|---|
| https://learn.microsoft.com/en-us/uwp/api/windows.devices.radios.radio | `Radio.RequestAccessAsync` before control; `GetRadiosAsync`; `SetStateAsync(RadioState)` returns `RadioAccessStatus`; `Kind` WiFi/Bluetooth; hardware switch or policy can deny | 2026-10-12 |
| https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager | `RequestAsync`, `GetCurrentSession`; session `TryGetMediaPropertiesAsync` (Title, Artist), `GetTimelineProperties` (StartTime, EndTime, Position, LastUpdatedTime), `GetPlaybackInfo().PlaybackStatus`, `TryTogglePlayPauseAsync`, `TryPlayAsync`, `TryPauseAsync`, `TrySkipNextAsync`, `TrySkipPreviousAsync`, `SourceAppUserModelId` | 2026-10-12 |
| spike `spikes/winrt_in_loop_thread.py` | GSMTC and Radios coroutines work from an unpackaged desktop process when awaited on Wisp's asyncio thread | 2026-10-12 |
| check on this PC | `Radio.get_radios_async()` returns an `IVectorView` projected by `winrt-Windows.Foundation.Collections` (hence the dependency) | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/wmicoreprov/wmisetbrightness-method-in-class-wmimonitorbrightnessmethods | `WmiMonitorBrightnessMethods.WmiSetBrightness(Timeout, Brightness)` in `root\WMI`; `WmiMonitorBrightness.CurrentBrightness`; only displays that support it (built-in panels) | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/wmisdk/swbemobject-execmethod- | `SWbemObject.ExecMethod_(name, InParameters)` with `Methods_(name).InParameters.SpawnInstance_()` | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/powrprof/nf-powrprof-setsuspendstate | `SetSuspendState(bHibernate, bForce, bWakeupEventsDisabled)`; caller needs `SE_SHUTDOWN_NAME` | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/shutdown | `shutdown /r` restart, `/s` shut down, `/t 0` no delay | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-lockworkstation | `LockWorkStation()` returns nonzero on success (asynchronous) | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/apps/develop/launch/launch-settings-app | `ms-settings:nightlight`, `:colors`, `:network-wifi`, `:bluetooth`, `:sound`, `:display` | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/apps/design/style/segoe-fluent-icons-font | Segoe Fluent Icons code points (Win 11); Segoe MDL2 Assets on Win 10 | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ishellitemimagefactory-getimage | `GetImage(SIZE, SIIGBF, HBITMAP*)`; `SIIGBF_ICONONLY`; caller frees the HBITMAP with `DeleteObject` | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-getdibits | `GetDIBits` with a `BITMAPINFOHEADER` (negative height = top-down, 32 bpp) copies the bits including alpha | 2026-10-12 |
| spike `spikes/shell_icon_probe.py`, test `test_island.py::test_shell_icon_keeps_alpha` | IID `{bcc18b79-…}` registered; icons for a Store app and a desktop app; transparent corners kept | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfow | `SPI_GETDESKWALLPAPER` (0x73), `SPI_SETDESKWALLPAPER` (0x14) with `SPIF_UPDATEINIFILE \| SPIF_SENDWININICHANGE` | 2026-10-12 |
| https://learn.microsoft.com/en-us/windows/win32/dataxchg/clipboard-formats | (see phase 4) exclusion markers honoured by clipboard history | 2026-10-12 |
| https://doc.qt.io/qt-6/qclipboard.html | `dataChanged` signal; `setText`, `setImage`, `image()` | 2026-10-12 |
| spike `spikes/system_probe.py` (read-only) | volume/mute, output devices, brightness (none on a desktop monitor), radios, dark mode and Night Light blob read on this PC | 2026-10-12 |

## Memory, loadout, stats (phase 8)

| URL | Confirmed | Checked |
|---|---|---|
| https://www.sqlite.org/fts5.html | external-content tables (`content=`, `content_rowid=`) kept in sync with triggers incl. the `'delete'` command; `MATCH` with quoted strings and trailing `*` prefix terms joined by `OR`; `bm25()` (lower = better) | 2026-10-13 |
| spike `spikes/sqlite_fts5.py`, tests `test_memory.py` | bundled SQLite has FTS5 + bm25; index follows inserts, edits and deletes; operator-laden input is neutralised | 2026-10-13 |
| https://ai.google.dev/gemini-api/docs/speech-generation | (see phase 2) prebuilt voice names used by the Loadout voice list | 2026-10-12 |
| https://ai.google.dev/gemini-api/docs/live-api/capabilities | (see phase 2) `speech_config.voice_config.prebuilt_voice_config.voice_name` | 2026-10-12 |

## Safety and hardening (phase 9)

| URL | Confirmed | Checked |
|---|---|---|
| https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_powershell_exe | `-NoLogo` hides the banner; `-NoProfile` doesn't load the profile; `-NonInteractive` makes prompts fail instead of hanging; a `-Command` string must be last; exit code from the last command or `exit n`; `-ExecutionPolicy` (not used) only sets the session policy | 2026-10-13 |
| test `test_hardening.py::test_run_command_*` | real PowerShell: UTF-8 output, exit code 3 from `exit 3`, a 2 s limit ends the process tree | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot | `TH32CS_SNAPPROCESS` (0x2) includes all processes, `th32ProcessID` ignored for it; `INVALID_HANDLE_VALUE` on failure; close with `CloseHandle`; enumerate with `Process32First`/`Next` | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-windowfrompoint | returns the window containing a point (NULL if none); skips hidden/disabled windows | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getancestor | `GA_ROOT` (2) gives the root window of a child window | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput | (see phase 2) UIPI silently blocks input to higher-integrity windows — Wisp checks elevation first and explains | 2026-10-12 |
| https://docs.python.org/3/library/threading.html#threading.excepthook | args `exc_type`, `exc_value`, `exc_traceback`, `thread`; `SystemExit` ignored by default | 2026-10-13 |
| https://docs.python.org/3/library/sys.html#sys.excepthook | called with (type, value, traceback) for uncaught exceptions | 2026-10-13 |

## Packaging (phase 10)

| URL | Confirmed | Checked |
|---|---|---|
| https://pyinstaller.org/en/stable/spec-files.html | the spec is executed as Python; `Analysis`/`PYZ`/`EXE(exclude_binaries=True)`/`COLLECT` one-folder layout; `SPECPATH` is the spec's folder. Filtering `a.binaries`/`a.datas` is only implied by the docs; the build output confirms it (no `opengl32sw.dll`, no `translations`) | 2026-10-13 |
| https://pyinstaller.org/en/stable/hooks.html | `collect_submodules`, `copy_metadata` | 2026-10-13 |
| build log + `--self-check` of `dist/Wisp/Wisp.exe` | all 12 checks pass frozen; the comtypes wrapper is bundled from `comtypes.gen`; the `%TEMP%\comtypes_cache\Wisp-312` folder is created empty (comtypes `_find_gen_dir` for frozen apps, read in the installed `comtypes/client/_code_cache.py`) | 2026-10-13 |
| installed `sounddevice.py` | on x64 Windows it loads `_sounddevice_data/portaudio-binaries/libportaudio64bit.dll` (or `-asio` with `SD_ENABLE_ASIO`) | 2026-10-13 |
| https://jrsoftware.org/ishelp/topic_consts.htm | `{autopf}` maps to `{userpf}` and `{autoprograms}` to `{userprograms}` in non-administrative mode; `{userappdata}`; `{%NAME}` environment constants | 2026-10-13 |
| https://jrsoftware.org/ishelp/topic_isxfunc_suppressiblemsgbox.htm | returns *Default* when message boxes are suppressed | 2026-10-13 |
| silent install/uninstall on this PC (PROGRESS log) | install: files, Start-menu shortcut, uninstall entry, Run value; the Run command line starts Wisp; uninstall removes all of these plus a Run value written by the app; user data kept | 2026-10-13 |
| https://ai.google.dev/gemini-api/terms | Unpaid Services: content may be used to improve products and human reviewers may read it; Paid Services: not used that way; EEA, Switzerland and UK: Paid Services only; users must be 18+ | 2026-10-13 |
| https://docs.github.com/en/actions | `runs-on: windows-latest`; `actions/checkout`, `actions/setup-python` (pip cache), `actions/upload-artifact` | 2026-10-13 |

## Speech recognition fix (2026-10-13)

| URL | Confirmed | Checked |
|---|---|---|
| https://ai.google.dev/gemini-api/docs/live-api/capabilities | input is raw 16-bit PCM, 16 kHz, little-endian, MIME `audio/pcm;rate=16000` (other rates are resampled by the API); native-audio models "automatically choose the appropriate language and don't support explicitly setting the language code", so restrict the language with system instructions; "The transcription language is inferred from the model's response"; `silence_duration_ms` 500–800 ms recommended; `prefix_padding_ms` 0 may clip words; with automatic VAD disabled the client sends `activityStart`/`activityEnd` | 2026-10-13 |
| https://ai.google.dev/api/live | `AudioTranscriptionConfig.languageCodes[]`: "BCP-47 language codes providing hints about the languages present in the audio" | 2026-10-13 |
| SDK `google.genai.types.AudioTranscriptionConfig` (2.29.0) and `_live_converters` | has `language_codes`; `input_audio_transcription` is passed to the setup as `inputAudioTranscription` | 2026-10-13 |
| probe with the user's key: silence and noise | 4 s of digital silence was transcribed as "¿Qué tal?"; faint hiss (≈ −64 dBFS) as "¿Qué?", with a Spanish reply | 2026-10-13 |
| probe with the user's key: full pipeline | 10 English phrases (Windows SAPI voice, 16 kHz) converted into 44.1 kHz × 4 ch float32 with two silent channels, then MicConverter → speech gate → `en-GB` hint → Gemini: 10/10 transcribed and answered in English; silence and hiss not sent | 2026-10-13 |
| probe with an invalid key | Live socket closed with 1007, reason "API key not valid. Please pass a valid API key."; `models.get` gives the same through the key check | 2026-10-13 |
| `sounddevice.check_input_settings` on this PC (no recording) | MME accepts the array's native 44100 Hz × 4 ch float32; WASAPI's shared format is 48000 Hz × 4 ch | 2026-10-13 |
| https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer.setoutputtowavefile | test phrases written as 16 kHz 16-bit mono WAV with `SpeechAudioFormatInfo` (test tooling only) | 2026-10-13 |

## UI polish (2026-10-13)

| URL | Confirmed | Checked |
|---|---|---|
| https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute | `DWMWA_USE_IMMERSIVE_DARK_MODE` (20) "supported starting with Windows 11 Build 22000"; `DWMWA_WINDOW_CORNER_PREFERENCE` (33) takes a `DWM_WINDOW_CORNER_PREFERENCE`; `DWMWA_SYSTEMBACKDROP_TYPE` (38) takes a `DWM_SYSTEMBACKDROP_TYPE`, "supported starting with Windows 11 Build 22621" | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_window_corner_preference | `DWMWCP_DEFAULT` 0, `DWMWCP_DONOTROUND` 1, `DWMWCP_ROUND` 2 ("Round the corners, if appropriate"), `DWMWCP_ROUNDSMALL` 3; minimum client build 22000 | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type | `DWMSBT_AUTO`, `DWMSBT_NONE`, `DWMSBT_MAINWINDOW` (2): "the backdrop material effect corresponding to a long-lived window behind the entire window bounds", Mica in its default variant on Windows 11; minimum client build 22621 | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmextendframeintoclientarea | negative margins create the "sheet of glass" effect (client area rendered without a window border); returns `S_OK` on success | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/ui/apply-mica-win32 | Microsoft's Win32 Mica path uses the Windows App SDK `MicaController` (system policy, light/dark, fallback colour); not used by Wisp (D-042). Mica samples the wallpaper once and falls back "to a neutral color when the app is inactive" | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/geometry | Windows 11 rounds top-level windows, flyouts and dialogs at 8 px, in-page controls at 4 px; windows aren't rounded when snapped or maximized | 2026-10-13 |
| `dwm.style_window` + `dwm.extend_frame` on this PC (Windows 11 build 26200) | `DwmSetWindowAttribute` returns S_OK for attributes 20, 33 and 38 and `DwmExtendFrameIntoClientArea` for −1 margins; on-screen capture (`docs/screenshots/after/onscreen`, taken while the window was inactive) shows the themed title bar and rounded corners. Seeing Mica itself needs an active window: MT-57 | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfow | `SPI_GETCLIENTAREAANIMATION` (0x1042): *pvParam* points to a BOOL that receives TRUE if animations are enabled (the Windows "Animation effects" setting) | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/typography | Segoe UI Variable is the Windows system font (weight and optical-size axes; Light 300 … Bold 700); Windows 11 uses Regular for most text and Semibold for titles; minimums 14 px Semibold, 12 px Regular; sentence case; type ramp: caption 12/16 in the Small cut, body 14/20 in Text, subtitle 20/28 and up in Display; installed families on this PC include `Segoe UI Variable Small`, `… Text`, `… Display` (QFontDatabase) | 2026-10-13 |
| https://www.w3.org/TR/WCAG21/ | contrast ratio (L1 + 0.05) / (L2 + 0.05), L1 the lighter; relative luminance L = 0.2126 R + 0.7152 G + 0.0722 B with each sRGB channel ≤ 0.04045 → /12.92, else ((c + 0.055)/1.055)^2.4 (0.03928 replaced in May 2021); SC 1.4.3: text at least 4.5:1 (large text 3:1) | 2026-10-13 |
| https://registry.npmjs.org/lucide-static/latest, https://unpkg.com/lucide-static@1.56.0/ | latest 1.56.0, licence ISC, repository github.com/lucide-icons/lucide; icons are 24×24 SVGs with `stroke="currentColor"` and `stroke-width="2"`; LICENSE is the ISC text plus Feather's MIT text for the icons it lists (Wisp uses some of them, e.g. calendar, check, chevrons, clipboard, info, lock, moon, power, search, trash, x); both texts ship with the icons and in THIRD_PARTY_NOTICES.txt | 2026-10-13 |
| https://doc.qt.io/qt-6/qiconengine.html | `paint()` and `clone()` must be reimplemented; `pixmap()` defaults to painting via `paint()`; `scaledPixmap(size, mode, state, scale)` returns a pixmap for that scale (reimplemented by Wisp so icons are drawn at the exact device-pixel size) | 2026-10-13 |
| https://doc.qt.io/qt-6/qtimer.html | `singleShot(msec, context, functor)`: the functor "will be called only if the context object has not been destroyed before the interval occurs" (checked in PySide6 6.12.0: a deleted context drops the call) | 2026-10-13 |
| `spikes/idle_cpu.py` on this PC | idle CPU of the whole process tree (GetProcessTimes over 60 s, Island visible, no key); results in PROGRESS.md | 2026-10-13 |

## Dynamic Island (2026-10-13, part 3)

| URL | Confirmed | Checked |
|---|---|---|
| https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles | WS_EX_NOACTIVATE (0x08000000): "does not become the foreground window when the user clicks it"; SetActiveWindow/SetForegroundWindow can still activate it; not on the taskbar by default. WS_EX_TOOLWINDOW (0x80): not in the taskbar or the Alt+Tab dialog. WS_EX_TOPMOST (0x8), WS_EX_LAYERED (0x80000), WS_EX_TRANSPARENT (0x20) | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features | layered windows: "Hit testing of a layered window is based on the shape and transparency of the window … areas … whose alpha value is zero will let the mouse messages through"; SetForegroundWindow is allowed only if, among others, "the calling process received the last input event" (or is the foreground process), and "it is possible for a process to be denied the right … even if it meets these conditions" | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowrgn | the window region determines where the system permits drawing; coordinates relative to the window's upper-left corner; the system owns the region after the call | 2026-10-13 |
| https://doc.qt.io/qt-6/qwindow.html | `setMask`: "a hint to the windowing system that the application does not want to receive mouse or touch input" outside the region, and the application must clear the rest to transparent; `requestActivate` asks for keyboard focus | 2026-10-13 |
| https://doc.qt.io/qt-6/qt.html | `Qt::Tool` (tool window), `FramelessWindowHint`, `WindowStaysOnTopHint`, `WindowDoesNotAcceptFocus` ("should not receive the input focus"), `WindowTransparentForInput` ("only for output … does not take input"); `WA_ShowWithoutActivating`, `WA_TranslucentBackground`, `WA_TransparentForMouseEvents` | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos | a window handle as hWndInsertAfter places the window behind it; SWP_NOACTIVATE (0x10) — without it the window is activated; SWP_NOMOVE (0x2), SWP_NOSIZE (0x1); a topmost window placed after another topmost window stays topmost | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getasynckeystate | most significant bit set while the key/button is down; VK_LBUTTON reports the physical left button | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shqueryusernotificationstate and …/ne-shellapi-query_user_notification_state | returns S_OK and a QUERY_USER_NOTIFICATION_STATE: QUNS_BUSY 2 ("a full-screen application is running or Presentation Settings are applied"), QUNS_RUNNING_D3D_FULL_SCREEN 3, QUNS_PRESENTATION_MODE 4, QUNS_ACCEPTS_NOTIFICATIONS 5; no notification is sent when a full-screen app starts or stops (so Wisp polls) | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-monitorfromwindow, …/ns-winuser-monitorinfo, …/nf-winuser-iszoomed | MonitorFromWindow returns the monitor with the largest intersection (MONITOR_DEFAULTTONEAREST); MONITORINFO.rcMonitor in virtual-screen coordinates; IsZoomed: non-zero when maximized | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nn-endpointvolume-iaudiometerinformation | obtained with IMMDevice::Activate(IID_IAudioMeterInformation); GetPeakValue normalised 0.0–1.0; a render endpoint is metered before the endpoint volume; software meter in shared mode | 2026-10-13 |
| https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmediaproperties.thumbnail, …/windows.storage.streams.irandomaccessstreamreference.openreadasync, …/windows.storage.streams.datareader | Thumbnail is an IRandomAccessStreamReference; OpenReadAsync gives an IRandomAccessStreamWithContentType; DataReader(IInputStream), LoadAsync(count), ReadBytes | 2026-10-13 |
| `spikes/island_window_probe.py` on this PC | Qt flags give WS_EX_NOACTIVATE \| TOOLWINDOW \| TOPMOST \| LAYERED; showing doesn't change the foreground window; with and without a mask WindowFromPoint beside/below the pill is another window, inside it is the island; the masked pill still draws black; setMask ≈ 0.4 ms; a WindowTransparentForInput window gets WS_EX_TRANSPARENT and is never hit | 2026-10-13 |
| `spikes/island_focus_probe.py` on this PC | SetForegroundWindow is refused for a test process that received no input (both with Qt's WindowDoesNotAcceptFocus and with WS_EX_NOACTIVATE set directly), so focusing the text box after a real click is manual test MT-70 | 2026-10-13 |
| `spikes/island_fps.py`, `spikes/idle_cpu.py` on this PC | frame times during morphs and idle CPU; results in PROGRESS.md | 2026-10-13 |

## Brief of 2026-10-13, part 4

| URL | Confirmed | Checked |
|---|---|---|
| https://doc.qt.io/qt-6/qfont.html | pointSize()/pointSizeF() return -1 "if the font size was specified in pixels"; setPointSize/F: "The point size must be greater than zero"; setPixelSize "makes the font device dependent" — use setPointSize(F) for device independence | 2026-10-13 |
| https://doc.qt.io/qt-6/qscreen.html | logicalDotsPerInchY: "This value is used to convert font point sizes to pixel sizes" | 2026-10-13 |
| probe on this PC (Qt message handler + Python stack) | the warning came from QDateTimeEdit.setCalendarPopup(True) in the Today tab; with the point-sized default font: none at start-up, in any island tab, the console, Settings or the menu; logical DPI 96 at 100/125/150/200 %, 9.75 pt = 13 px with identical line height | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getcursorpos | the cursor position "in screen coordinates"; the input desktop must be the current desktop | 2026-10-13 |
| https://learn.microsoft.com/en-us/windows/win32/api/shellscalingapi/nf-shellscalingapi-getdpiformonitor | "This API is not DPI aware and should not be used if the calling thread is per-monitor DPI aware" (Wisp is) — so not used; the reveal zone works in Qt's device-independent coordinates instead | 2026-10-13 |
| https://doc.qt.io/qt-6/qcursor.html, https://doc.qt.io/qt-6/qguiapplication.html | QCursor::pos: "the position of the cursor (hot spot) … in global screen coordinates", queried from the windowing system; QGuiApplication::screenAt: "the screen at point, or nullptr"; primaryScreen | 2026-10-13 |
| probe on this PC (one display at 175 %) | GetCursorPos (2244, 991) = QCursor.pos (1282, 566) × 1.75; QScreen geometry 2194 × 1234: Qt's cursor and screen coordinates are both device-independent | 2026-10-13 |

### Google Calendar (D-050)

| URL | Confirmed | Checked |
|---|---|---|
| https://developers.google.com/calendar/api/quickstart/python | packages google-api-python-client, google-auth-httplib2, google-auth-oauthlib; Google Auth platform → Branding / Audience / Clients → Create Client → **Desktop app** → download JSON; `InstalledAppFlow.from_client_secrets_file(...).run_local_server(port=0)`; tokens saved with `creds.to_json()`, refreshed with `creds.refresh(Request())`; delete the token when scopes change | 2026-10-13 |
| https://developers.google.com/identity/protocols/oauth2/native-app | loopback redirect `http://127.0.0.1:port` with a listener on a random free port, recommended for Windows desktop apps; PKCE supported, S256 challenge = Base64URL (no padding) of SHA-256 of the verifier; installed apps "cannot keep secrets"; revoke at `https://oauth2.googleapis.com/revoke?token=` (access or refresh token; revoking an access token also revokes its refresh token); "Incremental authorization is not supported for installed apps or devices" | 2026-10-13 |
| https://developers.google.com/identity/protocols/oauth2 | refresh tokens can stop working (revoked, unused for six months, too many live tokens); an External project in "Testing" status is "issued a refresh token expiring in 7 days" unless it asks only for basic profile scopes; 100 refresh tokens per account per client | 2026-10-13 |
| https://developers.google.com/workspace/calendar/api/auth | scopes: `calendar.calendarlist.readonly` (view the calendars you're subscribed to), `calendar.events.readonly` (view events on all your calendars), `calendar.events.owned` (create, change and delete events on calendars you own), `calendar.events` (view and edit events on all calendars), `calendar` (everything incl. sharing and permanently deleting calendars), `calendar.app.created` (calendars the app created) | 2026-10-13 |
| https://developers.google.com/workspace/calendar/api/guides/sync | full sync may be restricted (sample: `timeMin`); "Each list request should use the same set of query parameters, including the initial request"; disallowed restrictions give 400; incremental results "always contain deleted entries"; `nextSyncToken` only on the last page; 410 → "a full wipe of the client's store and a new full sync" | 2026-10-13 |
| https://developers.google.com/workspace/calendar/api/v3/reference/events/list | `GET …/calendars/calendarId/events`; `syncToken` can't be combined with iCalUID, orderBy, privateExtendedProperty, q, sharedExtendedProperty, timeMin, timeMax, updatedMin; showDeleted can't be False with a sync token; expired token → 410; `singleEvents` expands recurring events; timeMin/timeMax RFC 3339 with offset (timeMax exclusive bound on start, timeMin on end); maxResults ≤ 2500; cancelled events have status "cancelled"; nextPageToken / nextSyncToken; scopes include `calendar.events.readonly` | 2026-10-13 |
| https://developers.google.com/workspace/calendar/api/v3/reference/calendarList, …/calendarList/list | `GET …/users/me/calendarList`, scope `calendar.calendarlist.readonly` allowed; entry fields id, summary, summaryOverride, backgroundColor (hex, supersedes colorId), primary, selected, timeZone, accessRole (freeBusyReader, reader, writer, writerWithoutPrivateAccess, owner), hidden, deleted | 2026-10-13 |
| https://developers.google.com/workspace/calendar/api/v3/reference/events/insert | `POST …/calendars/calendarId/events`; start and end required; `dateTime` RFC 3339, offset required unless `timeZone` (IANA name) is given; `date` "yyyy-mm-dd" for all-day; scopes accepted: `calendar`, `calendar.events`, `calendar.app.created`, `calendar.events.owned` | 2026-10-13 |
| google-auth-oauthlib 1.5.0 source (`flow.py`) | `authorization_url` sets `access_type="offline"` and, with the default `autogenerate_code_verifier`, an S256 `code_challenge`; `run_local_server(host, port, open_browser, authorization_prompt_message, success_message, timeout_seconds, **kwargs)` passes extra kwargs (e.g. `prompt`) to the authorization URL; `InstalledAppFlow.from_client_config(config, scopes)` takes the "installed" or "web" client JSON | 2026-10-13 |
| google-api-python-client 2.201.0 source (`discovery.py`, `discovery_cache/__init__.py`, `errors.py`) | `build(serviceName, version, credentials=, cache_discovery=, static_discovery=)`; static discovery reads `discovery_cache/documents/<api>.<version>.json` next to the module; 605 documents, 112 MB; `HttpError.status_code` | 2026-10-14 |
| google-auth 2.61.0 source (`oauth2/credentials.py`, `exceptions.py`) | `Credentials.from_authorized_user_info(info, scopes)`, `to_json()`; a failed refresh raises `RefreshError` | 2026-10-13 |
| PyPI and installed metadata | google-api-python-client 2.201.0, google-auth-oauthlib 1.5.0, google-auth-httplib2 0.4.4, google-auth 2.61.0, google-api-core 2.42.0 (Apache-2.0); httplib2 0.32.0 (MIT); oauthlib 4.0.0 (BSD-3-Clause); requests-oauthlib 2.0.0 (ISC); uritemplate 4.2.0 (BSD-3-Clause or Apache-2.0) | 2026-10-14 |
| https://pyinstaller.org/en/stable/spec-files.html, pyinstaller-hooks-contrib `hook-googleapiclient.model.py` | Analysis `datas` may be filtered after analysis; the contrib hook collects all of `googleapiclient.discovery_cache` (so the spec keeps only `calendar.v3.json`) | 2026-10-14 |
| https://docs.python.org/3/library/zoneinfo.html | for ambiguous times "the offset from _before_ the transition is used when `fold=0`, and the offset _after_ the transition is used when `fold=1`"; converting from UTC sets fold correctly | 2026-10-14 |
| https://peps.python.org/pep-0495/ | in a gap, "the rules in effect before the transition should be used if fold=0" (so 01:30 on 29 Mar is read as GMT, i.e. 02:30 BST); timedelta addition "ignores both fold and tzinfo attributes" (local-field arithmetic), so Wisp computes durations in UTC | 2026-10-14 |
| https://support.google.com/cloud/answer/15549945 | Testing: "limited to up to 100 test users"; "Authorizations by a test user will expire seven days from the time of consent"; In production: "available to any user with a Google Account"; an Unverified apps warning is shown while sensitive scopes aren't verified | 2026-10-14 |

### Files & Share (D-051)

| URL | Confirmed | Checked |
|---|---|---|
| https://learn.microsoft.com/en-us/windows/win32/search/-search-3x-wds-qryidx-overview | ways to query the index: SQL and AQS approaches, ISearchQueryHelper, the search-ms protocol, Windows Search SQL syntax | 2026-10-14 |
| https://learn.microsoft.com/en-us/windows/win32/search/using-sql-and-aqs-to-query-the-index | OLE DB provider string `provider=Search.CollatorDSO;EXTENDED PROPERTIES="Application=Windows"`; ADO example `Provider=Search.CollatorDSO;Extended Properties='Application=Windows';` with `SELECT Top 5 System.ItemPathDisplay FROM SYSTEMINDEX WHERE scope='file:' ORDER BY …`; the provider is read-only; search-ms starts an application like File Explorer | 2026-10-14 |
| https://learn.microsoft.com/en-us/windows/win32/search/-search-sql-where, …/-search-sql-like, …/-search-sql-folderdepth, …/-search-sql-literals | LIKE wildcards % _ [ ] [^ ], a wildcard matched literally inside brackets ('[%]'); SCOPE='file:C:/…' deep, DIRECTORY shallow, backslashes become forward slashes, several combined with OR; string literals in single quotes, a quote written twice | 2026-10-14 |
| probe on this PC (`ADODB.Connection` with the provider, counts and timings only) | the WSearch service is running; a LIKE query over the profile answers in ~70 ms; doubled quotes accepted | 2026-10-14 |
| https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ishellitemimagefactory-getimage | "The default behavior is to load a thumbnail. If there is no thumbnail … retrieves an HBITMAP for the icon"; SIIGBF_RESIZETOFIT 0, SIIGBF_ICONONLY 4; extraction "should never be done on a UI thread" | 2026-10-14 |
| https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file | reserved characters < > : " / \ \| ? * and NUL; characters 1–31; reserved names CON, PRN, AUX, NUL, COM1–9, COM¹²³, LPT1–9, LPT¹²³, also followed by an extension; don't end a name with a space or a period | 2026-10-14 |
| https://doc.qt.io/qt-6/qwindowsmimeconverter.html | built-in mapping: CF_HDROP and CF_INETURL ↔ text/uri-list; CF_UNICODETEXT/CF_TEXT ↔ text/plain | 2026-10-14 |
| https://learn.microsoft.com/en-us/windows/win32/shell/shell-windows, …/shellfolderview-selecteditems | Shell.Windows returns the ShellWindows collection of open Shell windows; ShellFolderView.SelectedItems returns a FolderItems of the selected items | 2026-10-14 |
| https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-idatatransfermanagerinterop | IUnknown-based; methods GetForWindow ("Gets the DataTransferManager instance for the specified window") and ShowShareUIForWindow ("Displays the UI for sharing content for the specified window"); shobjidl_core.h | 2026-10-14 |
| https://learn.microsoft.com/en-us/uwp/winrt-cref/winrt-type-system | GUIDs of parameterized types: RFC 4122 version 5 (SHA-1) in namespace 11f47ad5-7b73-42c0-abae-878b1e16adee over the signature `pinterface({piid};args)`; interfaces `{iid}`, runtime classes `rc(name;default interface)`, `string` for HSTRING | 2026-10-14 |
| `spikes/winmd_dump.py` over C:\Windows\System32\WinMetadata (dnfile 0.18.0, MIT, dev only) | GUIDs and vtable order: IDataTransferManager {a5caee9b-…} add_DataRequested slot 6; IDataRequestedEventArgs {cb8ba807-…} get_Request 6; IDataRequest {4341ae3b-…} get_Data 6; IDataPackage {61ebf5c7-…} get_Properties 7, SetStorageItems(value, readOnly) 23; IDataPackagePropertySet {cd1c93eb-…} put_Title 7; IStorageFileStatics {5984c710-…} GetFileFromPathAsync 6; IStorageItem {4207a996-…}; IStorageFile {fa3f6186-…}; IAsyncInfo get_Status 7, get_ErrorCode 8, Cancel 9; IAsyncOperation`1 {9fc2b0bb-…} GetResults 8; IIterable`1 {faa585ea-…} First 6; IIterator`1 {6a79e863-…} get_Current 6, get_HasCurrent 7, MoveNext 8, GetMany 9; TypedEventHandler`2 {9de1c534-…} Invoke (IUnknown-based, slot 3); default interfaces of DataTransferManager and DataRequestedEventArgs | 2026-10-14 |
| `spikes/share_probe.py` on this PC | the computed IID of IAsyncOperation<StorageFile> is accepted by the real object; GetForWindow and add_DataRequested succeed for a top-level window; with --show the sheet opened and the handler filled the package (S_OK) | 2026-10-14 |
| https://learn.microsoft.com/en-us/windows/win32/api/netlistmgr/ne-netlistmgr-nlm_network_category, …/nf-netlistmgr-inetworkconnection-getadapterid | NLM_NETWORK_CATEGORY_PUBLIC 0 (untrusted), PRIVATE 1 (trusted), DOMAIN_AUTHENTICATED 2; categories must not be used to assume which firewall ports are open; GetAdapterId returns the adapter ID (GUID) of the connection's TCP/IP interface | 2026-10-14 |
| https://learn.microsoft.com/en-us/uwp/api/windows.networking.connectivity.networkinformation.gethostnames, …/windows.networking.hostname.ipinformation, …/windows.networking.connectivity.networkadapter.networkadapterid | GetHostNames: host names of the local machine; IPInformation set only for local IPv4/IPv6 addresses from GetHostNames (null otherwise); NetworkAdapterId is the adapter's GUID | 2026-10-14 |
| probe on this PC (comtypes wrapper of the Network List type library; IDispatch can't return the GUID) | one connected connection, category 0 (Public); its adapter ID matches an IPv4 host name's adapter | 2026-10-14 |
| https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules | with no allow rule "a dialog box prompts the user to either allow or block an application's packets the first time the app … tries to communicate in the network"; No/cancel, or a non-admin user, creates block rules; "they must be deleted to generate the prompt again" | 2026-10-14 |
| https://support.microsoft.com/en-us/windows/experience/connectivity-networking/share-things-with-nearby-devices-in-windows (via search) | Nearby sharing is turned on in Settings → System → Nearby sharing (newer builds: System → Multitasking); Bluetooth and Wi-Fi on | 2026-10-14 |
| https://docs.python.org/3/library/http.server.html | ThreadingHTTPServer handles requests in threads; log_message "Logs an arbitrary message to sys.stderr … typically overridden"; warning: "not recommended for production. It only implements basic security checks"; SimpleHTTPRequestHandler follows symbolic links; send_header doesn't validate CRLF | 2026-10-14 |
| https://docs.python.org/3/library/secrets.html | token_urlsafe(nbytes): URL-safe Base64 text of nbytes random bytes; "32 bytes (256 bits) of randomness is sufficient for the typical use-case"; compare_digest is constant-time | 2026-10-14 |
| https://segno.readthedocs.io/en/latest/api.html | make(error=…, micro=…); matrix_iter(scale, border) yields 0x1 dark / 0x0 light including the quiet zone; QR codes have a quiet zone of four modules | 2026-10-14 |
| https://unpkg.com/lucide-static@1.56.0/icons/ | 8 more icons, same package and licence as D-043: smartphone, share-2, file, pencil, folder-input, download, upload, external-link | 2026-10-14 |
| PyPI and installed metadata | segno 1.6.6 (BSD); winrt-Windows.Networking 3.2.1 and winrt-Windows.Networking.Connectivity 3.2.1 (MIT, PyWinRT); dnfile 0.18.0 (MIT, dev extra) | 2026-10-14 |

## Screen Assist + Discreet mode (brief of 2026-10-14)

### Screen Assist and Watch mode (D-052)

| URL | Confirmed | Checked |
|---|---|---|
| https://ai.google.dev/gemini-api/docs/image-understanding | inline image data limits the whole request to 20 MB; "258 tokens if both dimensions <= 384 pixels. Larger images are tiled into 768x768 pixel tiles, each costing 258 tokens"; Gemini 3's `media_resolution` "determines the maximum number of tokens allocated per input image"; put the text prompt before the image | 2026-10-14 |
| https://ai.google.dev/api/generate-content | MediaResolution levels MEDIA_RESOLUTION_LOW / MEDIUM / HIGH; `Part.mediaResolution`; UsageMetadata promptTokenCount, candidatesTokenCount, thoughtsTokenCount, totalTokenCount (prompt + tool-use prompt + thoughts + candidates) | 2026-10-14 |
| google-genai 2.29.0 source (`types.py`) | `GenerateContentConfig` has `system_instruction`, `thinking_config`, `media_resolution`, `response_mime_type`, `response_json_schema`, `response_modalities`, `speech_config`; `SpeechConfig.voice_config` → `VoiceConfig.prebuilt_voice_config` → `PrebuiltVoiceConfig.voice_name`; usage metadata fields as above | 2026-10-14 |
| https://ai.google.dev/gemini-api/docs/live-api/session-management | "Without compression, audio-only sessions are limited to 15 minutes, and audio-video sessions are limited to 2 minutes"; a connection lasts about 10 minutes; context-window compression extends sessions | 2026-10-14 |
| https://ai.google.dev/gemini-api/docs/speech-generation | TTS models gemini-3.8-flash-tts, gemini-3.8-flash-lite-tts, …; text in, audio out; 24 kHz mono 16-bit PCM (WAV unary, raw L16 when streaming); 30 prebuilt voices incl. Zephyr, Puck, Charon, Kore; examples use the Interactions API | 2026-10-14 |
| https://ai.google.dev/gemini-api/docs/interactions | Interactions are stored by default (55 days paid, 1 day free) unless `store=false`; generateContent "remains fully supported" | 2026-10-14 |
| https://ai.google.dev/gemini-api/docs/structured-output | JSON Schema output; a subset of JSON Schema; validate values in the application | 2026-10-14 |
| https://ai.google.dev/gemini-api/docs/pricing (last updated 2026-10-13) | Gemini 3.8 Flash paid tier: input $0.75 / output $3.75 per 1M tokens to 2026-12-31, $1.50 / $7.50 from 2027-01-01; 3.8 Flash TTS: $0.50 text in / $9.00 audio out, doubling from 2027 | 2026-10-14 |
| probe on this PC with the user's key and a drawn test image | generate_content returned 503 UNAVAILABLE ("experiencing high demand") twice; the request shapes are verified against the SDK and covered by MT-98 | 2026-10-14 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-monitorinfoexw | MONITORINFOEX adds `szDevice`, the monitor's device name, filled by GetMonitorInfo | 2026-10-15 |
| https://doc.qt.io/qt-6/qscreen.html | `name()` is "a user presentable string" (X11 example only; nothing about Windows); `grabWindow(0)` grabs the entire screen, the pixmap may be larger on high-DPI screens (devicePixelRatio) | 2026-10-15 |
| probe on this PC | `QScreen.name()` = `\\.\DISPLAY1` = MONITORINFOEX `szDevice` (UNDOCUMENTED match, D-052) | 2026-10-15 |
| Qt `QTextDocument.setMarkdown` on this PC | fenced code blocks carry `BlockCodeFence` / `BlockCodeLanguage` and the generic family "monospace"; Wisp sets Cascadia Mono/Consolas on them | 2026-10-15 |
| https://unpkg.com/lucide-static@1.56.0/icons/ | eye and scan-eye icons (same package and licence as D-043) | 2026-10-15 |

### Discreet mode (D-053)

| URL | Confirmed | Checked |
|---|---|---|
| https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html | SC 1.4.3 (AA): text contrast at least 4.5:1 (large text 3:1); ratio = (L1 + 0.05) / (L2 + 0.05) with relative luminance; measured against the background the text is rendered over (Wisp checks the card composited over white and black, the extremes) | 2026-10-15 |
| this PC (`theme.composite` + `theme.contrast`) | card text #c8cbd0 and labels #a9adb4 on #1e1f22 at 92 % over white: 8.0:1 and 5.8:1; at 85 %: 6.3:1 and 4.5:1; at 80 % the labels drop to 3.8:1 (so the setting starts at 85 %) | 2026-10-15 |

## Screen Assist and microphone fixes (2026-10-16)

### Screen Assist's closed client (D-054)

| URL | Confirmed | Checked |
|---|---|---|
| google-genai 2.29.0 source (`client.py`) | `Client.close()` closes the sync API client ("Close the client to release resources"); `__enter__` returns the client, `__exit__` calls `close()`; `__del__` calls `close()` — so a temporary `Client(...).models.generate_content(...)` is closed before it sends | 2026-10-16 |
| httpx 0.28.1 source (`_client.py`, `send`) | raises `RuntimeError("Cannot send a request, as the client has been closed.")` on a closed client; `ConnectError`, `ReadTimeout` … derive from `TransportError` | 2026-10-16 |
| google-genai 2.29.0 source (`_api_client.py`, `HttpOptions.base_url`) | a custom `base_url` replaces `https://generativelanguage.googleapis.com/`; requests go to `{base}/v1beta/models/{model}:generateContent` with the key in `x-goog-api-key`; inline data is URL-safe base64; some JSON fields are snake_case (`thinking_level`, `mime_type`) — checked against the loopback server | 2026-10-16 |
| https://ai.google.dev/gemini-api/docs/thinking | gemini-3.8-flash: thinking levels low, medium, high (default medium) — `thinking_level` LOW is valid | 2026-10-16 |
| https://ai.google.dev/api/generate-content | `MediaResolution` levels MEDIA_RESOLUTION_LOW / MEDIUM / HIGH / ULTRA_HIGH | 2026-10-16 |
| https://ai.google.dev/gemini-api/docs/media-resolution | per-image token budgets: low 280, medium 560, high 1120, ultra_high 2240; Gemini 3 models | 2026-10-16 |
| probe on this PC with the user's key (source, worker thread, drawn image) | before the fix: `RuntimeError: Cannot send a request, as the client has been closed.`; after: the request reaches Google (503 "high demand" twice) | 2026-10-16 |
| PyInstaller build of the old code (scratchpad) | `--self-check` → `screen_assist` fails with the same RuntimeError and traceback; exit code 1 | 2026-10-16 |

### A silent microphone (D-055)

| URL | Confirmed | Checked |
|---|---|---|
| https://learn.microsoft.com/en-us/uwp/api/windows.security.authorization.appcapabilityaccess.appcapability | `AppCapability` (Windows 10 1903+): "Create is callable only by SUA apps" — not usable by an unpackaged app like Wisp | 2026-10-16 |
| https://www.elevenforum.com/t/enable-or-disable-apps-access-to-microphone-in-windows-11.17117/ (third-party; UNDOCUMENTED by Microsoft) | `CapabilityAccessManager\ConsentStore\microphone` `Value` Allow/Deny under HKLM ("Microphone access") and HKCU ("Let apps access your microphone"); `…\microphone\NonPackaged` `Value` ("Let desktop apps access your microphone") | 2026-10-16 |
| this PC (read-only) | all three = Allow; `NonPackaged` usage subkeys list python.exe, never `dist\Wisp\Wisp.exe`; Core Audio `IAudioEndpointVolume`: default capture "Microphone Array (AMD Audio Device)", 4 channels, not muted, 100 %; default communications capture: a Bluetooth headset; Audio/Operational log: no events at either failure | 2026-10-16 |

## Screen Assist fixes (2026-10-20)

### Empty capture rectangles (D-056)

| URL | Confirmed | Checked |
|---|---|---|
| https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute | the enum starts at 1, so `DWMWA_EXTENDED_FRAME_BOUNDS` = 9 ("the extended frame bounds rectangle in screen space", a RECT) and `DWMWA_CLOAKED` = 14 (non-zero: why it is cloaked, app/shell/inherited) | 2026-10-20 |
| https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect | the bounding rectangle in screen coordinates; "may include invisible resize borders" (DWMWA_EXTENDED_FRAME_BOUNDS gives the visible bounds, so GetWindowRect is only the fallback); "virtualized for DPI" (Wisp is per-monitor DPI aware, so physical pixels) | 2026-10-20 |
| mss 10.2.0 source (`base.py`) | `grab` raises `ScreenShotError("Region has zero or negative size")` for width or height ≤ 0; `monitors[0]` is the bounding box of all monitors | 2026-10-20 |
| this PC's log and Action log | 2026-10-20 12:05: the 0×0 region came from a Screen-tab request (thread "screen-assist", no hotkey line) | 2026-10-20 |

### Busy Gemini (D-057)

| URL | Confirmed | Checked |
|---|---|---|
| https://docs.cloud.google.com/vertex-ai/generative-ai/docs/retry-strategy | the google-genai SDK's `types.HttpRetryOptions` (attempts, initial_delay, max_delay, exp_base, jitter, http_status_codes) set on the client's `types.HttpOptions(retry_options=…)`, or per request in `GenerateContentConfig(http_options=…)`; defaults: 5 attempts, 1 s initial delay | 2026-10-20 |
| google-genai 2.29.0 source (`_api_client.py`, `types.py`) | `retry_options=None` means one attempt ("never retry"); retries use tenacity with `wait_exponential_jitter`, retry on the listed status codes and on httpx timeouts and connection errors, and log before sleeping; `HttpOptions.client_args` ("Args passed to the HTTP client") go to `httpx.Client` (keys it doesn't take are dropped); a `verify` SSL context there is used as is; the websocket context comes from `async_client_args["ssl"]`, otherwise a new certifi context; `HttpOptions.timeout` is in milliseconds | 2026-10-20 |
| tenacity source (`wait_exponential_jitter.__call__`) | wait = initial × exp_base^(attempt − 1) + uniform(0, jitter), capped at max | 2026-10-20 |
| https://www.python-httpx.org/advanced/event-hooks/ | `event_hooks` on `httpx.Client` is a dict of lists of callables; a response hook is "passed the response instance" and called "before determining if the response body should be read" | 2026-10-20 |
| https://ai.google.dev/gemini-api/docs/models | current text models include gemini-3.8-flash, gemini-3.6-flash (multimodal), gemini-3.5-flash-lite, gemini-3.1-flash-lite | 2026-10-20 |
| https://ai.google.dev/gemini-api/docs/thinking | thinking levels: gemini-3.6-flash minimal/low/medium/high; gemini-3.5-flash-lite minimal/low/medium/high (so `thinking_level` low works for both fallbacks) | 2026-10-20 |
| probe on this PC (cProfile) | `genai.Client(...)` spent 0.46 s in two `ssl.create_default_context` calls; with a shared context, about 1 ms | 2026-10-20 |

### The press that ended in nothing (D-058)

| URL | Confirmed | Checked |
|---|---|---|
| this PC's log, Action log and `ai_usage` | 2026-10-19 22:27: press 27.616, mic open 29.215 (on MainThread), release 29.220; capture at 22:27:28; no usage row; quit at 22:27:54. 2026-10-20: a 503 arrived 28 s after its capture | 2026-10-20 |
| probe on this PC (no stream opened) | `import sounddevice` (PortAudio start-up) 0.23–0.65 s; device query 40–60 ms; format checks under 1 ms | 2026-10-20 |

### The CI build (D-059)

| URL | Confirmed | Checked |
|---|---|---|
| https://docs.python.org/3.12/library/sys.html (sys.stdout) | "On Windows, UTF-8 is used for the console device. Non-character devices such as disk files and pipes use the system locale encoding (i.e. the ANSI codepage)"; PYTHONIOENCODING / PYTHONUTF8 override it | 2026-10-20 |
| https://docs.python.org/3.12/library/io.html (TextIOWrapper.reconfigure) | `reconfigure(*, encoding=None, errors=None, …)`; "changing encoding after write is possible"; flushes first | 2026-10-20 |
| https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands | `::error file=…,line=…,title=…::message` creates an error annotation | 2026-10-20 |
| https://raw.githubusercontent.com/actions/toolkit/main/packages/core/src/command.ts | escapeData: % → %25, CR → %0D, LF → %0A; escapeProperty also : → %3A and , → %2C | 2026-10-20 |
| GitHub REST API on this repository, unauthenticated | job logs: 403 "Must have admin rights to Repository"; check-run annotations and job steps: readable | 2026-10-20 |
| https://doc.qt.io/qt-6/qobject.html (deleteLater) | without a running event loop "deferred deletes will not be processed automatically"; `QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete)` processes them | 2026-10-20 |
| this PC: pytest with a diagnostic plugin running atexit callbacks one by one | the crash is in `PySide6.QtCore.__moduleShutdown` (0xC0000005 / 0xC0000409); 29 top-level and 671 widgets in all left, two of each WispApp window; with the `wisp_app` fixture none are left and the exit code is 0 | 2026-10-20 |
