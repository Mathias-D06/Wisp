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
