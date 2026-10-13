"""Application bootstrap: builds the services, the tray and the windows, and wires them."""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from wisp import paths, startup
from wisp.ai import dictation as dictation_ai
from wisp.audio.capture import MicCapture
from wisp.audio.playback import Player
from wisp.circle import CircleController
from wisp.db import Database
from wisp.dictation import DictationController, DictationDeps
from wisp.hotkeys.manager import HotkeyManager
from wisp.keystore import KeyStore
from wisp.live.config import build_live_config, is_extended_thinking, system_instruction
from wisp.live.connector import GenaiConnector
from wisp.live.session import LiveSessionManager
from wisp.logging_setup import configure as configure_logging
from wisp.loop import LoopThread
from wisp.scheduling.scheduler import TaskScheduler
from wisp.scheduling.tasks import TaskStore
from wisp.services import Services
from wisp.settings import Settings, SettingsStore
from wisp.single_instance import SingleInstance
from wisp.stores.action_log import ActionLog
from wisp.stores.clipboard_history import ClipboardHistory
from wisp.stores.memory import MemoryStore
from wisp.stores.stats import Stats
from wisp.stores.todos import TodoStore
from wisp.system import clipboard
from wisp.system.app_index import AppIndex
from wisp.system.clipboard_monitor import ClipboardMonitor
from wisp.system.media import MediaWatcher
from wisp.tools.base import Origin
from wisp.tools.builtin import apps as apps_tools
from wisp.tools.builtin import core as core_tools
from wisp.tools.builtin import files as files_tools
from wisp.tools.builtin import memory as memory_tools
from wisp.tools.builtin import schedule as schedule_tools
from wisp.tools.builtin import screen as screen_tools
from wisp.tools.builtin import system as system_tools
from wisp.tools.builtin import todos as todo_tools
from wisp.tools.builtin import ui as ui_tools
from wisp.tools.builtin import web as web_tools
from wisp.tools.builtin import windows as windows_tools
from wisp.tools.confirm import ConfirmationManager
from wisp.tools.dispatcher import Dispatcher
from wisp.tools.registry import ToolRegistry
from wisp.tools.safety import SafetyPolicy, TaintTracker
from wisp.ui import theme
from wisp.ui.bridge import UiInvoker
from wisp.ui.bubble import AnswerBubble
from wisp.ui.confirm_card import ConfirmCard
from wisp.ui.console import ConsoleWindow
from wisp.ui.hud import Hud
from wisp.ui.island.apps_tab import AppsTab
from wisp.ui.island.clipboard_tab import ClipboardTab
from wisp.ui.island.common import Background
from wisp.ui.island.controls_tab import ControlsTab
from wisp.ui.island.island import Island
from wisp.ui.island.music import MediaSignals
from wisp.ui.island.power_tab import PowerTab
from wisp.ui.island.stats_tab import StatsTab
from wisp.ui.island.today_tab import TodayTab
from wisp.ui.island.wallpaper_tab import WallpaperTab
from wisp.ui.settings.dialog import SettingsDialog
from wisp.ui.settings.general_page import GeneralPage
from wisp.ui.settings.loadout_page import LoadoutPage
from wisp.ui.settings.memories_page import MemoriesPage
from wisp.ui.settings.routines_page import RoutinesPage
from wisp.ui.tray import Tray
from wisp.voice import VoiceController, VoiceSignals, make_callbacks
from wisp.winapi import input as winput
from wisp.winapi import windows as win

log = logging.getLogger(__name__)

RECONNECT_FIELDS = ("voice", "personality", "custom_personality", "skills")


class WispApp(QObject):
    def __init__(self, qt_app: QApplication, background: bool):
        super().__init__()
        self.qt_app = qt_app
        self.background = background
        self.keystore = KeyStore(paths.secrets_file())
        self.redactor = configure_logging(paths.log_dir(), self.keystore.get)
        log.info("Wisp starting (frozen=%s)", paths.is_frozen())
        self.settings_store = SettingsStore(paths.settings_file())
        self.db = Database(paths.database_file())
        settings = self.settings_store.get()
        self._last_settings = settings
        self._apply_theme(settings)
        self.ui = UiInvoker()
        self.tray = Tray(settings.loadout.accent)
        self.loop = LoopThread()
        self.loop.start()

        peek = self.settings_store.peek
        self.confirmations = ConfirmationManager()
        self.taint = TaintTracker(lambda: peek().safety.taint_minutes)
        self.registry = ToolRegistry()
        self.services = Services(
            settings=self.settings_store, keystore=self.keystore, db=self.db, ui=self.ui,
            notify=self.notify, confirmations=self.confirmations, taint=self.taint,
            registry=self.registry,
            action_log=ActionLog(self.db, self.redactor.redact),
            stats=Stats(self.db, lambda: peek().general.typing_wpm),
            app_index=AppIndex(self.db),
            todos=TodoStore(self.db),
            memory=MemoryStore(self.db),
            tasks=TaskStore(self.db),
            clipboard=ClipboardHistory(self.db, lambda: peek().general.clipboard_history_size),
        )
        self.services.scheduler = TaskScheduler(
            self.services.tasks, f"sqlite:///{paths.jobs_database_file()}", peek,
            self._execute_task, self.notify,
        )
        self._register_tools()
        self.dispatcher = Dispatcher(
            self.registry, SafetyPolicy(peek, self.taint), self.confirmations,
            self.services.action_log, self.services.stats, self.services,
        )
        self.dispatcher.bind_loop(self.loop.loop)
        self.services.dispatcher = self.dispatcher

        self.mic = MicCapture(lambda: peek().audio.input_device)
        if settings.audio.mic_muted:
            self.mic.set_muted(True)
        self.player = Player(lambda: peek().audio.output_device)
        self.voice_signals = VoiceSignals()
        self.live = LiveSessionManager(
            self.loop.loop,
            GenaiConnector(self.keystore.get, lambda: peek().ai.live_model),
            self._live_config,
            self.dispatcher,
            make_callbacks(self.voice_signals, self.player, self.confirmations.on_user_utterance),
            has_key=self.keystore.has_key,
            idle_timeout_s=lambda: peek().ai.idle_timeout_min * 60,
            always_listening=lambda: peek().audio.always_listening,
            is_playing=self.player.is_playing,
            extended_thinking=lambda: is_extended_thinking(peek().ai.live_model),
        )
        self.dispatcher.set_model_notifier(self.live.send_text)
        self.voice = VoiceController(
            self.live, self.mic, self.player, self.voice_signals, self.settings_store,
            self.confirmations, self.notify,
        )
        self.services.live, self.services.voice = self.live, self.voice
        self.services.mic, self.services.player = self.mic, self.player

        self.hotkeys = HotkeyManager()
        self.hotkeys.apply(settings)
        self.hotkeys.signals.event.connect(self._on_hotkey)

        self.clipboard_owner = QWidget()  # native window on the Qt thread that owns our writes
        self.clipboard_owner_hwnd = int(self.clipboard_owner.winId())
        self.hud = Hud(settings.loadout.accent)
        self.dictation = DictationController(self._dictation_deps(), self.mic, self.hud,
                                             self.services.stats, self.notify)
        palette = theme.palette(settings.loadout.theme, settings.loadout.accent)
        self.bubble = AnswerBubble(palette.surface, palette.border)
        self.circle = CircleController(self.voice, self.live, self.mic, self.hud, self.bubble,
                                       self.keystore.has_key, lambda: peek().loadout.accent)

        self.console = ConsoleWindow(self.voice, settings.loadout.accent)
        self.confirm_card = ConfirmCard(self.confirmations)
        self.confirm_card.apply_palette(palette.surface, palette.border)
        self.voice.visual.connect(lambda state, _level, text: self.tray.set_state(state, text))
        self._build_island(settings, palette)
        self._settings_dialog: SettingsDialog | None = None
        self.settings_store.subscribe(lambda s: self.ui.call(lambda: self._on_settings_changed(s)))
        self.keystore.subscribe(lambda has_key: self.ui.call(lambda: self._on_key_changed(has_key)))

    # ----- Island ----------------------------------------------------------------------------
    def _build_island(self, settings: Settings, palette) -> None:
        self.background = Background(self.loop.loop)
        self.media_signals = MediaSignals()
        self.media = MediaWatcher(self.loop.loop, self.media_signals.changed.emit)
        self.services.media = self.media
        self.clipboard_monitor = ClipboardMonitor(self.services.clipboard,
                                                  self.clipboard_owner_hwnd)
        services = self.services
        tabs = [
            ("Controls", ControlsTab(self.background, palette)),
            ("Today", TodayTab(services.todos, services.scheduler)),
            ("Stats", StatsTab(services.stats, self.settings_store, settings.loadout.accent)),
            ("Clipboard", ClipboardTab(services.clipboard, self.clipboard_monitor)),
            ("Apps", AppsTab(services.app_index, self.background, palette)),
            ("Wallpaper", WallpaperTab(self.background)),
            ("Power", PowerTab(self.background, palette, services.action_log)),
        ]
        self.island = Island(self.voice, palette, settings.loadout.accent, self.keystore.has_key,
                             lambda action: self.media.command(action), tabs)
        self.island.settings_requested.connect(lambda page: self.open_settings(page or None))
        self.media_signals.changed.connect(self.island.show_media)

    # ----- tools -----------------------------------------------------------------------------
    def _register_tools(self) -> None:
        for module in (core_tools, apps_tools, windows_tools, web_tools, screen_tools, ui_tools,
                       files_tools, todo_tools, memory_tools, system_tools):
            self.registry.register_all(module.tools())
        self.registry.register_all(schedule_tools.tools(self.registry))

    # ----- scheduled tasks and reminders -------------------------------------------------------
    def _execute_task(self, task) -> tuple[bool, str]:
        """Replay a task's stored tool calls (runs on a scheduler thread)."""
        lines: list[str] = []
        all_ok = True
        for step in task.steps:
            if "tool" in step:
                tool = self.registry.get(step["tool"])
                label = tool.describe(step["args"]) if tool else step["tool"]
                try:
                    result = self.dispatcher.dispatch_threadsafe(
                        step["tool"], step["args"], Origin.SCHEDULE, timeout=720)
                except Exception as exc:
                    result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                ok = bool(result.get("ok"))
                lines.append(f"{'✓' if ok else '✗'} {label}"
                             + ("" if ok else f" — {result.get('error', 'failed')}"))
            else:
                ok = self.keystore.has_key()
                if ok:
                    self.live.send_text(f"[Wisp notice] Scheduled task '{task.title}': "
                                        f"{step['prompt']}")
                lines.append(f"{'✓' if ok else '✗'} asked Wisp: {step['prompt'][:80]}"
                             + ("" if ok else " — needs an API key"))
            all_ok = all_ok and ok
        self.services.stats.record("routine")
        return all_ok, "\n".join(lines)

    def _check_reminders(self) -> None:
        for todo in self.services.todos.due_reminders():
            self.services.todos.mark_reminded(todo.id)
            when = todo.due_at.strftime("%H:%M") if todo.due_at else ""
            self.notify("Reminder", f"{todo.text} (due {when})")

    def _dictation_deps(self) -> DictationDeps:
        peek = self.settings_store.peek
        owner = self.clipboard_owner_hwnd
        modifier_keys = (winput.VK_LWIN, winput.VK_RWIN, winput.VK_LCONTROL, winput.VK_RCONTROL,
                         winput.VK_LSHIFT, winput.VK_RSHIFT, winput.VK_LMENU, winput.VK_RMENU)
        return DictationDeps(
            transcribe=lambda pcm: dictation_ai.transcribe(
                self.keystore.get() or "", peek().ai.text_model, pcm, peek().ai.language),
            has_key=self.keystore.has_key,
            snapshot=lambda: clipboard.snapshot(owner),
            set_text=lambda text: clipboard.set_text(text, owner),
            restore=lambda snap: clipboard.restore(snap, owner),
            clipboard_sequence=clipboard.sequence,
            paste=winput.paste_shortcut,
            modifiers_down=lambda: any(winput.is_down(vk) for vk in modifier_keys),
            foreground=win.foreground_window,
            activate=win.activate,
            target_is_elevated=lambda w: win.is_process_elevated(w.pid)
            and not win.self_elevated(),
        )

    def _live_config(self, handle: str | None):
        settings = self.settings_store.get()
        facts = (self.services.memory.session_facts()
                 if "memory" in settings.loadout.skills else [])
        instruction = system_instruction(settings, facts, datetime.now().astimezone())
        return build_live_config(settings, self.registry.declarations(settings), instruction,
                                 handle)

    # ----- lifecycle -------------------------------------------------------------------------
    def start(self) -> None:
        self._build_tray_menu()
        self.tray.show()
        self.services.app_index.refresh_in_background()
        try:
            self.services.scheduler.start()
        except Exception as exc:
            log.exception("Scheduler failed to start")
            self.notify("Scheduled tasks unavailable", f"The scheduler could not start: {exc}")
        self._reminder_timer = QTimer(self)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start(20_000)
        QTimer.singleShot(3000, self._check_reminders)
        self.media.start()
        self.island.update_key_prompt()
        if self.settings_store.peek().general.show_island:
            self.island.show()
        error = self.hotkeys.start()
        if error:
            self.notify("Hotkeys unavailable", f"Wisp could not install its keyboard hook: {error}")
        if not self.keystore.has_key():
            self.notify("Wisp is running",
                        "Add your Gemini API key in Settings to use voice and AI features.")
            if not self.background:
                self.open_settings("General")
        elif not self.background:
            self.console.open()

    def quit(self) -> None:
        log.info("Wisp quitting")
        self.services.scheduler.shutdown()
        self.media.stop()
        self.background.shutdown()
        self.island.hide()
        self.hotkeys.stop()
        self.live.disconnect()
        self.mic.close()
        self.player.close()
        self.dispatcher.shutdown()
        self.loop.stop()
        self.tray.hide()
        self.db.close()
        self.qt_app.quit()

    def notify(self, title: str, message: str) -> None:
        self.ui.call(lambda: self.tray.notify(title, message))

    # ----- UI --------------------------------------------------------------------------------
    def _build_tray_menu(self) -> None:
        settings = self.settings_store.get()
        self.talk_action = self.tray.add_action(
            f"Talk ({self.hotkeys.display('push_to_talk')})", self.voice.toggle_talk)
        self.tray.add_action("Open console", self.console.open)
        self.mute_action = self.tray.add_action("Mute microphone", self.voice.set_muted, True)
        self.mute_action.setChecked(settings.audio.mic_muted)
        self.listen_action = self.tray.add_action("Always listening",
                                                  self.voice.set_always_listening, True)
        self.listen_action.setChecked(settings.audio.always_listening)
        self.tray.add_separator()
        self.tray.add_action("Settings…", lambda: self.open_settings())
        self.tray.add_separator()
        self.tray.add_action("Quit Wisp", self.quit)
        self.tray.on_click(self.console.open)

    def settings_pages(self) -> list:
        return [
            GeneralPage(self.settings_store, self.keystore),
            LoadoutPage(self.registry),
            MemoriesPage(self.services.memory),
            RoutinesPage(self.services.tasks, self.services.scheduler),
        ]

    def open_settings(self, page: str | None = None) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.settings_store, self.settings_pages())
        self._settings_dialog.open_page(page)

    def _on_hotkey(self, name: str, kind: str) -> None:
        log.info("Hotkey %s %s", name, kind)
        self.voice.on_hotkey(name, kind)
        self.dictation.on_hotkey(name, kind)
        self.circle.on_hotkey(name, kind)

    def _apply_theme(self, settings: Settings) -> None:
        palette = theme.palette(settings.loadout.theme, settings.loadout.accent)
        self.qt_app.setStyleSheet(theme.stylesheet(palette))

    def _on_key_changed(self, has_key: bool) -> None:
        self.island.update_key_prompt()
        if has_key:
            self.live.request_reconnect()
        else:
            self.live.disconnect()

    def _on_settings_changed(self, settings: Settings) -> None:
        previous, self._last_settings = self._last_settings, settings
        self._apply_theme(settings)
        self.tray.set_accent(settings.loadout.accent)
        self.console.set_accent(settings.loadout.accent)
        palette = theme.palette(settings.loadout.theme, settings.loadout.accent)
        self.island.set_palette(palette)
        self.island.set_accent(settings.loadout.accent)
        self.confirm_card.apply_palette(palette.surface, palette.border)
        self.bubble.apply_palette(palette.surface, palette.border)
        self.hud.accent = settings.loadout.accent
        self.island.setVisible(settings.general.show_island)
        self.hotkeys.apply(settings)
        self.talk_action.setText(f"Talk ({self.hotkeys.display('push_to_talk')})")
        self.mute_action.blockSignals(True)
        self.mute_action.setChecked(settings.audio.mic_muted)
        self.mute_action.blockSignals(False)
        self.listen_action.blockSignals(True)
        self.listen_action.setChecked(settings.audio.always_listening)
        self.listen_action.blockSignals(False)
        if (previous.audio.input_device != settings.audio.input_device
                or previous.audio.output_device != settings.audio.output_device):
            self.voice.apply_settings()
        loadout_changed = any(getattr(previous.loadout, f) != getattr(settings.loadout, f)
                              for f in RECONNECT_FIELDS)
        if (loadout_changed or previous.ai.live_model != settings.ai.live_model
                or previous.ai.language != settings.ai.language
                or previous.safety.allow_terminal != settings.safety.allow_terminal
                or previous.safety.allow_raw_input != settings.safety.allow_raw_input):
            self.live.request_reconnect()
        try:
            if startup.is_enabled() != settings.general.start_with_windows:
                startup.set_enabled(settings.general.start_with_windows)
        except OSError as exc:
            log.error("Could not change start-up setting: %s", exc)
            self.notify("Wisp", f"Could not change the start-up setting: {exc}")


def run(argv: list[str]) -> int:
    instance = SingleInstance()
    qt_app = QApplication(argv)
    qt_app.setApplicationName(paths.APP_NAME)
    qt_app.setQuitOnLastWindowClosed(False)
    if instance.already_running:
        QMessageBox.information(None, "Wisp", "Wisp is already running. Look for it in the tray.")
        return 0
    app = WispApp(qt_app, background="--background" in argv)
    app.start()
    code = qt_app.exec()
    instance.release()
    return code


if __name__ == "__main__":
    sys.exit(run(sys.argv))
