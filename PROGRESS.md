# Wisp — progress tracker

Resume rule: a fresh session reads this file, then `DECISIONS.md` and `SOURCES.md`, then continues at
"Next step". Commit after every phase.

Legend: `[x]` done with evidence · `[~]` implemented, automated evidence where possible, but the
acceptance step needs real hardware/API key and is listed in `MANUAL_TESTS.md` (not yet run) ·
`[ ]` not done.

## Status

- Current phase: 9 — F12 hardening (not started)
- Phase 8 done: `stores/memory.py`, `tools/builtin/memory.py`, `ui/settings/{memories,loadout}_page.py`,
  loadout validation in `settings.py`; tests `test_memory.py`, `test_loadout_memories_ui.py`,
  `test_stats.py`; D-032/D-033; MT-35…MT-38.
- Next step: phase 9 (F12 hardening + remaining F11). Needed: Settings → Safety page (terminal /
  raw-input toggles F12.3, auto-approve list, taint minutes; the Loadout tooltip already points
  to it), terminal + raw input tools behind those toggles, action-log viewer page (F12.5),
  F12.4/F12.6 evidence, F11.2 (key test on save — `general_page._test_and_save` exists, check
  coverage), F11.4 Settings for hotkeys/devices/risky tools/model/language (General page has
  model/language/idle/startup; hotkeys + devices pages missing).
- Known gap: `README.md` does not exist yet although `pyproject.toml` names it and F6.5 cites it
  (the policy itself is in D-029). Write it in phase 10 (D.3); `pip install .` needs it.
- Safety note for automated runs: never toggle the user's Night Light/Wi-Fi/Bluetooth/theme/
  volume/output device in tests on this PC; test write paths with pure functions + manual tests.
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
- [x] 6 F5 to-dos + F6 scheduler — `stores/todos.py`, `scheduling/*`, `tools/builtin/{todos,schedule}.py`,
  `ui/settings/routines_page.py`; tests `test_todos.py`, `test_schedule_spec.py`, `test_scheduler.py`,
  `test_schedule_tools.py`, `test_routines_ui.py`
- [x] 7 F7 Island — `system/{controls,media,radios,wallpaper,power,clipboard_monitor}.py`,
  `stores/clipboard_history.py`, `winapi/shell_icons.py`, `tools/builtin/system.py`, `ui/island/*`;
  tests `test_system_controls.py`, `test_clipboard_history.py`, `test_island.py`
- [x] 8 F8 memory, F9 loadout, F10 stats — `stores/memory.py`, `tools/builtin/memory.py`,
  `ui/settings/{memories,loadout}_page.py`, `stores/stats.py`; tests `test_memory.py`,
  `test_loadout_memories_ui.py`, `test_stats.py`
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
- [x] F5.1 Add, complete, delete, list by voice — `tools/builtin/todos.py`, `test_todos.py::test_tools`;
  MT-25
- [x] F5.2 Add, complete, delete, list in UI — `ui/island/today_tab.py`;
  `test_island.py::test_today_add_complete_delete`; MT-33
- [x] F5.3 Due time + reminder toast — `stores/todos.py`, `WispApp._check_reminders`;
  `test_todos.py::test_reminders_fire_once`, `::test_update_resets_reminder`; MT-25
- [x] F5.4 Shown in Island "Today" tab — `test_island.py::test_today_add_complete_delete`,
  `::test_today_due_time_is_shown`; MT-25, MT-33

### F6 Scheduled tasks and routines
- [x] F6.1 One-off jobs — `test_schedule_spec.py::test_one_off_amazon_example`,
  `test_scheduler.py::test_one_off_runs_notifies_and_disables`, `test_schedule_tools.py::test_amazon_one_off`
- [x] F6.2 Recurring jobs — `test_schedule_spec.py::test_every_morning_at_nine`, `::test_weekdays_and_weekly`,
  `::test_monthly_and_hourly`, `test_scheduler.py::test_recurring_next_run_unschedule_and_sync`
- [x] F6.3 Structured schedule_task; resolved calls replayed without model —
  `test_schedule_tools.py::test_every_morning_routine_stores_resolved_calls`,
  `::test_model_schedules_routine_then_it_replays_without_model` (fake Live session)
- [x] F6.4 Persist across restarts — `test_scheduler.py::test_job_persists_and_runs_late_after_restart`; MT-28
- [x] F6.5 Missed-job policy defined + documented — DECISIONS.md D-029 (README in phase 10);
  `test_scheduler.py::test_missed_beyond_grace_is_reported`, `::test_grace_policy`
- [x] F6.6 Toast after each run — `test_scheduler.py::test_one_off_runs_notifies_and_disables`
  (notification text), `WispApp._execute_task` (✓/✗ per step)
- [x] F6.7 List, edit, delete by voice — `test_schedule_tools.py::test_prompt_step_list_update_delete_run`,
  `::test_move_one_off_keeps_date`; MT-27
- [x] F6.8 List, edit, delete in UI — `ui/settings/routines_page.py`; `test_routines_ui.py` (all)
- [x] F6.9 Start with Windows setting — `startup.py` + General page; `test_db_and_startup.py::test_run_key_toggle`

### F7 Island (works without API key)
- [x] F7.1 Pill fixed top-centre, always on top, expands on hover or scroll — `ui/island/island.py`;
  `test_island.py::test_pill_is_frameless_on_top_and_centred`, `::test_hover_expands_and_leaving_collapses`,
  `::test_scroll_expands`, `::test_tabs_refresh_when_shown`; D-031
- [~] F7.2 Controls tab: volume, output device, Wi-Fi, Bluetooth, Night Light, dark mode, brightness —
  `ui/island/controls_tab.py`, `system/controls.py`, `system/radios.py`; pure/fake tests
  `test_system_controls.py` (Night Light blob round trip, volume/brightness/output/toggle tools);
  real writes are not run on this PC (safety rule) → MT-30; UNDOCUMENTED parts D-030
- [x] F7.3 Today tab (to-dos, upcoming jobs) — `test_island.py::test_today_add_complete_delete`
- [x] F7.4 Stats tab — `ui/island/stats_tab.py`; `test_island.py::test_stats_tab_shows_today_and_week`
- [x] F7.5 Clipboard tab — `ui/island/clipboard_tab.py`; store tests `test_clipboard_history.py`; MT-29
- [x] F7.6 Apps tab — `ui/island/apps_tab.py`; `test_island.py::test_apps_tab_search_and_launch`,
  `::test_shell_icon_keeps_alpha`; MT-29
- [x] F7.7 Wallpaper tab — `ui/island/wallpaper_tab.py`, `system/wallpaper.py`;
  `test_island.py::test_wallpaper_lists_images_recursively`, `::test_wallpaper_rejects_non_images`; MT-34
- [x] F7.8 Power tab (sleep/restart/shut down with confirmation) — `ui/island/power_tab.py`;
  `test_island.py::test_power_tab_asks_before_restart_and_logs`, `::test_power_tab_lock_needs_no_question`;
  voice tool confirm-tier `test_system_controls.py::test_power_actions_except_lock_need_confirmation`; MT-34
- [x] F7.9 Music strip: title, artist, progress, play/pause/next/previous — `system/media.py`,
  `ui/island/music.py`; `test_island.py::test_music_strip`, `test_system_controls.py::test_current_position_adds_elapsed_only_while_playing`,
  `::test_media_tool_status_and_command`; real session `spikes/winrt_in_loop_thread.py`; MT-29
- [x] F7.10 Clipboard history: last N text + image, searchable, re-copy, clear —
  `test_clipboard_history.py` (dedupe, prune, literal search, images, clear); re-copy MT-29
- [x] F7.11 Clipboard skips content marked excluded by password managers —
  `test_clipboard_history.py::test_monitor_skips_password_manager_content`; marker detection on the real
  clipboard `test_dictation.py::test_real_clipboard_round_trip`; MT-32
- [~] F7.A Accept: with no API key, Island, music strip, app launcher, clipboard history work and AI
  features show "add your key" — `test_island.py::test_status_without_key_and_with_music`; MT-29

### F8 Memory
- [x] F8.1 remember / recall / forget tools backed by SQLite — `test_memory.py::test_remember_recall_forget_tools`,
  `::test_remember_replaces_older_fact`, `::test_add_search_update_delete`, `::test_search_survives_fts_operators`;
  taint escalation `::test_tainted_session_asks_before_remember`; MT-35
- [x] F8.2 Only the few most relevant facts injected at session start — D-032;
  `test_memory.py::test_session_facts_pinned_then_used_then_recent`, `::test_session_facts_respect_character_budget`,
  `::test_instruction_lists_facts_as_data_and_only_with_memory_skill`
- [x] F8.3 View, edit, delete all memories in Settings — `ui/settings/memories_page.py`;
  `test_loadout_memories_ui.py::test_memories_*`; MT-35

### F9 Loadout
- [x] F9.1 Voice slot (Gemini prebuilt voice) — `ui/settings/loadout_page.py`;
  `test_loadout_memories_ui.py::test_loadout_round_trip`, `::test_voice_and_skills_reach_live_config`; MT-36
- [x] F9.2 Personality slot (presets + custom) — `::test_loadout_round_trip`,
  `::test_personality_reaches_instruction`, `::test_custom_accent_and_too_long_personality`; MT-36
- [x] F9.3 Appearance slot (theme + accent) — `::test_loadout_round_trip`, `::test_validate_loadout_values`;
  applied live by `WispApp._on_settings_changed`; MT-36
- [x] F9.4 Skills slot (tool groups enabled) — `::test_voice_and_skills_reach_live_config`; dispatcher
  denial `test_dispatcher.py::test_disabled_skill_is_denied_in_dispatcher`; MT-37 (terminal/input also
  need the Safety page, phase 9)
- [x] F9.5 Gap decision recorded — DECISIONS.md D-033

### F10 Stats
- [x] F10.1 Words dictated, time saved (stated typing speed), commands run, routines executed — per
  day and per week — `stores/stats.py`, Island Stats tab; `test_stats.py` (all),
  `test_island.py::test_stats_tab_shows_today_and_week`; MT-38

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
- 2026-10-13: Phase 7 finished (tests, D-030/D-031, sources, MT-29…MT-34). Added
  `winrt-Windows.Foundation.Collections` to pyproject; clipboard search now treats % and _ literally.
- 2026-10-13: Phase 8 finished (memory, loadout page, stats tests, D-032/D-033, MT-35…MT-38).
