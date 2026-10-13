"""Controls tab: volume, output device, Wi-Fi, Bluetooth, Night Light, dark mode, brightness."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from wisp.system import controls, radios
from wisp.ui.island.common import (
    BLUETOOTH,
    BRIGHTNESS,
    MUTE,
    NIGHT,
    THEME,
    VOLUME,
    WIFI,
    Chip,
    GlyphButton,
    section,
)


class ControlsTab(QWidget):
    def __init__(self, background, palette):
        super().__init__()
        self.bg = background
        self.palette_ = palette
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(section("Sound"))
        row = QHBoxLayout()
        self.mute = GlyphButton(VOLUME, "Mute")
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self._mute_toggled)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setAccessibleName("Volume")
        self.volume_label = QLabel("–")
        self.volume_label.setFixedWidth(34)
        self._volume_timer = QTimer(self, singleShot=True, interval=120)
        self._volume_timer.timeout.connect(self._apply_volume)
        self.volume.valueChanged.connect(self._volume_moved)
        row.addWidget(self.mute)
        row.addWidget(self.volume, 1)
        row.addWidget(self.volume_label)
        layout.addLayout(row)
        self.output = QComboBox()
        self.output.setAccessibleName("Output device")
        self.output.activated.connect(self._output_chosen)
        layout.addWidget(self.output)

        layout.addWidget(section("Quick settings"))
        grid = QGridLayout()
        color = palette.text
        self.wifi = Chip(WIFI, "Wi-Fi", color)
        self.bluetooth = Chip(BLUETOOTH, "Bluetooth", color)
        self.night = Chip(NIGHT, "Night light", color)
        self.dark = Chip(THEME, "Dark mode", color)
        for index, chip in enumerate((self.wifi, self.bluetooth, self.night, self.dark)):
            grid.addWidget(chip, index // 2, index % 2)
        self.wifi.clicked.connect(lambda on: self._radio("wifi", on))
        self.bluetooth.clicked.connect(lambda on: self._radio("bluetooth", on))
        self.night.clicked.connect(self._night)
        self.dark.clicked.connect(self._dark)
        layout.addLayout(grid)

        self.brightness_row = QWidget()
        b_layout = QHBoxLayout(self.brightness_row)
        b_layout.setContentsMargins(0, 0, 0, 0)
        b_icon = GlyphButton(BRIGHTNESS, "Brightness")
        b_icon.setEnabled(False)
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.brightness.setRange(0, 100)
        self.brightness.setAccessibleName("Brightness")
        self._brightness_timer = QTimer(self, singleShot=True, interval=150)
        self._brightness_timer.timeout.connect(self._apply_brightness)
        self.brightness.valueChanged.connect(self._brightness_moved)
        b_layout.addWidget(b_icon)
        b_layout.addWidget(self.brightness, 1)
        layout.addWidget(section("Display"))
        layout.addWidget(self.brightness_row)
        self.message = QLabel()
        self.message.setObjectName("Hint")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        layout.addStretch(1)

    # ----- refresh -----------------------------------------------------------------------------
    def refresh(self) -> None:
        def read() -> dict:
            data: dict = {}
            for key, fn in (("volume", controls.volume), ("outputs", controls.output_devices),
                            ("brightness", controls.brightness), ("dark", controls.dark_mode),
                            ("night", controls.night_light)):
                try:
                    data[key] = fn()
                except Exception as exc:
                    data[key] = None
                    data.setdefault("errors", []).append(f"{key}: {exc}")
            return data

        self.bg.run(read, self._show)
        self.bg.run_coro(radios.states(), self._show_radios, lambda _e: self._show_radios({}))

    def _show(self, data) -> None:
        if isinstance(data, Exception):
            self.message.setText(f"Couldn't read system settings: {data}")
            return
        self._loading = True
        if data.get("volume"):
            level, muted = data["volume"]
            self.volume.setValue(level)
            self.volume_label.setText(f"{level}%")
            self.mute.setChecked(muted)
            self.mute.set_icon_name(MUTE if muted else VOLUME)
        self.output.clear()
        for device in data.get("outputs") or []:
            self.output.addItem(device.name, device.id)
            if device.is_default:
                self.output.setCurrentIndex(self.output.count() - 1)
        level = data.get("brightness")
        self.brightness_row.setVisible(level is not None)
        if level is not None:
            self.brightness.setValue(level)
        self.dark.setChecked(bool(data.get("dark")))
        self.night.setChecked(bool(data.get("night")))
        self.night.setToolTip("" if data.get("night") is not None else
                              "Night Light state unknown here; clicking opens Settings")
        self._loading = False

    def _show_radios(self, states) -> None:
        states = states if isinstance(states, dict) else {}
        for name, chip in (("wifi", self.wifi), ("bluetooth", self.bluetooth)):
            value = states.get(name)
            chip.setEnabled(value is not None)
            chip.setChecked(bool(value))

    # ----- actions -----------------------------------------------------------------------------
    def _volume_moved(self, value: int) -> None:
        self.volume_label.setText(f"{value}%")
        if not self._loading:
            self._volume_timer.start()

    def _apply_volume(self) -> None:
        value = self.volume.value()
        self.bg.run(lambda: controls.set_volume(value), None, self._failed)

    def _mute_toggled(self, muted: bool) -> None:
        self.mute.set_icon_name(MUTE if muted else VOLUME)
        if not self._loading:
            self.bg.run(lambda: controls.set_mute(muted), None, self._failed)

    def _output_chosen(self, index: int) -> None:
        device_id = self.output.itemData(index)
        self.bg.run(lambda: controls.set_default_output(device_id), lambda _r: self.refresh(),
                    self._failed)

    def _brightness_moved(self, _value: int) -> None:
        if not self._loading:  # programmatic updates during refresh must not write back
            self._brightness_timer.start()

    def _apply_brightness(self) -> None:
        value = self.brightness.value()
        self.bg.run(lambda: controls.set_brightness(value), None, self._failed)

    def _radio(self, name: str, on: bool) -> None:
        def done(result) -> None:
            if result != "ok":
                self.message.setText(f"Windows didn't allow changing {name}.")
                os.startfile(controls.SETTINGS_PAGES[name])
            self.bg.run_coro(radios.states(), self._show_radios)

        self.bg.run_coro(radios.set_state(name, on), done, self._failed)

    def _night(self, on: bool) -> None:
        self.bg.run(lambda: controls.set_night_light(on), None, self._failed)

    def _dark(self, on: bool) -> None:
        self.bg.run(lambda: controls.set_dark_mode(on), None, self._failed)

    def _failed(self, exc: Exception) -> None:
        page = getattr(exc, "page", None)
        self.message.setText(str(exc))
        if page:
            os.startfile(page)  # documented ms-settings: page for the control
        self.refresh()
