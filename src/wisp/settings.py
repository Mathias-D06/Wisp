"""User settings stored as JSON in the data folder.

Settings are plain dataclasses so they are easy to test and to show in the UI. Loading is
forgiving: unknown keys are dropped and values of the wrong type fall back to defaults, so a
hand-edited or older settings file never stops the app from starting.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import logging
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

TOOL_GROUPS = [
    "apps",
    "windows",
    "web",
    "screen",
    "ui",
    "files",
    "todos",
    "schedule",
    "memory",
    "system",
    "media",
    "power",
    "clipboard",
    "terminal",
    "input",
]
"""Skill groups the user can switch on or off in the Loadout (terminal/input also need Safety)."""

VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe",
    "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib",
    "Rasalgethi", "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima",
    "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
"""Gemini prebuilt voices (https://ai.google.dev/gemini-api/docs/speech-generation)."""

NEVER_AUTO_APPROVE = frozenset({
    "run_command", "mouse_click", "press_keys", "type_text", "delete_to_recycle_bin", "power",
    "click_element", "type_into_field", "open_path", "schedule_task", "delete_scheduled_task",
})
"""Tools whose confirmation can never be switched off (irreversible, purchase-capable or blind
actions; DECISIONS.md D-034). Enforced by validate() and again by the safety policy."""

LANGUAGE_CODES = {
    "English (UK)": "en-GB", "English (US)": "en-US", "English": "en", "Spanish": "es",
    "French": "fr", "German": "de", "Italian": "it", "Portuguese": "pt", "Dutch": "nl",
    "Polish": "pl", "Turkish": "tr", "Hindi": "hi", "Japanese": "ja", "Korean": "ko",
    "Chinese": "zh", "Arabic": "ar", "Russian": "ru", "Swedish": "sv",
}
"""Languages offered in Settings, with the BCP-47 code sent as a transcription hint (D-040)."""


def language_code(language: str) -> str | None:
    """BCP-47 code for a language name from the list (None for free text)."""
    return LANGUAGE_CODES.get(language.strip())


PERSONALITY_PRESETS = ["friendly", "professional", "playful", "minimal", "custom"]
THEMES = ["system", "dark", "light"]
CUSTOM_PERSONALITY_MAX = 600


@dataclass
class GeneralSettings:
    start_with_windows: bool = False
    show_island: bool = True
    clipboard_history_size: int = 50
    typing_wpm: int = 40
    amazon_domain: str = "www.amazon.com"


@dataclass
class AISettings:
    live_model: str = "gemini-3.8-live"
    text_model: str = "gemini-3.8-flash"
    language: str = "English (UK)"
    idle_timeout_min: int = 5


@dataclass
class AudioSettings:
    input_device: str = ""
    output_device: str = ""
    always_listening: bool = False
    mic_muted: bool = False
    save_debug_audio: bool = False


@dataclass
class HotkeySettings:
    push_to_talk: str = "alt+win"
    dictation: str = "ctrl+win"
    circle: str = "ctrl+shift"
    hold_ms: int = 250


@dataclass
class LoadoutSettings:
    voice: str = "Zephyr"
    personality: str = "friendly"
    custom_personality: str = ""
    theme: str = "dark"
    accent: str = "#7c5cff"
    skills: list[str] = field(
        default_factory=lambda: [g for g in TOOL_GROUPS if g not in ("terminal", "input")]
    )


@dataclass
class SafetySettings:
    allow_terminal: bool = False
    allow_raw_input: bool = False
    auto_approve: list[str] = field(default_factory=list)
    taint_minutes: int = 5


@dataclass
class SchedulerSettings:
    one_off_grace_hours: int = 12
    recurring_grace_minutes: int = 60


@dataclass
class Settings:
    general: GeneralSettings = field(default_factory=GeneralSettings)
    ai: AISettings = field(default_factory=AISettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    hotkeys: HotkeySettings = field(default_factory=HotkeySettings)
    loadout: LoadoutSettings = field(default_factory=LoadoutSettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    scheduler: SchedulerSettings = field(default_factory=SchedulerSettings)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        settings = _from_dict(cls, data)
        if settings.ai.language == "English":
            # The only English option before D-040 (not a choice of variant): use the new default.
            settings.ai.language = "English (UK)"
        return settings


def _coerce(default: Any, value: Any, path: str) -> Any:
    """Return ``value`` if it matches the type of ``default``; otherwise the default."""
    if isinstance(default, bool):
        ok = isinstance(value, bool)
    elif isinstance(default, int):
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif isinstance(default, str):
        ok = isinstance(value, str)
    elif isinstance(default, list):
        ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
    else:
        ok = False
    if ok:
        return list(value) if isinstance(value, list) else value
    log.warning("Ignoring invalid setting %s=%r", path, value)
    return default


def _from_dict(cls: type, data: Any, prefix: str = "") -> Any:
    instance = cls()
    if not isinstance(data, dict):
        return instance
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        current = getattr(instance, f.name)
        raw = data[f.name]
        path = f"{prefix}{f.name}"
        if dataclasses.is_dataclass(current):
            setattr(instance, f.name, _from_dict(type(current), raw, path + "."))
        else:
            setattr(instance, f.name, _coerce(current, raw, path))
    return instance


def validate(settings: Settings) -> list[str]:
    """Return human-readable problems; empty when the settings are usable."""
    problems: list[str] = []
    if not 1 <= settings.ai.idle_timeout_min <= 240:
        problems.append("Idle timeout must be between 1 and 240 minutes.")
    if not 5 <= settings.general.clipboard_history_size <= 500:
        problems.append("Clipboard history size must be between 5 and 500.")
    if not 10 <= settings.general.typing_wpm <= 200:
        problems.append("Typing speed must be between 10 and 200 words per minute.")
    if not 100 <= settings.hotkeys.hold_ms <= 2000:
        problems.append("Hotkey hold time must be between 100 and 2000 ms.")
    if not 0 <= settings.scheduler.one_off_grace_hours <= 168:
        problems.append("Missed one-off task grace must be 0-168 hours.")
    if not 0 <= settings.scheduler.recurring_grace_minutes <= 1440:
        problems.append("Missed repeating task grace must be 0-1440 minutes.")
    if settings.loadout.voice not in VOICES:
        problems.append(f"Unknown voice {settings.loadout.voice!r}.")
    if not re.fullmatch(r"(www\.)?amazon\.[a-z]{2,3}(\.[a-z]{2})?", settings.general.amazon_domain):
        problems.append("Amazon site must look like www.amazon.co.uk.")
    if not settings.ai.language.strip():
        problems.append("Language cannot be empty.")
    if not settings.ai.live_model.strip():
        problems.append("Live model name cannot be empty.")
    if not settings.ai.text_model.strip():
        problems.append("Text model name cannot be empty.")
    loadout = settings.loadout
    if loadout.personality not in PERSONALITY_PRESETS:
        problems.append(f"Unknown personality {loadout.personality!r}.")
    if len(loadout.custom_personality) > CUSTOM_PERSONALITY_MAX:
        problems.append(f"Custom personality must be at most {CUSTOM_PERSONALITY_MAX} characters.")
    if loadout.theme not in THEMES:
        problems.append(f"Unknown theme {loadout.theme!r}.")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", loadout.accent):
        problems.append("Accent colour must look like #7c5cff.")
    if not 1 <= settings.safety.taint_minutes <= 120:
        problems.append("Untrusted-content window must be 1-120 minutes.")
    blocked = sorted(set(settings.safety.auto_approve) & NEVER_AUTO_APPROVE)
    if blocked:
        problems.append(f"These actions always ask first: {', '.join(blocked)}.")
    unknown = [s for s in settings.loadout.skills if s not in TOOL_GROUPS]
    if unknown:
        problems.append(f"Unknown skill groups: {', '.join(unknown)}.")
    from wisp.hotkeys.chords import find_conflicts

    problems.extend(
        find_conflicts(
            {
                "Push-to-talk": settings.hotkeys.push_to_talk,
                "Dictation": settings.hotkeys.dictation,
                "Circle to Ask": settings.hotkeys.circle,
            }
        )
    )
    return problems


class SettingsStore:
    """Loads, saves and broadcasts settings. Thread-safe."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._listeners: list[Callable[[Settings], None]] = []
        self._settings = self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> Settings:
        if not self._path.exists():
            return Settings()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.error("Settings file unreadable (%s); using defaults", exc)
            return Settings()
        return Settings.from_dict(data)

    def get(self) -> Settings:
        """Return a copy; mutate it and pass it to :meth:`save`."""
        with self._lock:
            return copy.deepcopy(self._settings)

    def peek(self) -> Settings:
        """The current settings object without copying, for hot paths. Never mutate it;
        :meth:`save` replaces it wholesale."""
        return self._settings

    def save(self, settings: Settings) -> None:
        problems = validate(settings)
        if problems:
            raise ValueError(" ".join(problems))
        with self._lock:
            self._settings = copy.deepcopy(settings)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
            os.replace(tmp, self._path)
            listeners = list(self._listeners)
        snapshot = self.get()
        for listener in listeners:
            try:
                listener(snapshot)
            except Exception:
                log.exception("Settings listener failed")

    def update(self, mutate: Callable[[Settings], None]) -> Settings:
        settings = self.get()
        mutate(settings)
        self.save(settings)
        return settings

    def subscribe(self, listener: Callable[[Settings], None]) -> None:
        with self._lock:
            self._listeners.append(listener)
