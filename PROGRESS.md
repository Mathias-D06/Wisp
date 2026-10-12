# Wisp — progress tracker

Resume rule: a fresh session reads this file, then `DECISIONS.md` and `SOURCES.md`, then continues at
"Next step". Commit after every phase.

Legend: `[x]` done with evidence · `[~]` implemented, automated evidence where possible, but the
acceptance step needs real hardware/API key and is listed in `MANUAL_TESTS.md` (not yet run) ·
`[ ]` not done.

## Status

- Current phase: 6 — F5 to-dos + F6 scheduler
- Next step: verify APScheduler 3.x docs (SQLAlchemyJobStore, misfire_grace_time, coalesce,
  triggers); write `stores/todos.py`, `scheduling/scheduler.py` (+ tasks table), tools
  `tools/builtin/{todos,schedule}.py`, reminder toasts; UI comes with the Island (phase 7) and
  Settings → Tasks page.
- Environment: Windows 11, Python 3.12.10 venv in `.venv`, Git 2.55, Inno Setup 6.7.3 (per-user,
  `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`).
- Commands: `.venv\Scripts\python -m pytest`, `.venv\Scripts\ruff check src tests`,
  `.venv\Scripts\python -m wisp`.

## Phases

- [x] 0 Setup: docs read, tracking files, repo, venv, ruff, pytest (commit 8f65be6)
- [x] 1 Skeleton, tray, settings, secrets — `wisp/app.py`, `settings.py`, `keystore.py`,
  `logging_setup.py`, `db.py`, `startup.py`, `single_instance.py`, `ui/tray.py`, `ui/settings/*`;
  tests `test_settings.py`, `test_keystore.py`, `test_db_and_startup.py`, `test_settings_ui.py`
- [x] 2 Audio + Live session + tool framework + safety layer — `audio/*`, `live/*`, `tools/*`,
  `hotkeys/*`, `winapi/input.py`, `voice.py`, `ui/{console,orb,confirm_card,bridge}.py`; tests
  `test_live_session.py` (fake server), `test_dispatcher.py`, `test_tools_core.py`,
  `test_hotkeys.py`, `test_voice.py`, `test_audio_and_config.py`, `test_audio_devices.py`
- [x] 3 F2 computer-control tools — `system/app_index.py`, `winapi/{windows,screen,uia,files}.py`,
  `tools/builtin/{apps,windows,web,screen,ui,files}.py`; tests `test_app_index.py`,
  `test_f2_tools.py`, `test_win_integration.py`
- [x] 4 F3 dictation — `dictation.py`, `ai/dictation.py`, `system/clipboard.py`, `ui/hud.py`; tests
  `test_dictation.py`, `test_dictation_request.py`
- [x] 5 F4 Circle to Ask — `circle.py`, `ui/overlay.py`, `ui/bubble.py`; tests `test_circle.py`
- [ ] 6 F5 to-dos + F6 scheduler
- [ ] 7 F7 Island
- [ ] 8 F8 memory, F9 loadout, F10 stats
- [ ] 9 F12 hardening
- [ ] 10 Packaging, installer, CI
- [ ] 11 Final audit

## Acceptance criteria

### F1 Voice core
- [x] F1.1 Push-to-talk via configurable hotkey — `test_hotkeys.py` (all), `spikes/hook_probe.py`,
  `test_voice.py::test_push_to_talk_round_trip`, `test_live_session.py::test_push_to_talk_turn`;
  manual MT-01
- [x] F1.2 Push-to-talk by clicking the orb — `test_voice.py::test_orb_click_toggles`; MT-02
- [x] F1.3 Optional always-listening mode using Live API VAD —
  `test_audio_and_config.py::test_always_listening_and_resume_handle`,
  `test_live_session.py::test_always_listening_streams_without_activity_markers`; MT-04
- [x] F1.4 Answers aloud (24 kHz PCM playback) — `test_audio_devices.py::test_player_opens_24khz_and_clears_instantly`,
  model audio routed to player in `test_live_session.py::test_push_to_talk_turn`; MT-01
- [x] F1.5 Calls tools mid-conversation — `test_live_session.py::test_tool_call_mid_conversation`
- [x] F1.6 Barge-in — `test_live_session.py::test_barge_in_clears_playback_locally_and_on_server_interrupt`,
  `test_audio_devices.py::test_player_opens_24khz_and_clears_instantly`; MT-03
- [x] F1.7 Context window compression — `test_audio_and_config.py::test_push_to_talk_config_disables_server_vad`
  (sliding window present in setup)
- [x] F1.8 Session resumption — `test_live_session.py::test_go_away_reconnects_with_latest_handle`,
  `::test_idle_timeout_closes_and_next_turn_resumes`, `::test_failed_resume_starts_fresh`
- [x] F1.9 GoAway → transparent reconnect — `test_live_session.py::test_go_away_reconnects_with_latest_handle`
- [x] F1.10 Backoff + clear status — `test_live_session.py::test_network_error_shows_status_and_recovers`,
  `::test_fatal_key_error_stops_retrying`, `test_voice.py::test_offline_state_visual`
- [x] F1.11 Idle timeout + reconnect on next use — `test_live_session.py::test_idle_timeout_closes_and_next_turn_resumes`,
  `::test_idle_not_triggered_while_speaking`; MT-08
- [x] F1.12 Text console — `ui/console.py`, `test_live_session.py::test_typed_text_uses_realtime_text`,
  `test_voice.py::test_typed_text_counts_as_user_evidence`; MT-05
- [x] F1.13 Mic-mute toggle — `test_voice.py::test_mute_persists_and_cancels_turn`; MT-06
- [~] F1.A Accept: 30-minute conversation — simulated in
  `test_live_session.py::test_long_conversation_survives_many_reconnects` (4 connections, GoAway ×2,
  network blip, 6 tool calls, handle continuity); real run MT-09
- [~] F1.B Accept: network unplug — simulated in `::test_network_error_shows_status_and_recovers`;
  real run MT-07

### F2 Computer-control tools
- [x] F2.1 open_app fuzzy over Start Menu + Store apps — `system/app_index.py`,
  `test_app_index.py` (all, incl. `test_real_apps_folder_enumerates`), `spikes/apps_folder.py`
- [x] F2.2 close / switch / minimise windows — `tools/builtin/windows.py`, `winapi/windows.py`;
  `test_win_integration.py::test_window_bounds_minimize_restore`; close is confirm-tier; MT-15
- [x] F2.3 web_search Google/YouTube/Amazon — `test_f2_tools.py::test_search_urls`,
  `::test_web_search_opens_default_browser`; MT-13
- [x] F2.4 look_at_screen — `tools/builtin/screen.py`; capture tested in
  `test_win_integration.py::test_screen_capture_of_window`; model side MT-12
- [x] F2.5 UIA list/click/type/scroll — `winapi/uia.py`, `tools/builtin/ui.py`;
  `test_win_integration.py::test_uia_click_and_type`, `::test_uia_reports_missing_element`;
  risk escalation `test_f2_tools.py::test_risky_click_names`; MT-14
- [x] F2.6 Open files/folders, recent files — `tools/builtin/files.py`;
  `test_f2_tools.py::test_resolve_known_folders`, `::test_recent_and_search_do_not_crash`
- [x] F2.7 Delete → Recycle Bin only + confirmation — `test_f2_tools.py::test_real_recycle` (opt-in,
  passed 2026-10-12), `::test_protected_paths`, `::test_delete_tool_metadata`; MT-16
- [~] F2.A Accept on clean Windows 11 — MT-11, MT-12, MT-13, MT-14 (needs your API key + machine)

### F3 Dictation
- [x] F3.1 Hold Ctrl+Win records; release sends to Gemini — `dictation.py`;
  `test_dictation.py::test_full_flow_pastes_and_restores`, `test_dictation_request.py::test_request_shape`
- [~] F3.2 Clean intended text — prompt + post-processing tested (`test_dictation.py::test_clean_output`,
  `::test_prompt_mentions_self_corrections`); model quality needs MT-18
- [x] F3.3 Paste + restore previous clipboard — `system/clipboard.py`;
  `test_dictation.py::test_real_clipboard_round_trip`, `::test_real_paste_into_focused_field` (opt-in,
  passed 2026-10-12), `::test_no_restore_if_clipboard_changed`, `::test_waits_for_modifiers_before_paste`
- [x] F3.4 No Start menu / virtual-desktop interference — chord logic `test_hotkeys.py::test_other_key_while_armed_spoils_chord`,
  `::test_hold_fires_after_timer_and_release_emits` (mask key requested); shell behaviour UNDOCUMENTED
  (D-009) → MT-10, MT-21
- [x] F3.5 Only when no other key and held > 250 ms — `test_hotkeys.py::test_short_tap_does_nothing`,
  `::test_other_key_while_active_cancels`, `::test_extra_modifier_means_different_chord`
- [~] F3.6 Accept: Notepad, browser text box, VS Code — MT-18, MT-19
- [x] F3.7 Words dictated → Stats — `test_dictation.py::test_full_flow_pastes_and_restores` (stats event)

### F4 Circle to Ask
- [x] F4.1 Hold Ctrl+Shift shows full-screen overlay (one per screen) — `ui/overlay.py`, `circle.py`;
  `test_circle.py::test_push_to_talk_flow_sends_image_before_closing_turn`; MT-22
- [x] F4.2 Freehand loop while speaking — `test_circle.py::test_overlay_crop_uses_physical_pixels`
  (real mouse events), question audio streamed during the gesture (same flow test)
- [x] F4.3 Crop bbox, send image + question — `test_circle.py::test_overlay_crop_uses_physical_pixels`,
  `::test_push_to_talk_flow_sends_image_before_closing_turn`, `::test_always_listening_buffers_and_replays_question`
- [x] F4.4 Answer aloud + text bubble — `ui/bubble.py`; bubble updates in the flow test; MT-22
- [x] F4.5 No interference with Ctrl+Shift+key — `test_circle.py::test_other_key_cancels`,
  `test_hotkeys.py::test_other_key_while_active_cancels`; overlays never take focus; MT-24
- [~] F4.6 Multi-monitor + scaling — `test_circle.py::test_map_to_pixmap_scales`,
  `::test_map_to_pixmap_secondary_monitor_left_of_primary`, `::test_real_screens_grab_at_physical_resolution`;
  real second monitor MT-23

### F5 To-do list
- [ ] F5.1 Add, complete, delete, list by voice
- [ ] F5.2 Add, complete, delete, list in UI
- [ ] F5.3 Optional due time with reminder toast
- [ ] F5.4 Shown in Island "Today" tab

### F6 Scheduled tasks and routines
- [ ] F6.1 One-off jobs
- [ ] F6.2 Recurring jobs
- [ ] F6.3 Model emits structured schedule_task; resolved tool calls stored and replayed without model
- [ ] F6.4 Jobs persist across restarts
- [ ] F6.5 Missed-job policy defined and documented
- [ ] F6.6 Toast after each run
- [ ] F6.7 List, edit, delete by voice
- [ ] F6.8 List, edit, delete in UI
- [ ] F6.9 Start with Windows setting

### F7 Island (works without API key)
- [ ] F7.1 Pill fixed top-centre, always on top, expands on hover or scroll
- [ ] F7.2 Controls tab: volume, output device, Wi-Fi, Bluetooth, Night Light, dark mode, brightness
- [ ] F7.3 Today tab (to-dos, upcoming jobs)
- [ ] F7.4 Stats tab
- [ ] F7.5 Clipboard tab
- [ ] F7.6 Apps tab
- [ ] F7.7 Wallpaper tab
- [ ] F7.8 Power tab (sleep/restart/shut down with confirmation)
- [ ] F7.9 Music strip: title, artist, progress, play/pause/next/previous
- [ ] F7.10 Clipboard history: last N text + image, searchable, re-copy, clear
- [ ] F7.11 Clipboard skips content marked excluded by password managers
- [ ] F7.A Accept: with no API key, Island, music strip, app launcher, clipboard history work and AI
  features show "add your key"

### F8 Memory
- [ ] F8.1 remember / recall / forget tools backed by SQLite
- [ ] F8.2 Only the few most relevant facts injected at session start
- [ ] F8.3 View, edit, delete all memories in Settings

### F9 Loadout
- [ ] F9.1 Voice slot (Gemini prebuilt voice)
- [ ] F9.2 Personality slot (presets + custom)
- [ ] F9.3 Appearance slot (theme + accent)
- [ ] F9.4 Skills slot (tool groups enabled)
- [ ] F9.5 Gap decision recorded

### F10 Stats
- [ ] F10.1 Words dictated, time saved (stated typing speed), commands run, routines executed — per
  day and per week

### F11 Settings and secrets
- [x] F11.1 API key stored with DPAPI, never logged or shown in full — tests
  `test_keystore.py::test_dpapi_round_trip`, `::test_mask_never_reveals_middle`,
  `::test_redacting_filter_removes_keys`, `::test_redacting_filter_cleans_tracebacks`; Settings shows
  only `mask(key)` (`ui/settings/general_page.py`)
- [ ] F11.2 Key validated with a test call on save
- [ ] F11.3 README note: UK/EEA/Swiss users need a billing-enabled key
- [ ] F11.4 Settings: hotkeys with conflict detection, mic + speaker device, idle timeout, start with
  Windows, risky-tool toggles, model name, language

### F12 Safety
- [x] F12.1 Risk tiers enforced in dispatcher — `tools/safety.py` + `tools/dispatcher.py`;
  `test_tools_core.py` (safety tests), `test_dispatcher.py::test_disabled_skill_is_denied_in_dispatcher`,
  `::test_model_cannot_confirm_without_user`
- [x] F12.2 Confirm tier needs spoken "yes" or a click — `test_dispatcher.py::test_confirm_flow_with_spoken_yes`,
  `::test_click_executes_and_notifies_model`, `::test_spoken_no_cancels`,
  `::test_scheduled_confirm_waits_for_click`, `test_live_session.py::test_spoken_yes_confirms_through_transcription`;
  card `ui/confirm_card.py`
- [ ] F12.3 Terminal + raw mouse/keyboard disabled by default behind Settings toggle
- [ ] F12.4 Screen/web/file text is untrusted; confirm-tier after reading it always asks
- [ ] F12.5 Action log of every tool call, viewable in Settings
- [ ] F12.6 Never bypasses UAC, secure desktop, lock screen, anti-cheat; explains the limit

### Testing, packaging, definition of done
- [ ] T.1 Unit tests: dispatcher, safety tiers, scheduler parsing + persistence, memory, clipboard store,
  settings (Windows-only tests marked)
- [ ] T.2 Integration tests with fake Live session replaying scripted tool calls
- [ ] T.3 MANUAL_TESTS.md runnable in ~20 minutes
- [ ] T.4 GitHub Actions on windows-latest: lint + tests + PyInstaller exe
- [ ] D.1 Installer installs, launches at login, uninstalls cleanly
- [ ] D.2 Stub/placeholder grep returns nothing
- [ ] D.3 README complete
- [ ] D.4 Final report

## Log

- 2026-10-12: Phase 0 started. Installed Python 3.12.10 (py install manager), Git, Inno Setup (winget),
  with user approval. Project at `C:\Users\mathi\Documents\Wisp`.
