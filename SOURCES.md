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
| winrt-runtime / -Windows.Foundation / -Windows.Media.Control / -Windows.Devices.Radios | 3.2.1 | 2025-06-06 | MIT | pywinrt; only Python projection of WinRT; last release 16 months old — acceptable, isolated behind interfaces |
| APScheduler | 3.11.3 | 2026-06-28 | MIT | 3.x API (4.x not used) |
| SQLAlchemy | 2.1.4 | 2026-10-07 | MIT | APScheduler SQLAlchemyJobStore |
| rapidfuzz | 3.14.6 | 2026-08-30 | MIT | fuzzy app matching |
| Pillow | 12.3.0 | 2026-07-01 | MIT-CMU | image crop/scale/JPEG |
| pyinstaller | 6.22.3 | 2026-09-12 | GPLv2+ with bootloader exception | build tool only |
| ruff 0.17.0, pytest 9.1.1, pytest-asyncio 1.4.0, pytest-qt 4.5.0 | | | MIT / Apache-2.0 | dev only |
| Not used: pynput (LGPLv3; replaced by ctypes hook), uiautomation (last release 2025-08; replaced by comtypes + documented UIA COM API), pywinauto (last release 2025-01) | | | | |
