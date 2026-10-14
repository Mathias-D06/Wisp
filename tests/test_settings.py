from __future__ import annotations

import json

import pytest

from wisp.settings import Settings, SettingsStore, validate


def test_defaults_are_valid():
    assert validate(Settings()) == []


def test_round_trip(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.update(lambda s: setattr(s.ai, "idle_timeout_min", 12))
    reloaded = SettingsStore(tmp_path / "s.json").get()
    assert reloaded.ai.idle_timeout_min == 12


def test_unknown_keys_and_wrong_types_fall_back(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {
                "ai": {"idle_timeout_min": "ten", "live_model": "custom-live", "bogus": 1},
                "audio": {"always_listening": 1},
                "unknown_section": {"x": 1},
                "loadout": {"skills": ["apps", 3]},
            }
        ),
        encoding="utf-8",
    )
    settings = SettingsStore(path).get()
    assert settings.ai.idle_timeout_min == 5
    assert settings.ai.live_model == "custom-live"
    assert settings.audio.always_listening is False  # int is not accepted as bool
    assert "apps" in settings.loadout.skills and "terminal" not in settings.loadout.skills


def test_corrupt_file_uses_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json", encoding="utf-8")
    assert SettingsStore(path).get() == Settings()


def test_validation_rejects_bad_values(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    settings = store.get()
    settings.ai.idle_timeout_min = 0
    settings.loadout.voice = "Nobody"
    with pytest.raises(ValueError, match="Idle timeout"):
        store.save(settings)
    assert not (tmp_path / "s.json").exists()


def test_listeners_receive_copy(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    seen = []
    store.subscribe(seen.append)
    store.update(lambda s: setattr(s.audio, "mic_muted", True))
    assert seen and seen[0].audio.mic_muted is True
    seen[0].audio.mic_muted = False
    assert store.get().audio.mic_muted is True


def test_terminal_and_input_skills_off_by_default():
    settings = Settings()
    assert settings.safety.allow_terminal is False
    assert settings.safety.allow_raw_input is False
    assert "terminal" not in settings.loadout.skills
    assert "input" not in settings.loadout.skills


def test_island_hiding_defaults_and_range():
    settings = Settings()
    general = settings.general
    assert (general.island_hide_when_idle, general.island_hide_after_s,
            general.island_keep_for_music) == (True, 6, True)
    for seconds, ok in ((2, False), (3, True), (15, True), (16, False)):
        general.island_hide_after_s = seconds
        assert (not any("hides after" in p for p in validate(settings))) is ok


def test_new_skill_groups_start_on_once_but_stay_off_if_switched_off(tmp_path):
    old = {"loadout": {"skills": ["apps", "todos", "memory"]}}  # saved before "calendar"
    settings = Settings.from_dict(old)
    assert "calendar" in settings.loadout.skills and "terminal" not in settings.loadout.skills
    assert "calendar" in settings.loadout.known_skills
    settings.loadout.skills.remove("calendar")  # the user switches it off
    again = Settings.from_dict(json.loads(json.dumps(settings.to_dict())))
    assert "calendar" not in again.loadout.skills  # stays off


def test_calendar_settings_defaults_and_range():
    settings = Settings()
    assert (settings.calendar.heads_up_min, settings.calendar.allow_create) == (10, False)
    settings.calendar.heads_up_min = 61
    assert any("heads-up" in p for p in validate(settings))


def test_phone_link_size_limit_default_range_and_old_files():
    settings = Settings()
    assert settings.share.phone_max_upload_mb == 2048 and validate(settings) == []
    for bad in (0, 20481):
        settings.share.phone_max_upload_mb = bad
        assert any("phone link" in p for p in validate(settings))
    assert Settings.from_dict({"general": {}}).share.phone_max_upload_mb == 2048  # saved before
    assert Settings.from_dict({"share": {"phone_max_upload_mb": "big"}}).share \
        .phone_max_upload_mb == 2048
