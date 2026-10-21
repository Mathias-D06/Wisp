"""Entry point: ``python -m wisp`` or the packaged ``Wisp.exe``.

``--self-check [report.json]`` verifies the build without starting the app (see selfcheck.py);
``--mic-check [report.json]`` opens the microphone for about 1.5 s and reports its levels
(audio/mic_report.py); ``--run-uninstaller <pid>`` waits for that Wisp to close, then starts
the uninstaller (uninstall.py); ``--version`` prints the version.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if "--version" in sys.argv:
        from wisp import __version__

        if sys.stdout is not None:
            print(__version__)
        return 0
    if "--self-check" in sys.argv:
        from wisp import selfcheck

        index = sys.argv.index("--self-check")
        report = Path(sys.argv[index + 1]) if len(sys.argv) > index + 1 else None
        return selfcheck.run(report)
    if "--run-uninstaller" in sys.argv:  # started by Settings → General → Uninstall (D-061)
        from wisp import uninstall

        index = sys.argv.index("--run-uninstaller")
        return uninstall.run_uninstaller(int(sys.argv[index + 1]))
    if "--mic-check" in sys.argv:
        from wisp.audio import mic_report

        index = sys.argv.index("--mic-check")
        report = Path(sys.argv[index + 1]) if len(sys.argv) > index + 1 else None
        return mic_report.run(report)
    from wisp.app import run

    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
