"""Entry point: ``python -m wisp`` or the packaged ``Wisp.exe``.

``--self-check [report.json]`` verifies the build without starting the app (see selfcheck.py);
``--version`` prints the version.
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
    from wisp.app import run

    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
