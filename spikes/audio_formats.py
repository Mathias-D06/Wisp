"""Spike: confirm the default devices accept the Live API formats without recording anything.

Run: .venv\\Scripts\\python spikes\\audio_formats.py
Uses sounddevice.check_input_settings / check_output_settings (PortAudio Pa_IsFormatSupported).
"""

import sounddevice as sd

hostapis = sd.query_hostapis()
for api_index, api in enumerate(hostapis):
    for kind, dev in (("in", api["default_input_device"]), ("out", api["default_output_device"])):
        if dev < 0:
            continue
        rate = 16000 if kind == "in" else 24000
        check = sd.check_input_settings if kind == "in" else sd.check_output_settings
        try:
            check(device=dev, samplerate=rate, channels=1, dtype="int16")
            verdict = "OK"
        except Exception as exc:
            verdict = f"REJECTED ({exc})"
        name = sd.query_devices(dev)["name"]
        print(f"{api['name']:<22} {kind} dev={dev:<3} {rate} Hz mono int16: {verdict} [{name}]")
    del api_index
