"""Child-process UIA client used by test_win_integration.py.

Wisp only automates other processes' windows, so the test drives its probe window from a
separate process too (in-process UIA clients calling Qt's provider from a worker thread can
crash, which is not a production path). Prints one JSON line.
Usage: python tests/uia_client_probe.py <hwnd> <action>
"""

from __future__ import annotations

import json
import sys

import comtypes.client  # noqa: F401  (main-thread COM init, as in the app)


def run(hwnd: int, action: str, result: dict) -> None:
    import pythoncom

    from wisp.winapi.uia import Uia, UiaLimit

    # Same as Wisp's tool workers: a non-UI thread in the multithreaded apartment.
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    uia = Uia()
    try:
        if action == "click_and_type":
            result["names"] = [e["name"] for e in uia.list_elements(hwnd)]
            result["how"] = uia.click(uia.find(hwnd, "Probe Action"))
            field = uia.find(hwnd, "Probe Field", editable=True)
            result["typed"] = uia.type_into(field, "hello wisp")
        elif action == "missing":
            uia.find(hwnd, "Nonexistent Fancy Control")
            result["found"] = True
    except UiaLimit as exc:
        result["limit"] = str(exc)


def main() -> None:
    import threading

    result: dict = {}
    worker = threading.Thread(target=run, args=(int(sys.argv[1]), sys.argv[2], result))
    worker.start()
    worker.join()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
