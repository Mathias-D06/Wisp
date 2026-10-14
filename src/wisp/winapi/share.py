"""The Windows share sheet for files (D-051): Nearby Sharing, Mail, Teams and other share targets.

A desktop app gets the DataTransferManager for its window through IDataTransferManagerInterop
(GetForWindow), fills the DataPackage when the DataRequested event fires, and opens the sheet with
ShowShareUIForWindow. PyWinRT doesn't project that interop interface, so this module makes the
calls itself (wisp/winapi/winrt_abi.py). The share sheet asks for the data on the window's own
thread, so everything here runs on the Qt UI thread.

Interface IDs and vtable slots: Windows' own metadata (spikes/winmd_dump.py) and shobjidl_core.h
(IDataTransferManagerInterop: IUnknown, then GetForWindow, ShowShareUIForWindow).
"""

from __future__ import annotations

import ctypes
import logging
import uuid
from ctypes import HRESULT, POINTER, WINFUNCTYPE, byref, c_int64, c_ubyte, c_uint32, c_void_p
from pathlib import Path

from wisp.winapi import winrt_abi as abi

log = logging.getLogger(__name__)

IID_INTEROP = uuid.UUID("3a3dcd6c-3eab-43dc-bcde-45671ce800c8")  # IDataTransferManagerInterop
IID_MANAGER = uuid.UUID("a5caee9b-8708-49d1-8d36-67d25a8da00c")  # IDataTransferManager
IID_ARGS = uuid.UUID("cb8ba807-6ac5-43c9-8ac5-9ba232163182")  # IDataRequestedEventArgs
IID_FILE = uuid.UUID("fa3f6186-4214-428c-a64c-14c9ac7315ea")  # IStorageFile
IID_FILE_STATICS = uuid.UUID("5984c710-daf2-43c8-8bb4-a4d3eacfd03f")  # IStorageFileStatics
IID_ITEM = uuid.UUID("4207a996-ca2f-42f7-bde8-8b10457a7f30")  # IStorageItem
TYPED_EVENT_HANDLER = uuid.UUID("9de1c534-6ae1-11e0-84e1-18a905bcc53f")  # TypedEventHandler`2
ITERABLE = uuid.UUID("faa585ea-6214-4217-afda-7f46de5869b3")  # IIterable`1
ITERATOR = uuid.UUID("6a79e863-4300-459a-9966-cbb660963ee1")  # IIterator`1
MANAGER_CLASS = "Windows.ApplicationModel.DataTransfer.DataTransferManager"
ARGS_CLASS = "Windows.ApplicationModel.DataTransfer.DataRequestedEventArgs"

IID_HANDLER = abi.pinterface_iid(TYPED_EVENT_HANDLER, abi.class_sig(MANAGER_CLASS, IID_MANAGER),
                                 abi.class_sig(ARGS_CLASS, IID_ARGS))
IID_ITEMS = abi.pinterface_iid(ITERABLE, abi.interface_sig(IID_ITEM))
IID_ITEM_ITERATOR = abi.pinterface_iid(ITERATOR, abi.interface_sig(IID_ITEM))

# vtable slots (IInspectable interfaces start at 6; the interop interface is IUnknown-based)
INTEROP_GET_FOR_WINDOW, INTEROP_SHOW = 3, 4
MANAGER_ADD_DATA_REQUESTED, MANAGER_REMOVE_DATA_REQUESTED = 6, 7
ARGS_GET_REQUEST = 6
REQUEST_GET_DATA, REQUEST_FAIL = 6, 9
PACKAGE_GET_PROPERTIES, PACKAGE_SET_STORAGE_ITEMS = 7, 23  # SetStorageItems(value, readOnly)
PROPERTIES_PUT_TITLE, PROPERTIES_PUT_DESCRIPTION = 7, 9
FILE_STATICS_GET_FILE = 6
E_BOUNDS = -2147483637  # 0x8000000B


def _item_iterable(items: list[c_void_p]) -> abi.ComObject:
    """IIterable<IStorageItem> over ``items`` (pointers this module owns)."""

    def first(out) -> int:
        out[0] = _item_iterator(items).new_reference().value
        return abi.S_OK

    return abi.ComObject([IID_ITEMS], [(WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p)), first)],
                         inspectable=True)


def _item_iterator(items: list[c_void_p]) -> abi.ComObject:
    position = [0]

    def current(out) -> int:
        if position[0] >= len(items):
            return E_BOUNDS
        abi.add_ref(items[position[0]])
        out[0] = items[position[0]].value
        return abi.S_OK

    def has_current(out) -> int:
        out[0] = position[0] < len(items)
        return abi.S_OK

    def move_next(out) -> int:
        position[0] = min(position[0] + 1, len(items))
        out[0] = position[0] < len(items)
        return abi.S_OK

    def get_many(capacity, out, actual) -> int:
        count = 0
        while count < capacity and position[0] < len(items):
            abi.add_ref(items[position[0]])
            out[count] = items[position[0]].value
            count += 1
            position[0] += 1
        actual[0] = count
        return abi.S_OK

    pointer_out = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))
    bool_out = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_ubyte))
    many = WINFUNCTYPE(HRESULT, c_void_p, c_uint32, POINTER(c_void_p), POINTER(c_uint32))
    return abi.ComObject([IID_ITEM_ITERATOR], [(pointer_out, current), (bool_out, has_current),
                                               (bool_out, move_next), (many, get_many)],
                         inspectable=True)


def storage_items(paths: list[Path]) -> list[c_void_p]:
    """IStorageItem pointers for files (StorageFile.GetFileFromPathAsync). Caller releases."""
    statics = abi.activation_factory("Windows.Storage.StorageFile", IID_FILE_STATICS)
    items: list[c_void_p] = []
    try:
        for path in paths:
            operation = c_void_p()
            with abi.HString(str(path.resolve())) as name:
                abi.call(statics, FILE_STATICS_GET_FILE, [c_void_p, POINTER(c_void_p)], name,
                         byref(operation))
            try:
                file = abi.wait_for(operation)
            finally:
                abi.release(operation)
            try:
                items.append(abi.query(file, IID_ITEM))
            finally:
                abi.release(file)
    except Exception:
        for item in items:
            abi.release(item)
        raise
    finally:
        abi.release(statics)
    return items


class ShareSheet:
    """Opens the share sheet for files from one window (its HWND)."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self._interop = c_void_p()
        self._manager = c_void_p()
        self._token = c_int64()
        self._handler: abi.ComObject | None = None
        self._pending: tuple[str, list[c_void_p]] | None = None
        self.last_error = ""

    def _connect(self) -> None:
        if self._manager:
            return
        self._interop = abi.activation_factory(MANAGER_CLASS, IID_INTEROP)
        abi.call(self._interop, INTEROP_GET_FOR_WINDOW,
                 [ctypes.c_void_p, POINTER(abi.GUID), POINTER(c_void_p)],
                 self.hwnd, byref(abi.GUID.of(IID_MANAGER)), byref(self._manager))
        self._handler = abi.ComObject(
            [IID_HANDLER], [(WINFUNCTYPE(HRESULT, c_void_p, c_void_p, c_void_p),
                             self._data_requested)])
        abi.call(self._manager, MANAGER_ADD_DATA_REQUESTED, [c_void_p, POINTER(c_int64)],
                 self._handler.pointer, byref(self._token))

    def share(self, paths: list[Path], title: str) -> None:
        """Open the share sheet with ``paths``. Raises OSError if Windows refuses."""
        items = storage_items(paths)
        self._connect()
        self._drop_pending()
        self._pending = (title, items)
        abi.call(self._interop, INTEROP_SHOW, [ctypes.c_void_p], self.hwnd)

    def _data_requested(self, _sender, args) -> int:
        """DataRequested: fill the package with the title and the files (read-only)."""
        if self._pending is None:
            return abi.S_OK
        title, items = self._pending
        request = package = properties = c_void_p()
        try:
            request = abi.get_object(args, ARGS_GET_REQUEST)
            package = abi.get_object(request, REQUEST_GET_DATA)
            properties = abi.get_object(package, PACKAGE_GET_PROPERTIES)
            with abi.HString(title) as text:
                abi.call(properties, PROPERTIES_PUT_TITLE, [c_void_p], text)
            iterable = _item_iterable(items)
            abi.call(package, PACKAGE_SET_STORAGE_ITEMS, [c_void_p, c_ubyte],
                     iterable.pointer, 1)
            self.last_error = ""
            return abi.S_OK
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("Share sheet data request failed: %s", self.last_error)
            return abi.E_FAIL
        finally:
            for pointer in (properties, package, request):
                abi.release(pointer)

    def _drop_pending(self) -> None:
        if self._pending is not None:
            for item in self._pending[1]:
                abi.release(item)
            self._pending = None

    def close(self) -> None:
        self._drop_pending()
        if self._manager:
            abi.call(self._manager, MANAGER_REMOVE_DATA_REQUESTED, [c_int64], self._token)
        for pointer in (self._manager, self._interop):
            abi.release(pointer)
        self._manager = self._interop = c_void_p()
