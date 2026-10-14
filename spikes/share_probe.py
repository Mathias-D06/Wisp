r"""Probe the share sheet path (D-051) step by step on this PC.

1. StorageFile.GetFileFromPathAsync for a temporary file, then IStorageItem (vtable slots and the
   async wait).
2. The computed IID of IAsyncOperation<StorageFile> is accepted by QueryInterface on the real
   operation (checks the parameterized-IID algorithm with a runtime-class argument, the same
   form as the DataRequested handler's IID).
3. IDataTransferManagerInterop.GetForWindow for a real top-level window and add_DataRequested.
4. With --show: ShowShareUIForWindow; the DataRequested handler fills the package (the sheet
   opens on screen; press Esc to close it).

Run: .venv\Scripts\python spikes\share_probe.py [--show]
"""

from __future__ import annotations

import sys
import tempfile
import time
from ctypes import POINTER, byref, c_void_p
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wisp.winapi import share
from wisp.winapi import winrt_abi as abi

ASYNC_OPERATION = __import__("uuid").UUID("9fc2b0bb-e446-44e2-aa61-9cab8f636af2")


def main() -> None:
    app = QApplication(sys.argv[:1])
    folder = Path(tempfile.mkdtemp(prefix="wisp-share-"))
    sample = folder / "Wisp share probe.txt"
    sample.write_text("Shared from Wisp's probe.", encoding="utf-8")

    items = share.storage_items([sample])
    print("1 storage items:", len(items))
    for item in items:
        abi.release(item)

    statics = abi.activation_factory("Windows.Storage.StorageFile", share.IID_FILE_STATICS)
    operation = c_void_p()
    with abi.HString(str(sample)) as name:
        abi.call(statics, share.FILE_STATICS_GET_FILE, [c_void_p, POINTER(c_void_p)], name,
                 byref(operation))
    iid = abi.pinterface_iid(ASYNC_OPERATION,
                             abi.class_sig("Windows.Storage.StorageFile", share.IID_FILE))
    typed = abi.query(operation, iid)
    print("2 IAsyncOperation<StorageFile> IID accepted:", iid, bool(typed))
    abi.release(abi.wait_for(operation))
    for pointer in (typed, operation, statics):
        abi.release(pointer)

    window = QWidget()
    window.setWindowTitle("Wisp share probe")
    window.resize(320, 120)
    window.show()
    app.processEvents()
    sheet = share.ShareSheet(int(window.winId()))
    calls = []
    original = sheet._data_requested

    def spy(sender, args):
        result = original(sender, args)
        calls.append(result)
        return result

    sheet._data_requested = spy
    sheet._connect()
    print("3 manager for window:", bool(sheet._manager), "token:", bool(sheet._token.value))
    if "--show" in sys.argv:
        sheet.share([sample], "Wisp share probe")
        deadline = time.monotonic() + 8
        while not calls and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        print("4 DataRequested results:", calls, sheet.last_error or "ok")
    sheet.close()
    window.close()


if __name__ == "__main__":
    main()
