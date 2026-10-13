"""Peak level of the default output device, for the island's music equaliser (D-045).

Documented Core Audio: IMMDevice::Activate(IID_IAudioMeterInformation) and
IAudioMeterInformation::GetPeakValue, normalised 0.0–1.0 and measured before the endpoint volume
(learn.microsoft.com, endpointvolume.h). COM objects are created and used on the Qt thread only
(D-021). Any failure reads as 0.0, so the bars simply rest.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class OutputMeter:
    def __init__(self) -> None:
        self._meter = None
        self._failed = False

    def _open(self):
        import comtypes
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

        speakers = AudioUtilities.GetSpeakers()
        if speakers is None:
            raise OSError("no audio output device")
        unknown = speakers._dev.Activate(IAudioMeterInformation._iid_, comtypes.CLSCTX_ALL, None)
        return unknown.QueryInterface(IAudioMeterInformation)

    def peak(self) -> float:
        if self._failed:
            return 0.0
        try:
            if self._meter is None:
                self._meter = self._open()
            return max(0.0, min(1.0, float(self._meter.GetPeakValue())))
        except Exception as exc:
            log.info("Output meter unavailable: %s", type(exc).__name__)
            self._meter, self._failed = None, True
            return 0.0

    def reset(self) -> None:
        """Try again (the default output device may have changed)."""
        self._meter, self._failed = None, False
