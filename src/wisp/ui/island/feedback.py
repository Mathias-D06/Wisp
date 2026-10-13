"""Services report to the island instead of drawing their own pop-ups (D-045).

``IslandFeedback`` has the HUD's interface (dictation and Circle to Ask call show_state, flash,
hide_now) and ``IslandBubble`` the answer bubble's (show_at, set_text, finish). Both send events
to the island's state machine; when the island is switched off in Settings they fall back to the
old HUD and bubble, so nothing is lost.
"""

from __future__ import annotations

from collections.abc import Callable

TONES = ("accent", "success", "warning", "danger", "muted")


def _tone(dot: str | None) -> str:
    return dot if dot in TONES else "accent"


class IslandFeedback:
    def __init__(self, island, hud):
        self.island = island
        self.hud = hud

    @property
    def accent(self) -> str:
        return self.hud.accent

    @accent.setter
    def accent(self, value: str) -> None:
        self.hud.accent = value

    def _on(self) -> bool:
        return self.island.enabled

    def show_state(self, text: str, dot: str | None = None,
                   level: Callable[[], float] | None = None) -> None:
        if not self._on():
            self.hud.show_state(text, dot, level)
            return
        self.island.set_level_source(level)
        self.island.machine.show_status("dictation", text, _tone(dot),
                                        meter="dictation" if level is not None else None)

    def flash(self, text: str, ms: int = 2500, dot: str | None = None) -> None:
        if not self._on():
            self.hud.flash(text, ms, dot)
            return
        self.island.set_level_source(None)
        if dot == "danger":
            self.island.machine.clear_status()
            self.island.machine.post(text, "", "error", "danger")
        else:
            self.island.machine.show_status("status", text, _tone(dot), ms=ms)

    def hide_now(self) -> None:
        self.hud.hide_now()
        self.island.set_level_source(None)
        self.island.machine.clear_status()


class IslandBubble:
    """Circle to Ask's answer: spoken and shown live in the island (speaking state, Chat tab);
    when it ends, a banner with its first line opens the Chat tab on click."""

    def __init__(self, island, bubble):
        self.island = island
        self.bubble = bubble
        self._text = ""

    def apply_palette(self, surface: str, border: str) -> None:
        self.bubble.apply_palette(surface, border)

    def show_at(self, anchor, text: str) -> None:
        if not self.island.enabled:
            self.bubble.show_at(anchor, text)
            return
        self._text = ""

    def set_text(self, text: str) -> None:
        if not self.island.enabled:
            self.bubble.set_text(text)
            return
        self._text = text

    def finish(self, linger: float = 0.0) -> None:
        if not self.island.enabled:
            self.bubble.finish(linger)
            return
        text, self._text = " ".join(self._text.split()), ""
        if text:
            first = text.split(". ")[0][:120]
            self.island.machine.post("Answer", first, "speaking", "accent",
                                     action=lambda: self.island.open_tab("Chat"))
