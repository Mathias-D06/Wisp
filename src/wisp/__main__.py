"""Entry point: ``python -m wisp`` or the packaged ``Wisp.exe``."""

from __future__ import annotations

import sys


def main() -> int:
    from wisp.app import run

    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
