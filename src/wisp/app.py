"""Application bootstrap: builds the services, the tray and the windows, and wires them."""

from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import datetime

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from wisp import paths, startup
from wisp.ai import dictation as dictation_ai
from wisp.ai import retry
from wisp.ai.dictation import pcm_to_wav
from wisp.assist.client import GeminiAssistModel
from wisp.assist.engine import AssistEngine, Capturer, WatchCheck, real_window_system
from wisp.assist.privacy import Blocklist
from wisp.assist.service import ScreenAssist, Watcher
from wisp.audio import OUTPUT_RATE, mic_check
from wisp.audio.capture import MicCapture
from wisp.audio.convert import has_speech
from wisp.audio.debug_wav import DebugAudioRecorder, save_jpeg, save_pcm
from wisp.audio.playback import Player
from wisp.audio.resample import Resampler
from wisp.circle import CircleController
from wisp.db import Database
from wisp.dictation import DictationController, DictationDeps, insert_text
from wisp.discreet import DiscreetMode
from wisp.files.finder import FileFinder
from wisp.files.shelf import Shelf
from wisp.gcal.service import CalendarService
from wisp.gcal.store import CalendarStore
from wisp.hotkeys.manager import HotkeyManager
from wisp.keystore import KeyStore, SecretJson
from wisp.live.config import build_live_config, is_extended_thinking, system_instruction
from wisp.live.connector import GenaiConnector
from wisp.live.session import LiveSessionManager
from wisp.logging_setup import configure as configure_logging
from wisp.loop import LoopThread
from wisp.phone.service import PhoneLink
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
from wisp.stores.usage import UsageStore
from wisp.system import clipboard
from wisp.system.app_index import AppIndex
from wisp.system.audio_meter import OutputMeter
from wisp.system.clipboard_monitor import ClipboardMonitor
from wisp.system.media import MediaWatcher
from wisp.tools.base import Origin
from wisp.tools.builtin import apps as apps_tools
from wisp.tools.builtin import calendar as calendar_tools
from wisp.tools.builtin import core as core_tools
from wisp.tools.builtin import discreet as discreet_tools
from wisp.tools.builtin import files as files_tools
from wisp.tools.builtin import memory as memory_tools
from wisp.tools.builtin import raw_input as raw_input_tools
from wisp.tools.builtin import schedule as schedule_tools
from wisp.tools.builtin import screen as screen_tools
from wisp.tools.builtin import share as share_tools
from wisp.tools.builtin import system as system_tools
from wisp.tools.builtin import terminal as terminal_tools
from wisp.tools.builtin import todos as todo_tools
from wisp.tools.builtin import ui as ui_tools
from wisp.tools.builtin import web as web_tools
from wisp.tools.builtin import windows as windows_tools
from wisp.tools.confirm import ConfirmationManager
from wisp.tools.dispatcher import Dispatcher
from wisp.tools.registry import ToolRegistry
from wisp.tools.safety import SafetyPolicy, TaintTracker
from wisp.ui import motion, theme
from wisp.ui.bridge import UiInvoker
from wisp.ui.bubble import AnswerBubble
from wisp.ui.confirm_card import ConfirmCard
from wisp.ui.console import ConsoleWindow
from wisp.ui.discreet_card import DiscreetCard
from wisp.ui.hud import Hud
from wisp.ui.icons import orb_icon
from wisp.ui.island.assist_tab import AssistTab, escape_markdown
from wisp.ui.island.calendar_tab import CalendarTab
from wisp.ui.island.clipboard_tab import ClipboardTab
from wisp.ui.island.common import Background
from wisp.ui.island.controls_tab import ControlsTab
from wisp.ui.island.feedback import IslandBubble, IslandFeedback
from wisp.ui.island.files_tab import FilesTab
from wisp.ui.island.island import Island
from wisp.ui.island.machine import pick_countdown
from wisp.ui.island.music import MediaSignals
from wisp.ui.island.power_tab import PowerTab
from wisp.ui.island.stats_tab import StatsTab
from wisp.ui.island.today_tab import TodayTab
from wisp.ui.settings.accounts_page import AccountsPage
from wisp.ui.settings.action_log_page import ActionLogPage
from wisp.ui.settings.assist_page import AssistPage
from wisp.ui.settings.dialog import SettingsDialog
from wisp.ui.settings.discreet_page import DiscreetPage
from wisp.ui.settings.general_page import GeneralPage
from wisp.ui.settings.hotkeys_audio_page import HotkeysAudioPage
from wisp.ui.settings.loadout_page import LoadoutPage
from wisp.ui.settings.memories_page import MemoriesPage
from wisp.ui.settings.routines_page import RoutinesPage
from wisp.ui.settings.safety_page import SafetyPage
from wisp.ui.tray import Tray
from wisp.ui.wallpaper_picker import WallpaperDialog
from wisp.voice import VoiceController, VoiceSignals, make_callbacks
from wisp.winapi import input as winput
from wisp.winapi import windows as win

log = logging.getLogger(__name__)
FILES_TAB = "Files & Share"

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
        self.calendar = CalendarService(
            CalendarStore(self.db),
            SecretJson(paths.google_client_file(), b"Wisp/google-client/v1", "Google OAuth client"),
            SecretJson(paths.google_token_file(), b"Wisp/google-token/v1", "Google sign-in"))
        self.services.calendar = self.calendar
        self.discreet = DiscreetMode(self.settings_store, self.calendar)
        self.services.discreet = self.discreet
        self.shelf = Shelf(self.db)
        self.finder = FileFinder()
        self.phone = PhoneLink(lambda: self.finder.downloads_folder() / "Wisp",
                               lambda: peek().share.phone_max_upload_mb * 1024 * 1024)
        self._share_sheet = None
        self.services.shelf, self.services.finder = self.shelf, self.finder
        self.services.phone = self.phone
        self.services.share_files = self._share_files
        self.services.open_files_tab = self._open_files_tab
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
            make_callbacks(self.voice_signals, self.player, self.confirmations.on_user_utterance,
                           mic_notice=lambda: mic_check.silence_notice(
                               self.mic.device_label, mic_check.privacy_states())),
            has_key=self.keystore.has_key,
            idle_timeout_s=lambda: peek().ai.idle_timeout_min * 60,
            always_listening=lambda: self.voice.always_listening,  # off in Discreet mode
            is_playing=self.player.is_playing,
            extended_thinking=lambda: is_extended_thinking(peek().ai.live_model),
            debug_audio=DebugAudioRecorder(lambda: peek().audio.save_debug_audio),
        )
        self.dispatcher.set_model_notifier(self.live.send_text)
        self.voice = VoiceController(
            self.live, self.mic, self.player, self.voice_signals, self.settings_store,
            self.confirmations, self.notify,
        )
        self.services.live, self.services.voice = self.live, self.voice
        self.services.mic, self.services.player = self.mic, self.player
        self._build_screen_assist()

        self.hotkeys = HotkeyManager()
        self.hotkeys.apply(settings)
        self.hotkeys.signals.event.connect(self._on_hotkey)

        self.clipboard_owner = QWidget()  # native window on the Qt thread that owns our writes
        self.clipboard_owner_hwnd = int(self.clipboard_owner.winId())
        self.hud = Hud(settings.loadout.accent)
        palette = theme.palette(settings.loadout.theme, settings.loadout.accent)
        self.bubble = AnswerBubble(palette.surface, palette.border)
        self.console = ConsoleWindow(self.voice, settings.loadout.accent)
        self._build_island(settings)
        # Dictation and Circle to Ask report to the island (HUD/bubble when it's off; D-045).
        self.feedback = IslandFeedback(self.island, self.hud)
        self.island_bubble = IslandBubble(self.island, self.bubble)
        self.dictation = DictationController(self._dictation_deps(), self.mic, self.feedback,
                                             self.services.stats, self.notify)
        self.circle = CircleController(self.voice, self.live, self.mic, self.feedback,
                                       self.island_bubble, self.keystore.has_key,
                                       lambda: peek().loadout.accent)

        self.confirm_card = ConfirmCard(self.confirmations)
        self.confirm_card.apply_palette(palette.surface, palette.border)
        self.confirm_card.showing.connect(self.island.machine.set_confirming)
        self.voice.visual.connect(lambda state, _level, text: self.tray.set_state(state, text))
        self._settings_dialog: SettingsDialog | None = None
        self.settings_store.subscribe(lambda s: self.ui.call(lambda: self._on_settings_changed(s)))
        self.keystore.subscribe(lambda has_key: self.ui.call(lambda: self._on_key_changed(has_key)))

    # ----- Island ----------------------------------------------------------------------------
    def _build_island(self, settings: Settings) -> None:
        self.background = Background(self.loop.loop)
        self.media_signals = MediaSignals()
        self.media = MediaWatcher(self.loop.loop, self.media_signals.changed.emit)
        self.services.media = self.media
        self.clipboard_monitor = ClipboardMonitor(self.services.clipboard,
                                                  self.clipboard_owner_hwnd)
        services = self.services
        palette = theme.palette("dark", settings.loadout.accent)  # the island is always black
        tabs = [
            ("Screen", AssistTab(self.assist, self.watcher, palette,
                                 lambda: self.hotkeys.display("screen_assist"))),
            ("Controls", ControlsTab(self.background, palette)),
            ("Today", TodayTab(services.todos, services.scheduler)),
            ("Calendar", CalendarTab(self.calendar)),
            ("Stats", StatsTab(services.stats, self.settings_store, settings.loadout.accent,
                               self.usage)),
            ("Clipboard", ClipboardTab(services.clipboard, self.clipboard_monitor)),
            (FILES_TAB, FilesTab(self.finder, self.shelf, services.app_index, self.phone,
                                 self.background, palette, share=self._share_files)),
            ("Power", PowerTab(self.background, palette, services.action_log)),
        ]
        self.island = Island(self.voice, settings.loadout.accent, self.keystore.has_key,
                             lambda action: self.media.command(action), tabs,
                             meter=OutputMeter())
        self.island.configure(settings.general.island_monitor,
                              settings.general.island_hide_when_idle,
                              settings.general.island_hide_after_s,
                              settings.general.island_keep_for_music)
        self.island.settings_requested.connect(lambda page: self.open_settings(page or None))
        self.island.console_requested.connect(self.console.open)
        self.island.quit_requested.connect(self.quit)
        self.media_signals.changed.connect(self.island.show_media)
        calendar_tab = next(w for name, w in tabs if name == "Calendar")
        calendar_tab.open_accounts.connect(lambda: self.open_settings("Accounts"))
        self.calendar.changed.connect(self._update_countdown)
        files_tab = next(w for name, w in tabs if name == FILES_TAB)
        self.island.watch_stop_requested.connect(lambda: self.watcher.stop("clicked"))
        self.island.discreet_toggled.connect(lambda on: self.discreet.set_enabled(on, "menu"))
        self.discreet_card = DiscreetCard()
        self.discreet_card.speak_requested.connect(self.assist.speak)
        self.discreet_card.open_requested.connect(self._open_discreet_card)
        self.discreet.changed.connect(self._apply_discreet)
        self.voice.transcript.connect(self._on_transcript_discreet)
        self.watcher.changed.connect(self._update_watch_indicator)
        self.watcher.commented.connect(self._on_watch_comment)
        self.assist.started.connect(self._on_assist_started)
        self.assist.answered.connect(self._on_assist_answer)
        self.assist.failed.connect(self._on_assist_failed)
        self.assist.unheard.connect(self._on_assist_unheard)
        self.assist.progress.connect(lambda note: self.feedback.show_state(note, "warning"))
        self.island.files_dropped.connect(files_tab.add_to_shelf)
        self.phone.changed.connect(self._update_phone_activity)
        self.phone.upload_requested.connect(lambda _upload: self.island.open_tab(FILES_TAB))
        self.phone.received.connect(lambda upload: self.notify(
            "Saved from your phone", f"{upload.saved.name} is in Downloads\\Wisp"))
        # Esc anywhere collapses the expanded island (the key still reaches the app in front).
        self.island.machine.subscribe(
            lambda p: setattr(self.hotkeys.hook, "watch_escape", p.mode == "expanded"))

    # ----- tools -----------------------------------------------------------------------------
    def _register_tools(self) -> None:
        for module in (core_tools, apps_tools, windows_tools, web_tools, screen_tools, ui_tools,
                       files_tools, share_tools, todo_tools, calendar_tools, memory_tools,
                       system_tools, terminal_tools, raw_input_tools, discreet_tools):
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
        self._update_countdown()
        for todo in self.services.todos.due_reminders():
            self.services.todos.mark_reminded(todo.id)
            when = todo.due_at.strftime("%H:%M") if todo.due_at else ""
            self.notify("Reminder", f"{todo.text} (due {when})")

    def _update_countdown(self) -> None:
        """The island's countdown: the next reminder or routine due within 10 minutes, or the
        next calendar event within the heads-up time (Settings → Accounts)."""
        now = datetime.now().astimezone()
        items = [(todo.text, todo.due_at) for todo in self.services.todos.list()
                 if todo.remind and not todo.reminded and todo.due_at]
        try:
            items += [(task.title, when) for task, when in self.services.scheduler.upcoming(5)]
        except Exception as exc:
            log.info("No upcoming tasks for the countdown: %s", type(exc).__name__)
        candidates = [pick_countdown(items, now)]
        heads_up = self.settings_store.peek().calendar.heads_up_min
        event = self.calendar.next_event(now, heads_up) if self.calendar.connected else None
        if event is not None:
            candidates.append((event.title, event.start.timestamp()))
        picked = min((c for c in candidates if c), key=lambda c: c[1], default=None)
        self.island.machine.set_countdown(*(picked or (None, None)))

    def _dictation_deps(self) -> DictationDeps:
        peek = self.settings_store.peek
        owner = self.clipboard_owner_hwnd
        modifier_keys = (winput.VK_LWIN, winput.VK_RWIN, winput.VK_LCONTROL, winput.VK_RCONTROL,
                         winput.VK_LSHIFT, winput.VK_RSHIFT, winput.VK_LMENU, winput.VK_RMENU)
        return DictationDeps(
            transcribe=lambda pcm, on_busy: dictation_ai.transcribe(
                self.keystore.get() or "", peek().ai.text_model, pcm, peek().ai.language,
                on_busy),
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
            save_debug=lambda pcm: (save_pcm("dictation", pcm)
                                    if peek().audio.save_debug_audio else None),
            mic_silence=self._mic_silence,
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
        self._apply_discreet(self.discreet.active)  # remembered from last time (D-053)
        self.tray.show()
        self.services.app_index.refresh_in_background()
        # PortAudio's start-up (and the device query) took over a second on the first hotkey;
        # do it now, on a thread. No stream is opened: nothing is recorded (D-058).
        threading.Thread(target=self.mic.warm_up, name="mic-warm-up", daemon=True).start()
        threading.Thread(target=retry.warm_up, name="gemini-warm-up", daemon=True).start()
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
        self.calendar.start()
        self.island.update_key_prompt()
        self.island.set_enabled(self.settings_store.peek().general.show_island)
        error = self.hotkeys.start()
        if error:
            self.notify("Hotkeys unavailable", f"Wisp could not install its keyboard hook: {error}")
        if not self.keystore.has_key():
            self.notify("Wisp is running",
                        "Add your Gemini API key in Settings to use voice and AI features.")
            if not self.background:
                self.open_settings("General")
        elif not self.background:
            if self.island.enabled:
                talk = self.hotkeys.display("push_to_talk")
                self.island.machine.post("Wisp is ready", f"Hover here, or hold {talk} to talk",
                                         "speaking", "accent", action=self.island.expand)
            else:
                self.console.open()

    # ----- Screen Assist and Watch mode (D-052) --------------------------------------------------
    def _build_screen_assist(self) -> None:
        peek = self.settings_store.peek
        self.usage = UsageStore(self.db)
        self.services.usage = self.usage

        def blocklist() -> Blocklist:
            assist = peek().screen_assist
            return Blocklist.from_lists(assist.blocked_apps, assist.blocked_titles)

        self.services.blocklist = blocklist
        capturer = Capturer(real_window_system(), blocklist, log_capture=self._log_capture,
                            save_debug=lambda jpeg, label: (save_jpeg(label, jpeg)
                                                            if peek().audio.save_debug_audio
                                                            else None))
        model = GeminiAssistModel(lambda: self.keystore.get() or "", lambda: peek().ai.text_model,
                                  lambda: peek().ai.tts_model,
                                  fallback_model=lambda: peek().ai.fallback_text_model)

        def usage(feature: str, reply) -> None:
            self.usage.record(feature, reply.model or peek().ai.text_model,
                              reply.input_tokens, reply.output_tokens)

        engine = AssistEngine(model, capturer, lambda: peek().ai.language, on_usage=usage)
        self.assist = ScreenAssist(
            engine, self.mic, self.player, peek, self.keystore.has_key,
            voice_name=lambda: peek().loadout.voice, speak_allowed=self._speak_answers,
            paste=self._paste_text, to_wav=pcm_to_wav, has_speech=has_speech,
            resample=lambda pcm, rate: (pcm if rate == OUTPUT_RATE
                                        else Resampler(rate, OUTPUT_RATE).process(pcm)),
            on_speech_usage=lambda speech: self.usage.record(
                "speech", peek().ai.tts_model, speech.input_tokens, speech.output_tokens),
            mic_silence=self._mic_silence)
        check = WatchCheck(model, capturer, lambda: peek().screen_assist.watch_comment_gap_s,
                           on_usage=usage)
        self.watcher = Watcher(check, peek, lambda: self.usage.record(
            "watch", peek().ai.text_model, skipped=True), self.keystore.has_key)
        self.services.assist, self.services.watcher = self.assist, self.watcher

    def _log_capture(self, entry: dict) -> None:
        """Every screenshot in the Action log: when, which window, why; never the image."""
        blocked = "blocked" in entry
        self.services.action_log.record(
            origin=entry.get("origin", "screen_assist"), tool="screen_capture",
            args={"window": entry.get("window", ""), "target": entry.get("target", ""),
                  "mode": entry.get("mode", "")},
            decision="refused (blocklist)" if blocked else "captured",
            result={"blocked": entry["blocked"]} if blocked
            else {"pixels": entry.get("pixels"), "hidden_areas": entry.get("masked", 0)},
            ok=not blocked)

    def _mic_silence(self, pcm: bytes) -> str | None:
        """The notice naming the Windows setting to check, if the mic gave only silence."""
        return mic_check.notice_if_silent(pcm, self.mic.device_label)

    def _speak_answers(self) -> bool:
        if self.discreet.active:  # Discreet mode: text only, unless kept on for headphones
            return self.discreet.profile().speak_replies
        return self.settings_store.peek().screen_assist.speak_answers

    def _paste_text(self, hwnd: int, text: str) -> str:
        """Reply mode's Insert: paste into the window the screenshot came from (D-052)."""
        if not win.is_window(hwnd):
            return "That window has closed."
        target = win.WindowInfo(hwnd, "", "", win.pid_of(hwnd), False, False)
        if insert_text(self._dictation_deps(), target, text) == "copied":
            return "Copied: press Ctrl+V in that window (administrator windows block pasting)."
        return "Inserted. Check it and send it yourself."

    def _on_assist_started(self) -> None:
        if self.assist.listening:
            self.feedback.show_state("Listening… release to ask", "accent",
                                     lambda: self.mic.level)
        else:
            self.feedback.show_state("Looking…", "warning")

    def _on_assist_answer(self, exchange) -> None:
        self.feedback.hide_now()
        if self.discreet.active:  # only the small card (D-053)
            notes = "".join(f"*{escape_markdown(note)}*\n\n" for note in exchange.notes)
            self.discreet_card.show_text(notes + exchange.answer, self.island.card_anchor(),
                                         kind="screen", speakable=True, openable=True)
            return
        if self.island.enabled:
            self.island.open_tab("Screen")
        else:
            self.notify("Screen Assist", exchange.answer[:240])

    def _on_assist_unheard(self, message: str) -> None:
        """The keys were held but no question came through: a warning banner (it opens up in
        Discreet mode too) whose click shows the whole message in the Screen tab (D-058)."""
        self.feedback.hide_now()
        self._notify("Screen Assist didn't hear a question", message)

    def _on_assist_failed(self, message: str) -> None:
        """A warning banner (errors open up in Discreet mode too); clicking it opens the Screen
        tab, which shows the whole message. A Windows notification when the island is off."""
        self.feedback.hide_now()
        self._notify("Screen Assist failed", message)

    def _on_watch_comment(self, result) -> None:
        if self.discreet.active:
            self.discreet_card.show_text(f"**Wisp noticed:** {result.text}",
                                         self.island.card_anchor(), kind="watch")
            if self.settings_store.peek().screen_assist.watch_speak and self._speak_answers():
                self.assist.speak(result.text)
            return
        if self.island.enabled and not self.island.machine.hidden:
            self.island.notify("Wisp noticed", result.text)
        else:
            self.tray.notify("Wisp noticed", result.text)
        if self.settings_store.peek().screen_assist.watch_speak and self._speak_answers():
            self.assist.speak(result.text)

    # ----- Discreet mode (D-053) ------------------------------------------------------------------
    def _apply_discreet(self, active: bool) -> None:
        """On: the quiet look, text-only answers, push-to-talk. Off: everything as before (the
        normal settings were never changed)."""
        profile = self.discreet.profile()
        self.island.set_discreet(self.discreet.look())
        self.player.muted = active and not profile.speak_replies
        if self.player.muted:
            self.player.clear()
        self.voice.set_discreet(active)
        self.discreet_card.configure(profile.card_text_px, profile.card_opacity / 100,
                                     profile.card_seconds)
        if not active:
            self.discreet_card.dismiss()
        action = getattr(self, "discreet_action", None)
        if action is not None:
            action.blockSignals(True)
            action.setChecked(active)
            action.blockSignals(False)

    def _on_transcript_discreet(self, role: str, text: str, final: bool, _turn: int = 0) -> None:
        """Discreet mode shows the voice session's replies as text on the card (the audio
        isn't played), unless a Screen Assist answer is showing there."""
        if not self.discreet.active or role != "model" or not text.strip():
            return
        card = self.discreet_card
        if card.isVisible() and card.kind == "screen":
            return
        card.show_text(text, self.island.card_anchor(), kind="voice", final=final,
                       speakable=True, openable=True)

    def _open_discreet_card(self) -> None:
        kind = self.discreet_card.kind
        self.island.open_tab("Screen" if kind in ("screen", "watch") else "Chat")

    def _update_watch_indicator(self) -> None:
        watcher = self.watcher
        running = watcher.running
        self.island.machine.set_watching("Watching" if running else None,
                                         watcher.ends_at if running else None)
        self.tray.set_badge(theme.current().warning if running else "",
                            "Watch mode is on: looking at your screen" if running else "")
        action = getattr(self, "stop_watch_action", None)  # the tray menu comes in start()
        if action is not None:
            action.setVisible(running)

    def _update_phone_activity(self) -> None:
        """While the phone link runs, the island shows it with the time left (and stays up)."""
        running = self.phone.running
        self.island.machine.set_sharing("Phone link" if running else None,
                                        self.phone.ends_at if running else None)

    def _open_files_tab(self) -> bool:
        """Show the Files & Share tab; False when the island is switched off."""
        if not self.island.enabled:
            return False
        self.island.open_tab(FILES_TAB)
        return True

    def _share_files(self, paths) -> None:
        """The Windows share sheet for ``paths``, attached to the island's window (D-051)."""
        from wisp.winapi.share import ShareSheet

        if self._share_sheet is None:
            self._share_sheet = ShareSheet(int(self.island.winId()))
        title = paths[0].name if len(paths) == 1 else f"{len(paths)} files"
        self._share_sheet.share(list(paths), title)

    def quit(self) -> None:
        log.info("Wisp quitting")
        self.phone.stop()
        self.watcher.stop("quit")
        self.assist.stop_speaking()
        if self._share_sheet is not None:
            self._share_sheet.close()
        self.services.scheduler.shutdown()
        self.clipboard_monitor.close()
        self.media.stop()
        self.background.shutdown()
        self.island.set_enabled(False)
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
        self.ui.call(lambda: self._notify(title, message))

    def _notify(self, title: str, message: str) -> None:
        """Banners in the island; a Windows notification when the island is off or hidden
        behind a full-screen app (D-045)."""
        if self.island.enabled and not self.island.machine.hidden:
            self.island.notify(title, message)  # a pulse in Discreet mode, unless an error
        elif not (self.discreet.active and self.discreet.profile().mute_toasts):
            self.tray.notify(title, message)

    # ----- UI --------------------------------------------------------------------------------
    def _build_tray_menu(self) -> None:
        settings = self.settings_store.get()
        self.talk_action = self.tray.add_action(
            f"Talk ({self.hotkeys.display('push_to_talk')})", self.voice.toggle_talk)
        self.tray.add_action("Open console", self.console.open)
        self.mute_action = self.tray.add_action("Mute microphone", self.voice.set_muted, True)
        self.mute_action.setChecked(settings.audio.mic_muted)
        self.discreet_action = self.tray.add_action(
            "Discreet mode", lambda on: self.discreet.set_enabled(on, "tray"), True)
        self.discreet_action.setChecked(self.discreet.active)
        self.stop_watch_action = self.tray.add_action(
            "Stop watching the screen", lambda: self.watcher.stop("tray"))
        self.stop_watch_action.setVisible(False)
        self.listen_action = self.tray.add_action("Always listening",
                                                  self.voice.set_always_listening, True)
        self.listen_action.setChecked(settings.audio.always_listening)
        self.tray.add_separator()
        self.tray.add_action("Settings…", lambda: self.open_settings())
        self.tray.add_separator()
        self.tray.add_action("Quit Wisp", self.quit)
        self.tray.on_click(self._tray_clicked)

    def _tray_clicked(self) -> None:
        if self.island.enabled and not self.island.machine.hidden:
            self.island.open_tab("Chat")
        else:
            self.console.open()

    def settings_pages(self) -> list:
        return [
            GeneralPage(self.settings_store, self.keystore, uninstall_app=self._uninstall),
            AccountsPage(self.calendar),
            AssistPage(),
            DiscreetPage(),
            LoadoutPage(self.registry, open_wallpaper=self._open_wallpaper),
            HotkeysAudioPage(self.mic),
            SafetyPage(self.registry),  # after Loadout: it may tick the terminal/input skills
            MemoriesPage(self.services.memory),
            RoutinesPage(self.services.tasks, self.services.scheduler),
            ActionLogPage(self.services.action_log, str(paths.log_dir())),
        ]

    def _uninstall(self) -> None:
        """Settings → General → Uninstall: a waiter starts the uninstaller once Wisp has closed
        (the uninstaller refuses while Wisp's mutex exists, D-061)."""
        from wisp import uninstall

        uninstall.start_waiter(os.getpid())
        self.quit()

    def _open_wallpaper(self, parent) -> None:
        WallpaperDialog(self.background, parent).exec()

    def open_settings(self, page: str | None = None) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.settings_store, self.settings_pages())
        self._settings_dialog.open_page(page)

    def _on_hotkey(self, name: str, kind: str) -> None:
        (log.debug if kind in ("arm", "disarm") else log.info)("Hotkey %s %s", name, kind)
        self.voice.on_hotkey(name, kind)
        self.dictation.on_hotkey(name, kind)
        self.circle.on_hotkey(name, kind)
        self.assist.on_hotkey(name, kind)
        if name == "watch" and kind == "press":
            self.watcher.toggle()
        if name == "discreet" and kind == "press":
            self.discreet.toggle("hotkey")
        if name == "island" and kind == "press":
            self.island.toggle()
        elif name == "escape":
            self.island.escape()

    def _apply_theme(self, settings: Settings) -> None:
        """One place applies the design tokens: palette, stylesheet, base font, motion."""
        motion.configure(settings.loadout.reduce_motion)
        palette = theme.palette(settings.loadout.theme, settings.loadout.accent)
        self.qt_app.setFont(theme.app_font())  # in points: Qt widgets copy its point size
        self.qt_app.setStyleSheet(theme.stylesheet(palette))
        self.qt_app.setWindowIcon(orb_icon(palette.accent))  # title bars and the taskbar
        theme.set_current(palette)

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
        self.island.set_accent(settings.loadout.accent)
        self.island.configure(settings.general.island_monitor,
                              settings.general.island_hide_when_idle,
                              settings.general.island_hide_after_s,
                              settings.general.island_keep_for_music)
        if settings.discreet.enabled != previous.discreet.enabled:
            self.discreet.set_enabled(settings.discreet.enabled, "settings")
        elif self.discreet.active and settings.discreet != previous.discreet:
            self._apply_discreet(True)  # a changed Discreet setting, while it's on
        self.discreet.check_schedule()
        self.island.set_enabled(settings.general.show_island)
        if not settings.general.show_island:
            self.phone.stop()  # its QR code and indicator live in the island
        self.island.panel.sync_toggles(settings.audio.mic_muted, settings.audio.always_listening)
        self.confirm_card.apply_palette(palette.surface, palette.border)
        self.island_bubble.apply_palette(palette.surface, palette.border)
        self.hud.accent = settings.loadout.accent
        self.hotkeys.apply(settings)
        self.talk_action.setText(f"Talk ({self.hotkeys.display('push_to_talk')})")
        self.mute_action.blockSignals(True)
        self.mute_action.setChecked(settings.audio.mic_muted)
        self.mute_action.blockSignals(False)
        self.listen_action.blockSignals(True)
        self.listen_action.setChecked(settings.audio.always_listening)
        self.listen_action.blockSignals(False)
        self.console.sync_toggles(settings.audio.mic_muted, settings.audio.always_listening)
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
