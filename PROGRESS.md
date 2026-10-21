# Wisp — progress tracker

Resume rule: a fresh session reads this file, then `DECISIONS.md` and `SOURCES.md`, then continues at
"Next step". Commit after every phase.

Legend: `[x]` done with evidence · `[~]` implemented, automated evidence where possible, but the
acceptance step needs real hardware/API key and is listed in `MANUAL_TESTS.md` (not yet run) ·
`[ ]` not done.

## Status

- Current phase: all phases done (0–11), plus the briefs of 2026-10-13 (speech fix, part 1; UI polish,
  part 2; Dynamic Island, part 3; part 4: font warning, auto-hide, Calendar tab, Files & Share tab) and
  of 2026-10-14 (Screen Assist + Watch mode, part 1; Discreet mode, part 2), and the fixes of 2026-10-16
  (Screen Assist's closed client, D-054; a silent microphone, D-055) and of 2026-10-20 (empty capture
  rectangles, D-056; Gemini's "high demand", D-057; a press that ended in nothing, D-058; CI, D-059).
  On GitHub (github.com/Mathias-D06/Wisp) with CI green. Remaining work needs a person: the
  MANUAL_TESTS core run and the extended cases (API key + microphone, MT-01…MT-124: a Google account
  for MT-82…MT-89, a phone on a Private Wi-Fi for MT-94…MT-96, Gemini answering for MT-98…MT-124 — it
  returned 503 "high demand" during the builds). The laptop's AMD microphone array delivers almost no
  signal to any program (MT-116, D-060): check its mute key, driver or input choice. MIT-licensed;
  releases are published by CI from a version tag. See FINAL_REPORT.md.
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
- [x] 9 F12 hardening — `tools/builtin/{terminal,raw_input}.py`, `winapi/processes.py`,
  `ui/settings/{safety,hotkeys_audio,action_log}_page.py`; tests `test_hardening.py`,
  `test_safety_settings_ui.py`
- [x] 10 Packaging, installer, CI — `packaging/*`, `wisp/selfcheck.py`, `.github/workflows/ci.yml`,
  `README.md`; tests `test_packaging.py`
- [x] 11 Final audit — reference audit (every cited test/file/MT/D exists), pins = installed =
  SOURCES, fresh `git clone` build green, suite green 3× idle + 2× under full CPU load; fixed:
  StatsTab shadowing `QWidget::metric` (TypeError on every settings save), leaked ClipboardMonitor
  connections + unguarded store write in a Qt slot, a timing-sensitive scheduler test, item-view check
  indicators; FINAL_REPORT.md

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
- [x] F6.5 Missed-job policy defined + documented — DECISIONS.md D-029, README "Scheduled tasks";
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
- [x] F11.2 Key validated with a test call on save — `general_page._test_and_save` (`models.get` for both
  models); `test_safety_settings_ui.py::test_key_is_tested_before_saving`,
  `test_settings_ui.py::test_bad_key_is_rejected_before_network`
- [x] F11.3 README note: UK/EEA/Swiss users need a billing-enabled key — README "Your Gemini API key"
  (checked against ai.google.dev/gemini-api/terms); also in Settings → General and key-test errors
- [x] F11.4 Settings: hotkeys with conflict detection, mic + speaker device, idle timeout, start with
  Windows, risky-tool toggles, model name, language — General (key, models, language, idle, start-up),
  Hotkeys and audio, Safety pages; `test_safety_settings_ui.py::test_hotkeys_live_conflicts_and_audio`,
  `::test_missing_audio_device_is_kept_and_labelled`, `::test_safety_toggle_also_ticks_skill_and_loadout_follows`,
  `test_settings_ui.py`; MT-39

### F12 Safety
- [x] F12.1 Risk tiers enforced in dispatcher — `tools/safety.py` + `tools/dispatcher.py`;
  `test_tools_core.py` (safety tests), `test_dispatcher.py::test_disabled_skill_is_denied_in_dispatcher`,
  `::test_model_cannot_confirm_without_user`
- [x] F12.2 Confirm tier needs spoken "yes" or a click — `test_dispatcher.py::test_confirm_flow_with_spoken_yes`,
  `::test_click_executes_and_notifies_model`, `::test_spoken_no_cancels`,
  `::test_scheduled_confirm_waits_for_click`, `test_live_session.py::test_spoken_yes_confirms_through_transcription`;
  card `ui/confirm_card.py`
- [x] F12.3 Terminal + raw mouse/keyboard disabled by default behind Settings toggle — D-034;
  `test_hardening.py::test_terminal_and_raw_input_off_by_default`, `::test_terminal_needs_toggle_and_skill_then_always_asks`,
  `::test_raw_input_tiers_when_enabled`, `::test_run_command_*`, `::test_mouse_click_maps_and_needs_a_recent_screenshot`; MT-40…MT-42
- [x] F12.4 Screen/web/file text is untrusted; confirm-tier after reading it always asks — D-012/D-019;
  `test_dispatcher.py::test_untrusted_output_is_wrapped_and_taints`, `test_tools_core.py::test_auto_approve_ignored_when_tainted_and_for_schedules`,
  `test_hardening.py::test_auto_approve_limits`, `test_memory.py::test_tainted_session_asks_before_remember`; MT-45
- [x] F12.5 Action log of every tool call, viewable in Settings — `ui/settings/action_log_page.py`;
  `test_safety_settings_ui.py::test_action_log_*`, `test_hardening.py::test_action_log_prunes_and_redacts`,
  `test_dispatcher.py::test_safe_tool_runs_and_is_logged`; MT-41
- [x] F12.6 Never bypasses UAC, secure desktop, lock screen, anti-cheat; explains the limit — D-022, D-035;
  `test_hardening.py::test_refuses_secure_desktop_and_elevated_windows`, `::test_refuses_fullscreen_window_while_anti_cheat_runs`,
  `::test_look_at_screen_refuses_secure_desktop`, `::test_instruction_states_the_limits`, `::test_real_secure_desktop_probe_and_window_at`;
  MT-17, MT-43, MT-44

### Speech recognition fix (brief of 2026-10-13, part 1)
- [x] S.1 Audio format: native capture + conversion to 16 kHz mono int16, `audio/pcm;rate=16000` —
  `audio/convert.py`, `audio/capture.py`; `test_audio_convert.py` (48 kHz stereo float32 → length, rate,
  dtype, frequency, level; dead array channels; anti-aliasing; 44.1 kHz; passthrough),
  `test_speech_pipeline.py::test_native_4ch_48k_float_capture_reaches_subscribers_as_16k_mono`,
  `::test_device_refusing_native_format_falls_back_to_16k_mono`; D-039
- [~] S.2 Debug WAV of exactly what is sent — `audio/debug_wav.py`, Settings switch + Test microphone;
  `test_speech_pipeline.py::test_session_saves_the_exact_bytes_sent`, `::test_recorder_writes_exactly_what_was_added`,
  `::test_mic_test_report_in_plain_english`; listening check MT-50, MT-51
- [x] S.3 Clipped starts: 300 ms pre-roll on push-to-talk arm; activity signals correct; VAD values
  700/200 ms unchanged — `test_voice.py::test_push_to_talk_hotkey_opens_mic_on_arm_and_sends_preroll`,
  `test_hotkeys.py::test_arm_and_disarm_events`, `test_live_session.py::test_speech_after_a_pause_sends_everything_in_order`; MT-52
- [x] S.4 Language lock (default English (UK), firm instruction, `en-GB` transcription hint; docs say native
  audio has no language code) — `test_speech_pipeline.py::test_default_language_is_english_uk_with_a_firm_rule`,
  `::test_transcription_gets_a_language_hint`, `::test_old_plain_english_setting_becomes_english_uk`; D-040; MT-56
- [x] S.5 Real errors, never "None"; Retry — `test_live_session.py::test_precondition_close_reason_is_shown`,
  `::test_bad_key_close_reason_gives_the_key_message`, `::test_error_detail_lists_type_code_and_reason`;
  real invalid-key probe 2026-10-13; D-041; MT-55
- [x] S.6 One "You:" line per turn — `test_live_session.py::test_user_words_stay_on_one_row_per_turn`; D-041
- [x] S.7 Silence/taps never sent (the cause of "¿Qué?") — `test_live_session.py::test_silent_turn_is_not_sent_and_explained`,
  `::test_tap_sends_nothing_and_hints`, `test_dictation.py::test_silent_dictation_is_never_sent`,
  `test_voice.py::test_talk_button_click_or_hold`, `::test_orb_click_toggles`; MT-53, MT-54
- [~] S.A Accept: 10 English phrases 10/10 on the laptop mic — 10/10 through the full pipeline with
  synthesised speech in the array's format against the real API (2026-10-13); real mic MT-51

### UI polish (brief of 2026-10-13, part 2)
- [x] U.1 One token module for every window (colour, type, spacing, radii, shadow, motion); no hard-coded
  styles — `ui/theme.py`, `ui/motion.py`; `test_ui_design.py::test_no_hard_coded_colours_outside_the_theme`,
  `::test_type_scale_and_shape_tokens`; D-043
- [x] U.2 Near-black cool palette, two surfaces, three text levels, WCAG AA in both modes (worst 4.91:1 dark,
  4.81:1 light); readable accent buttons for any accent — `::test_text_meets_wcag_aa_on_every_surface`,
  `::test_accent_buttons_are_readable_for_any_accent`
- [x] U.3 Segoe UI Variable (Small/Text/Display cut by size), 12/13/15/20, Regular + Semibold (titles only),
  sentence case, 145 % transcript line height — `::test_type_follows_the_windows_minimums`
- [x] U.4 4/8 spacing grid, radii 8 (controls) / 12 (panels), hairline borders — `::test_type_scale_and_shape_tokens`
- [~] U.5 Mica + rounded corners + themed title bar, Windows 10 fallback — `winapi/dwm.py`, `ui/chrome.py`;
  `::test_chrome_never_fails_and_honours_no_mica`, `::test_theme_change_after_widgets_are_deleted`; DWM accepts
  every attribute on build 26200 (S_OK); title bar and corners in `docs/screenshots/after/onscreen`; D-042. Seeing
  Mica needs an active window: MT-57. No Windows 10 PC here: MT-63
- [x] U.6 One line icon set (Lucide 1.56.0, ISC; Feather-derived icons also MIT) as tinted SVG, licence in SOURCES
  and THIRD_PARTY_NOTICES — `ui/iconset.py`, `assets/icons`; `::test_every_icon_exists_and_has_its_licence`,
  `::test_icons_render_sharp_at_each_scale`, `::test_stroke_is_the_same_visual_weight_at_any_size`,
  `test_packaging.py::test_notices_carry_the_icon_licence`
- [x] U.7 App and tray orb icon crisp at 16/24/32/48/256 (drawn per size; `packaging/wisp.ico` regenerated) —
  `ui/icons.py`; `::test_app_icon_is_drawn_natively_at_every_size`; MT-63
- [x] U.8 Console: icon toggles instead of check boxes, message rows, orb states, restyled composer and buttons,
  thin hover-only scrollbars, Retry — `ui/console.py`, `ui/transcript.py`, `ui/widgets.py`;
  `::test_console_rows_merge_per_turn`, `::test_console_retry_shows_only_after_an_error`,
  `::test_console_toggles_and_composer`, `::test_console_trims_old_rows`; MT-57, MT-58
- [x] U.9 Same treatment for the Island, Settings, overlay and Wisp's popups (native Windows toasts can't be
  styled; D-043) — `::test_hud_tones_come_from_the_palette`, `::test_hud_ticks_only_while_a_level_is_shown`,
  `test_circle.py::test_overlay_loop_is_outlined_not_filled`; screenshots; MT-59, MT-61
- [x] U.10 Motion only on state changes (120/180/250 ms, OutCubic); the orb is the one living element; off with
  Windows "Animation effects" or Settings → Loadout → Reduce motion; timers stop when hidden — `ui/motion.py`,
  `ui/orb.py`; `::test_motion_follows_setting_and_windows`, `::test_animate_jumps_to_the_end_without_motion`,
  `::test_toggle_switch_slides_with_motion`, `::test_orb_timer_runs_only_when_visible_and_moving`,
  `::test_orb_frames_by_state`, `test_island.py::test_expand_and_collapse_animate_when_motion_is_on`,
  `::test_reduce_motion_jumps_straight_to_the_end`; D-044; MT-60
- [x] U.11 Idle CPU (`spikes/idle_cpu.py 60`: Island visible, no key, whole process tree, % of one core, this PC,
  2026-10-13): before (commit 48bdfe8, clean export) **6.17 %**; after **3.28 %**; after with Reduce motion
  **0.29 %**. The orb's idle glow runs at 8 fps, and voice visuals and the Island status update only on change —
  `test_voice.py::test_visual_is_emitted_only_on_change`; D-044
- [~] U.A Accept: before/after screenshots in `docs/screenshots` (17 screens each, plus 100/125/150 % renders and
  an on-screen capture of the console); no regressions, suite green; sharp at 100/125/150 % in true-scale renders and the icon
  tests; idle CPU logged (U.11). Smoothness on a real display and real scaling: MT-59, MT-62

### Dynamic Island (brief of 2026-10-13, part 3)
- [x] I.1 One island surface replaces the console window, the old pill, the HUD, the answer bubble and
  tray toasts: idle, sliver, activity, split, banner, expanded — `ui/island/{island,machine,content,
  geometry,spring,panel,feedback}.py`, `ui/chat.py`; `test_island_core.py`, `test_island_window.py`; D-045
- [x] I.2 Priority in one place (voice > banner > timer > music > idle, `machine.TIERS`) —
  `test_island_core.py::test_priority_order_is_defined_once`,
  `::test_voice_beats_timer_beats_music_and_split_shows_two`; D-045
- [~] I.3 Live activities: listening (mic waveform), thinking, speaking (first words, output bars),
  dictation (level), music (album art, equaliser from IAudioMeterInformation), countdown, short status —
  `ui/island/content.py`, `system/audio_meter.py`, `system/media.py::read_thumbnail`; stills in
  `docs/island/stills`; `test_island_window.py::test_speaking_shows_the_first_words_of_the_reply`,
  `::test_media_art_and_the_panel_strip`, `test_island_core.py::test_countdown_*`. No media session was
  playing on this PC while this was built, so real album art is MT-66
- [x] I.4 Split (two activities: pill + detached circle) — `test_island_core.py::test_split_circle_sits_beside_the_pill_and_the_group_is_centred`,
  `::test_input_region_is_the_visible_shape_only`; `docs/island/split_music_and_voice.gif`
- [x] I.5 Banners: hold 3 s (longer while hovered), queue one at a time, coalesce, stale ones dropped,
  click action, swipe/scroll up to dismiss — `test_island_core.py::test_banner_*`, `::test_banners_queue_*`,
  `::test_hover_holds_a_banner_*`, `::test_stale_banners_are_dropped`, `test_island_window.py::test_swipe_up_*`,
  `::test_orb_click_talks_and_banner_click_runs_its_action`; `docs/island/banner_routine_done.gif`
- [x] I.6 Expanded panel: Chat (transcript + text box) first, the existing tabs, now playing, current
  reply; collapses on leave (0.5 s), Esc, click outside; "Open in window" keeps the console —
  `test_island_window.py::test_panel_has_chat_first_and_open_in_window`, `::test_esc_collapses_and_dismisses`
- [x] I.7 Motion: one continuous shape, springs (overshoot when growing, none when shrinking),
  interruptions retarget from the current size and speed, capsule radius, content fades and scales,
  panel rows staggered 20 ms — `test_island_core.py::test_spring_*`, `::test_retarget_mid_flight_has_no_jump`,
  `test_island_window.py::test_expand_springs_*`, `::test_collapse_never_overshoots_and_interrupting_never_jumps`,
  `::test_radius_stays_a_capsule_while_compact`, `::test_content_fades_and_scales_between_states`; GIFs; D-047
- [x] I.8 Windows "Animation effects" off or Reduce motion: shape jumps, content crossfades —
  `test_island_window.py::test_reduce_motion_jumps_the_shape_and_crossfades_content`; MT-60
- [~] I.9 Window: frameless, translucent, topmost tool window (no taskbar button, no Alt+Tab), never
  takes focus except a click into a text box, fixed canvas (never resized), input region = the shape,
  shadow in a click-through window, top centre of the chosen display — `test_island_window.py::test_native_styles_and_the_foreground_is_never_taken`,
  `::test_canvas_is_fixed_size_at_the_top_centre`, `::test_clicks_beside_the_shape_reach_the_app_underneath`
  (WindowFromPoint) (passed on this PC; skips while the lock screen is up), `::test_text_box_click_takes_focus_and_collapse_gives_it_back`; probes
  `spikes/island_window_probe.py`, `spikes/island_focus_probe.py`; D-046. Real typing, clicks, multiple
  displays and scaling: MT-70, MT-71, MT-74, MT-62
- [x] I.10 Hidden while a full-screen app or game is in front (SHQueryUserNotificationState + the
  foreground window covering the island's monitor) — `winapi/fullscreen.py`;
  `test_island_core.py::test_fullscreen_decision`, `test_island_window.py::test_full_screen_apps_hide_the_island`;
  on this PC a full-screen window in front (QUNS_BUSY, covering the monitor) was detected; D-046; MT-73
- [x] I.11 Interaction: hover grows 4 %, hover 300 ms or click expands, scroll down/up, right-click menu
  (Settings, Mute, Open in window, Quit), music click = play/pause, hotkey Ctrl+Alt+Space, Esc via the
  keyboard hook — `test_island_window.py::test_hover_*`, `::test_scroll_*`, `::test_right_click_menu`,
  `::test_compact_music_click_*`, `::test_esc_watch_follows_expansion`; MT-64, MT-72
- [x] I.12 Services send events to the IslandStateMachine (voice, dictation, Circle to Ask, media,
  reminders and routines, notifications), with the old HUD/bubble/toasts as fallbacks when the island is
  off or hidden — `ui/island/feedback.py`, `app.py`; `test_island_window.py::test_feedback_adapter_*`,
  `::test_circle_answer_*`, `::test_voice_messages_become_banners`, `::test_notifications_*`; MT-69, MT-76
- [x] I.13 Every island size, spring and timing in the theme tokens (`theme.ISLAND`)
- [x] I.14 Performance — morphs at 62 fps, p95 frame ≤ 18 ms, worst 23 ms, paint 1–2 ms
  (`spikes/island_fps.py`, this PC, 2026-10-13); the frame timer runs only while something moves
  (`test_island_window.py::test_frame_timer_only_runs_while_something_moves`). Idle CPU: 0.44 % of one core while visible and idle with the orb's glow (0.42 % with Reduce motion) against 5.99 % for the old island measured the same way (`spikes/island_idle_cpu.py`: in-process, island visible, 30 s warm-up, 60 s); 0.21 % while hidden behind a full-screen app (`spikes/idle_cpu.py`)
- [x] I.15 Unit tests: state machine (priorities, interruptions, banner queue, timeouts), springs (settle,
  retarget without jumps, no overshoot on collapse), click-through region — `test_island_core.py`
- [x] I.16 MANUAL_TESTS: MT-64…MT-77 (every state and transition, displays, scaling, full screen, focus while
  typing elsewhere) plus updated MT-01/04/05/07/22/29/53/55/59/60/61; core run step 15
- [~] I.A Accept: the voice flow is one fluid shape (`docs/island/voice_flow.gif`, morph tests); music +
  voice splits (GIF, tests); a routine's banner returns to idle by itself (GIF, tests); typing elsewhere never
  loses focus (native styles + foreground-unchanged test; real typing MT-70); clicks beside reach the app
  (WindowFromPoint test; MT-71); recordings in `docs/island` (rendered from the widget rather than
  recorded from the screen, D-045; your own recording MT-77); suite green; docs updated

### Brief of 2026-10-13, part 4 (font warning, auto-hide, Calendar, Files & Share)
- [x] P4.1 No QFont point-size warning: the application font is sized in points (`theme.app_font`), pixel
  fonts only where widgets/painters set their own — `test_ui_design.py::test_app_font_is_point_sized_and_renders_at_the_body_size`,
  `::test_calendar_popup_raises_no_point_size_warning_with_the_app_font` (fails with the old font); probe
  over start-up, every tab, Settings and the menu; same 13 px at 100/125/150/200 %; D-048; MT-78
- [x] P4.2 Auto-hide: the idle island slides up and fades after 3–15 s (default 6), never while voice, dictation,
  a banner (showing or queued), a countdown, a confirmation, the pointer or the expanded panel is there, music
  keeps it (setting); once out of view its window is hidden (nothing blocked) — `machine.hideable`,
  `test_island_core.py::test_idle_island_slides_away_*`, `::test_never_hides_while_something_is_going_on`,
  `::test_music_keeps_it_visible_unless_switched_off`, `::test_full_screen_doesnt_bring_a_hidden_island_back`,
  `test_island_window.py::test_idle_island_slides_up_fades_and_then_hides_its_window`,
  `::test_a_waiting_confirmation_keeps_it_visible`, `test_settings.py::test_island_hiding_defaults_and_range`; D-049
- [~] P4.2b Reveal: pointer resting 150 ms in the top-centre zone (pill width + 40 px each side, top 3 px), in
  device-independent px per display, polled ~30 Hz only while hidden; voice, banners, reminders, the hotkey reveal
  at once — `reveal.py`; `test_island_core.py::test_hot_zone_*`, `::test_dwell_needs_a_short_rest_in_the_zone`,
  `::test_activity_reveals_instantly`, `test_island_window.py::test_resting_in_the_top_centre_zone_reveals_it`,
  `::test_hotkey_and_voice_reveal_a_hidden_island`; idle CPU 0.52 % of one core while slid away (the ~30 Hz reveal poll) against 0.36 % while visible and idle, with or without the orb's glow (in-process, 30 s warm-up, 60 s); real pointer, displays and scaling: MT-79…MT-81;
  `docs/island/autohide_and_reveal.gif`
- [~] P4.3 Calendar tab (replaces Wallpaper; wallpaper → Settings → Loadout and a new `wallpaper` voice tool) —
  `gcal/{google,sync,store,times,service}.py`, `ui/island/calendar_tab.py`, `ui/settings/accounts_page.py`,
  `tools/builtin/calendar.py`, `ui/wallpaper_picker.py`. Own Desktop app client, loopback + PKCE, read-only scopes
  (`calendar.events.owned` only when switched on; owned calendars only), DPAPI tokens, reconnect/disconnect +
  revoke; sync tokens, 410 → full sync, weekly window, 5-min schedule with backoff; SQLite cache; colours and
  shown calendars; agenda + month; island heads-up; Europe/London DST — `test_gcal.py` (21: sync merge, 410,
  window, offline after restart, backoff, DST gap/overlap/durations, all-day, encrypted tokens, error mapping,
  request parameters, connect/disconnect/reconnect/create), `test_calendar_ui.py` (9: tools and confirm text,
  tab states, month, click → browser, Accounts page, wallpaper tool/picker, app tabs), `test_settings.py`;
  self-check `google_calendar`; `docs/island/calendar_tab.gif` (made-up data); D-050; a real account: MT-82…MT-89
- [~] P4.4 Files & Share tab (replaces Apps) — `files/{finder,shelf,actions,names,resolve}.py`,
  `phone/{network,server,service,qr}.py`, `winapi/{share,winrt_abi}.py`, `ui/island/files_tab.py`, island drops,
  `tools/builtin/share.py`. Search via the Windows Search index (ADO) with fuzzy ranking and a folder-walk
  fallback; shelf in SQLite with thumbnails, drag in/out; Recent and Downloads; quick actions (Recycle Bin only,
  confirmed); share sheet via IDataTransferManagerInterop (ctypes, metadata-checked slots, probe opened it); phone
  link: Private network only, 256-bit token, first device owns it, 10 minutes, ask-then-send with Accept on the PC,
  size limit (Settings → Safety), sanitised names in Downloads\Wisp, banner, island "Phone link" activity, never
  logged — `test_files.py` (32: names, shelf persistence, actions incl. Recycle-Bin-only, SQL escaping, fuzzy
  ranking, fallback, Downloads, "this"), `test_phone.py` (19: network rule, token, device, approval flow,
  timeout/size/short uploads, downloads, auto-stop, no token in logs, service, QR), `test_files_ui.py` (11: tab,
  drop on the island, activity, tools, WinRT IIDs, Python COM objects, StorageFile); self-check `files_share`;
  `docs/island/files_and_share.gif` (made-up files); D-051; real phone, share targets, firewall: MT-90…MT-97

### Brief of 2026-10-14: Screen Assist + Discreet mode
- [~] S.1 Screen Assist — `assist/{engine,client,prompts,privacy,imaging,service}.py`, `ui/island/assist_tab.py`
  (Screen tab), `ui/settings/assist_page.py`, `tools/builtin/screen.py` (screen_assist, watch_screen; blocklist in
  look_at_screen), Circle to Ask masking, `stores/usage.py`. Hotkey Ctrl+Alt+Space (capture on press, spoken
  question, tap = quick look; Island moved to Ctrl+Alt+I by the user's choice, migrated), generateContent with no
  tools, short answers + More, Explain/Review/Summarise/Reply, Insert on click only, Copy, monospace code, TTS in the
  Loadout voice, follow-ups that re-capture only when the window changed (brightness-grid diff), blocklist with
  masking, ≤1024 px trimmed JPEGs and a thumbnail, Action-log rows, never on disk — `test_screen_assist.py` (32:
  change detection, crop/downscale, blocklist, masking, capture/refusal logging, follow-up reuse vs re-capture,
  more/retry, spoken question, prompt-injection fixture, no tools in the request, TTS audio, Watch
  analyse/skip/throttle/repeat/blocked/auto-stop, usage and cost, what's read aloud), `test_screen_assist_ui.py`
  (14: hotkey tap/hold, Insert only on click, refusal, voice tool from a worker thread, watch tool,
  look_at_screen blocklist, Screen tab, Watching indicator + one-click stop, tray badge, Circle masking, settings
  and hotkey migration, settings page); `docs/island/screen_assist.gif`; D-052; real use: MT-98…MT-106
- [~] S.2 Watch mode — `assist/service.Watcher`, `engine.WatchCheck`; 20 s, change-gated, JSON verdicts at low media
  resolution, one comment a minute, 30-minute auto-stop, island "Watching" (never hides, click Stop), tray dot +
  menu, Stats estimate — tests above; MT-104/MT-105
- [~] S.3 Discreet mode — `discreet.py`, `ui/discreet_card.py`, `ui/settings/discreet_page.py`,
  `tools/builtin/discreet.py`, the island's Discreet look (`island.py`, `geometry.py`, `reveal.py`, `machine.py`),
  `Player.muted`, `VoiceController.set_discreet`. Toggle from Settings, the island and tray menus, Ctrl+Alt+D and
  voice; the calendar schedule; a grey line or dot (50 %, top-centre or a corner, its own reveal zone, no glow,
  no motion); text-only answers on a card that fades after 12 s unless hovered (Speak it, Open; WCAG AA at the
  default); banners as a pulse, errors and confirmations open; Windows toasts muted; push-to-talk only; a
  separate profile, so off restores everything — `test_discreet.py` (13: switch remembered, calendar schedule
  incl. turned off during an event, line/dot look and restore, corner/reveal/hit area, pulse vs error banner,
  Watch dot, card contrast at 92 % and 85 %, card fade/hover/links, muted player vs Speak it, always-listening
  pause, settings + page, voice tool, and the acceptance case: a hotkey Screen Assist exchange in Discreet
  mode on the real app with no sound and only the card, then everything as before); also
  `test_island_window.py::test_right_click_menu`; `docs/island/discreet_mode.gif`, `discreet_card_100.png`,
  `discreet_card_150.png`; D-053; MT-107…MT-114

### Fixes of 2026-10-16
- [x] X.1 Screen Assist failed every time with "RuntimeError" — root cause: `GeminiAssistModel` used a temporary
  `genai.Client`, whose `__del__` closed its HTTP client before the request was sent ("Cannot send a request, as
  the client has been closed"); source and frozen alike. Fixed with `with self._client() as client` in `answer`
  and `speak` (`assist/client.py`). Reproduced from source with the real key and in a PyInstaller build of the
  old code (its self-check fails with the same traceback); after the fix the request reaches Google (503 "high
  demand" at the time) — `test_screen_assist.py::test_the_client_stays_open_until_the_request_is_sent` (real SDK
  + httpx against `ai/loopback.py`, worker thread), `test_a_client_closed_when_collected_still_works`,
  `test_screen_assists_request_has_no_tools_and_the_right_config`; D-054; MT-115
- [x] X.2 Failures logged in full and shown with their message — `log.exception` in the request, speech, Watch
  and capture threads and `Capturer.capture`; `describe_error` fallback "Unexpected error (Type): message"
  (redacted, ≤300 chars), httpx transport errors = "Couldn't reach Google", capture crashes and a screenshot
  timeout say so; a "Screen Assist failed" banner that opens the Screen tab — `test_screen_assist_ui.py` (8 new:
  traceback + thread name for each worker, real message on the card, capture crash, shot timeout, banner →
  Screen tab), `test_screen_assist.py` (error text, key redaction, network errors)
- [x] X.3 `--self-check` runs Screen Assist — `selfcheck.py::_screen_assist`: real capture → mask → downscale →
  JPEG on "assist-capture", then the real google-genai client to a 127.0.0.1 stand-in on "screen-assist", answer
  and speech checked; `build.py` stops if it fails — `test_packaging.py::test_self_check_from_source`; frozen
  run in the build of 2026-10-16
- [x] X.4 A microphone that delivers only silence — `audio/mic_check.py` (digital silence vs a quiet room, the
  three Windows privacy switches read from the registry, a notice naming the switch or listing what to check);
  Screen Assist holds, push-to-talk turns ("mic_silent") and dictation show it instead of acting on silence; the
  1 s level line uses plain numbers and warns with the switches — `test_mic_check.py`,
  `test_live_session.py::test_a_mic_that_delivers_nothing_is_reported_as_such`, `test_screen_assist_ui.py`
  (silent hold vs tap). The cause, measured on 2026-10-21 with `--mic-check` (D-060): source and exe both get
  about −95 dBFS from the AMD array with every privacy switch on, so it is the input itself (mute key, driver,
  or the wrong input), not Windows privacy; D-055, D-060; MT-116…MT-118

### Fixes of 2026-10-20
- [x] Y.1 Zero-size capture — root cause: the window in front was used as it came; DWM gave it an empty
  rectangle (0,0,0,0) and only `None` was checked, so mss got a 0×0 region (a Screen-tab request; the island
  never takes the foreground). `frame_bounds` falls back to GetWindowRect and never returns an empty
  rectangle; `Capturer.choose` skips Wisp's own windows, the desktop, taskbars, minimised, cloaked, empty and
  off-screen windows for the conversation's window or the next real one in z-order (blocked ones passed
  over), else the whole monitor under the pointer, with a note on the card; rectangles clamped to the
  virtual screen — `test_capture_targets.py` (19: each case, clamping, blocklist, the note on the card, the
  GetWindowRect fallback with fake DLLs, real rectangles never empty); D-056; MT-119, MT-120
- [x] Y.2 Gemini's 503 — the SDK's `HttpRetryOptions` (3 attempts, 429/503, backoff 3–5 s then 6–8 s with
  jitter, 40 s per attempt) on every generate_content (Screen Assist, Watch, reading aloud, dictation); an
  httpx response hook logs each busy answer and puts "Google is busy, retrying… (2 of 3)" on the card and
  the dictation HUD; an optional fallback text model (Settings → General, off by default) after the retries
  end in 503, named on the card and in Stats; plain messages for 503, other 5xx and timeouts; one shared
  TLS context (client creation 0.45 s → 1 ms) — `test_retry.py` (16: the real SDK against the loopback
  answering 503: retried and answered, given up and explained, fallback and its note, no fallback for 429/500
  or the same model, 500 not retried, TTS and dictation retried, the HUD note, fake-client checks, the
  setting and its page); D-057; MT-121, MT-122, MT-124
- [x] Y.3 A press that ended in nothing — root cause: `press()` opened the microphone on the Qt thread (the
  first use starts PortAudio: 1.6 s), so the release ran right after with 5 ms of audio, was taken for a tap,
  and the quick look then waited on an overloaded Gemini with no timeout and no log line until Wisp was
  quit. The mic now opens on a thread ("Listening…" at once; a late-opening mic is let go), PortAudio is
  warmed up at start (no stream), tap vs hold is timed from the keys, and every press ends in an answer, an
  error or "I didn't hear a question", each logged with the request and its outcome —
  `test_screen_assist_ui.py` (8 new: the press doesn't wait for a slow mic, released before it opened, no
  speech, no microphone vs a tap, logged outcomes, a press while busy, the busy note on the card,
  unsubscribing doesn't wait for an opening stream, the warm-up opens no stream); D-058; MT-123
- [x] Y.4 "Mic levels" log line in plain numbers — already in the build of 2026-10-16 (D-055,
  `test_mic_check.py`); the 2026-10-19 log has no such line because the mic was open for 79 ms only
- [x] Y.5 `--self-check` `screen_assist` now chooses a window with the new rules and has the loopback answer
  503 once, so the SDK's retry and the busy note run in the frozen build too

### Licence and release (2026-10-21)
- [x] R.1 Licence: MIT, chosen by the owner — `LICENSE` (SPDX text), `pyproject.toml` `license`/`license-files`
  (PEP 639, setuptools ≥ 77), bundled next to `THIRD_PARTY_NOTICES.txt` (`packaging/wisp.spec`); README and
  the user guide say so — `test_packaging.py::test_version_matches_pyproject`; D-060
- [x] R.2 Releases from CI — `.github/workflows/ci.yml` job `release`: on a tag `v<version>` it checks the
  version, takes the installer the build job tested and publishes it with `gh release create --verify-tag`
  and `docs/releases/<tag>.md`; job `release-notes`: a push to main that changes those notes updates the
  published release's text (`gh release edit --notes-file`) — `test_packaging.py::test_version_matches_pyproject`
  (notes exist for the version); v0.1.0 published by CI on 2026-10-21 with the installer; D-060
- [x] R.3 `Wisp.exe --mic-check [report.json]` — `audio/mic_report.py`, `__main__.py`; 1.5 s, levels only, a
  verdict and an exit code — `test_mic_check.py` (4 new: working, silent vs blocked, not opening, exit code);
  run on this PC from source and from the exe for MT-116; D-060

### Testing, packaging, definition of done
- [x] T.1 Unit tests: dispatcher, safety tiers, scheduler parsing + persistence, memory, clipboard store,
  settings (Windows-only tests marked) — `test_dispatcher.py`, `test_tools_core.py`, `test_hardening.py`,
  `test_schedule_spec.py`, `test_scheduler.py`, `test_memory.py`, `test_clipboard_history.py`, `test_settings.py`;
  `windows` marker skips Windows-only tests elsewhere (conftest)
- [x] T.2 Integration tests with fake Live session replaying scripted tool calls — `tests/fakes.py`
  (FakeLiveServer), `test_live_session.py`, `test_schedule_tools.py::test_model_schedules_routine_then_it_replays_without_model`
- [x] T.3 MANUAL_TESTS.md runnable in ~20 minutes — "Core run" (16 steps, ~27 min) covering every `[~]`
  item; the full catalogue (77 cases) is the extended set
- [x] T.4 GitHub Actions on windows-latest: lint + tests + PyInstaller exe — `.github/workflows/ci.yml`
  (ruff, pytest, Inno Setup, `packaging/build.py` incl. frozen self-check, artefacts). On GitHub since
  2026-10-18 (github.com/Mathias-D06/Wisp). The first runs failed twice over (D-059): the build printed
  "→" to a cp1252 pipe, and the test process crashed in PySide6's shutdown after "all passed" (two
  WispApps' windows left by tests). Both fixed; run 39449959046 (1fac972, 2026-10-20) passed every step,
  677 passed / 4 skipped, all required self-checks ok on the runner, app and installer artefacts uploaded.
  Failures show as annotations. The actions are on their Node 24 majors (checkout, setup-python and
  upload-artifact @v7). Hosted runners have no audio devices (those tests skip; the self-check marks
  audio optional)
- [x] D.1 Installer installs, launches at login, uninstalls cleanly — `packaging/installer.iss`; silent
  install/uninstall on this PC 2026-10-13 (files, shortcut, uninstall entry, Run value; the Run command
  started Wisp; uninstall removed everything incl. an app-written Run value; user data kept);
  `test_packaging.py::test_installer_agrees_with_the_app`; real sign-in MT-47
- [x] D.2 Stub/placeholder grep returns nothing — `\b(TODO|FIXME|XXX|HACK|TBD)\b|NotImplementedError|stub|
  not implemented|coming soon` over *.py/iss/spec/yml/md/toml: no hits in code (2026-10-13); bare `pass`
  only in empty exception classes
- [x] D.3 README complete — `README.md` (the project: what it does, stack, architecture, how it was built)
  and `docs/USER_GUIDE.md` (install, key + billing/terms, usage, settings, Scheduled tasks, Safety model,
  privacy and data, troubleshooting, building, notices)
- [x] D.4 Final report — `FINAL_REPORT.md`

## Log

- 2026-10-12: Phase 0 started. Installed Python 3.12.10 (py install manager), Git, Inno Setup (winget),
  with user approval. Project at `C:\Users\mathi\Documents\Wisp`.
- 2026-10-13: Phase 7 finished (tests, D-030/D-031, sources, MT-29…MT-34). Added
  `winrt-Windows.Foundation.Collections` to pyproject; clipboard search now treats % and _ literally.
- 2026-10-13: Phase 8 finished (memory, loadout page, stats tests, D-032/D-033, MT-35…MT-38).
- 2026-10-13: Phase 9 finished (Safety/Hotkeys and audio/Action log pages, terminal + raw input,
  anti-cheat guard, crash logging, D-034…D-036, MT-39…MT-45).
- 2026-10-13: Phase 10 finished. PyInstaller one-folder build (164 MB) passes `--self-check` frozen;
  installer 54 MB. Silent per-user install/uninstall tested on this PC into %TEMP% (state before/after
  recorded; nothing left behind, user data kept, dummy data folder removed). CI steps emulated in a
  fresh venv: all green. Commands: `.venv\Scripts\python packaging\build.py`.
- 2026-10-13: Phase 11 final audit. Bugs found and fixed: `StatsTab.metric` shadowed
  `QWidget::metric()` (re-applying the stylesheet on every settings save raised TypeError);
  ClipboardMonitor kept a lambda connection to the global clipboard signal (never released) and let
  store errors escape a Qt slot; `test_missed_beyond_grace_is_reported` raced under load. Regression
  tests added for each. Item-view check boxes now styled like QCheckBox.
- 2026-10-13: First real test with the user's key. Voice worked; an 81 ms tap closed the session
  (1007 "Precondition check failed"). Probe confirmed empty activities are rejected. Fixed (D-038):
  push-to-talk turns open after 0.2 s of audio, taps send nothing (hint), image turns always sent,
  sender adds 32 ms of silence before an empty activity_end; close reason shown. Verified against
  the real API with the app's LiveSessionManager; tests in test_live_session.py (6 new) and test_voice.py.
- 2026-10-13: Speech fix (part 1). Root cause of "¿Qué?"/"我才没睡。": near-empty or silent turns (orb
  double-click 221 ms, quick Talk click 81 ms; possibly a quiet 4-channel array downmix) — Gemini's
  transcriber invents foreign phrases for silence (reproduced with the user's key). Fixed: native-format
  capture with active-channel downmix + FIR resampling, speech gate, pre-roll, click/hold Talk, orb
  double-click, language lock (en-GB), debug WAV + mic test, clear errors + Retry, one row per turn.
  Real-API check: 10/10 English, silence/hiss not sent, invalid key → "Google rejected this API key".
- 2026-10-13: UI polish (part 2). Design tokens (`ui/theme.py`, `ui/motion.py`), near-black palette meeting
  WCAG AA in both modes, Segoe UI Variable type rules from Microsoft's typography page, Lucide icons via a vector
  QIconEngine, Mica/rounded corners/themed title bar with a solid fallback, console rebuilt (icon toggles, message
  rows, composer, Retry), Island/Settings/popups restyled, state-change motion with Reduce motion and the Windows
  setting, orb as the only living element. Found and fixed on the way: the circle hint pill's brush filled the
  user's loop; theme hooks connected as lambdas outlived their widgets (now bound/child-object connections); the
  transcript's scroll timer had no context object; an Island test depended on where the real pointer rested.
  Idle CPU 6.17 % → 3.28 % (0.29 % with Reduce motion). Screenshots in docs/screenshots. D-042…D-044, MT-57…MT-63.
- 2026-10-13: Dynamic Island (part 3). One black island replaces the console window, the old pill, the
  dictation HUD, the answer bubble and tray toasts: idle/sliver/activity/split/banner/expanded, decided by
  an IslandStateMachine (voice > banner > timer > music > idle); springs (closed-form, retargetable) drive
  one shape on a fixed canvas; input region = the shape (setMask), shadow in a click-through window,
  WS_EX_NOACTIVATE (focus only on a click into a text box, given back on collapse), hidden behind
  full-screen apps (SHQueryUserNotificationState + covering foreground window), Esc via the keyboard hook,
  hotkey Ctrl+Alt+Space, album art (new dependency winrt-Windows.Storage.Streams 3.2.1) and a real output
  meter. 62 fps morphs; idle CPU 0.44 % of one core while visible and idle with the orb's glow (0.42 % with Reduce motion) against 5.99 % for the old island measured the same way (`spikes/island_idle_cpu.py`: in-process, island visible, 30 s warm-up, 60 s); 0.21 % while hidden behind a full-screen app (`spikes/idle_cpu.py`). Recordings in docs/island
  (rendered from the widget). D-045…D-047, MT-64…MT-77.
- 2026-10-14: Part 4.3 Calendar. Bugs found while testing: `EventRow.event` hid `QWidget.event()` (TypeError
  on every event; renamed), cleared rows painted until deleted (now hidden first), the agenda's scroll area
  painted the palette's grey (transparent like the rest), event creation allowed calendars shared with write
  access that `calendar.events.owned` can't reach (owned only), incremental syncs left out `showDeleted`
  (same parameters now). GIF recordings use one palette across frames (small colours kept).
- 2026-10-14: Part 4.4 Files & Share. This PC's network is Public, so the phone link refuses here (as required);
  the server was tested on 127.0.0.1 and with a real phone it is MT-94…MT-96. The share sheet opened from a probe.
  Found while testing: refused uploads were answered before the body was read (browsers report a dropped
  connection), so uploads now ask first and send after Accept; "&" in the tab name showed as a mnemonic.
- 2026-10-15: Screen Assist (brief of 2026-10-14, part 1). Gemini answered 503 "high demand" to both real-API
  probes, so the live check is MT-98. Found while testing: a dHash missed a big dialog on a flat background (switched
  to a brightness grid); fenced code from Qt's Markdown import used the generic "monospace" family (now Cascadia
  Mono/Consolas); the voice model's instruction outgrew its length budget (shortened).
- 2026-10-15: Discreet mode (brief of 2026-10-14, part 2). Found while building: reminders share the warning tone
  with errors, so errors are now told apart by their icon; the "Phone link" and "Watching" countdowns never ticked
  (only "countdown" scheduled 250 ms frames) — fixed for both; tests must never open the real microphone (the
  acceptance test uses a fake one).
- 2026-10-16: Fixes (D-054, D-055). Screen Assist's "RuntimeError" was google-genai closing a temporary client
  before it sent the request; reproduced from source and in a PyInstaller build, fixed, and now covered by
  `--self-check` and by tests that drive the real SDK against a loopback server. The silent microphone was not
  settled without opening the mic (no recording without asking): all privacy switches are on and the device is
  unmuted, but Windows never recorded the exe as a mic user; Wisp now detects digital silence, says which setting
  to check and logs the switches (MT-116…MT-118).
- 2026-10-20: Fixes (D-056…D-058) from the installed build's log. The zero-size capture was an empty DWM
  rectangle for the window in front; the 503s are now retried by the SDK with a note on the card and an
  optional fallback model; the "nothing happened" press was the microphone opening on the UI thread (1.6 s)
  followed by a quick look stuck on an overloaded Gemini. Found while fixing: every genai.Client loaded the CA
  bundle twice (0.45 s a request), now shared. The "Windows fatal exception 0x8001010d" printed during
  `test_win_integration.py` is COM's RPC_E_CANTCALLOUT_ININPUTSYNCCALL reported by faulthandler; it is
  already there at the previous commit and the tests pass.
- 2026-10-21: CI's actions moved to their Node 24 majors (@v7); FINAL_REPORT.md brought up to date (it
  still described the 2026-10-13 state); T.4 done.
- 2026-10-21: MIT licence (owner's choice); CI publishes a release from a version tag; `--mic-check` added and
  run with the owner's permission: both builds get about −95 dBFS from the AMD array with every privacy switch
  on, so MT-116's answer is the input, not Windows privacy.
