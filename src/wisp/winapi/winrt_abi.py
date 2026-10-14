"""A little of the Windows Runtime ABI with ctypes, for the one place PyWinRT can't reach: an
object tied to a Win32 window through a COM interop interface (the share sheet, D-051).

* HSTRING: WindowsCreateString / WindowsDeleteString (combase).
* Activation factories: RoGetActivationFactory(class name, IID).
* Calls through a vtable slot. Slot numbers come from Windows' own metadata
  (C:\\Windows\\System32\\WinMetadata\\*.winmd, see spikes/winmd_dump.py): IUnknown takes slots
  0-2, IInspectable 3-5, so an interface's first method is slot 6. Delegates derive from
  IUnknown only, so Invoke is slot 3.
* IIDs of parameterized types ("pinterface") per the WinRT type system: a version 5 UUID (SHA-1)
  of the type's signature in the namespace 11f47ad5-7b73-42c0-abae-878b1e16adee.
* ComObject: a COM object implemented in Python (a delegate, an iterable), with reference counting.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from ctypes import HRESULT, POINTER, WINFUNCTYPE, byref, c_uint32, c_ulong, c_void_p, wintypes
from typing import ClassVar

log = logging.getLogger(__name__)

S_OK = 0
E_FAIL = -2147467259  # 0x80004005
E_NOINTERFACE = -2147467262  # 0x80004002
E_POINTER = -2147467261  # 0x80004003
PINTERFACE_NAMESPACE = uuid.UUID("11f47ad5-7b73-42c0-abae-878b1e16adee")
IID_IUNKNOWN = uuid.UUID("00000000-0000-0000-c000-000000000046")
IID_IINSPECTABLE = uuid.UUID("af86e2e0-b12d-4c6a-9c5a-d7aa65101e90")
IID_IAGILEOBJECT = uuid.UUID("94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90")
IID_IASYNCINFO = uuid.UUID("00000036-0000-0000-c000-000000000046")

ASYNC_STARTED, ASYNC_COMPLETED, ASYNC_CANCELED, ASYNC_ERROR = 0, 1, 2, 3


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, value: uuid.UUID) -> GUID:
        return cls.from_buffer_copy(value.bytes_le)

    def uuid(self) -> uuid.UUID:
        return uuid.UUID(bytes_le=bytes(self))


def pinterface_iid(generic: uuid.UUID, *args: str) -> uuid.UUID:
    """The IID of a parameterized interface or delegate instance; ``args`` are type
    signatures such as ``interface_sig(...)`` or ``class_sig(...)``."""
    return uuid.uuid5(PINTERFACE_NAMESPACE, f"pinterface({{{generic}}};{';'.join(args)})")


def interface_sig(iid: uuid.UUID) -> str:
    return f"{{{iid}}}"


def class_sig(name: str, default_interface: uuid.UUID) -> str:
    return f"rc({name};{interface_sig(default_interface)})"


_combase = ctypes.WinDLL("combase")
_combase.WindowsCreateString.argtypes = [wintypes.LPCWSTR, c_uint32, POINTER(c_void_p)]
_combase.WindowsCreateString.restype = HRESULT
_combase.WindowsDeleteString.argtypes = [c_void_p]
_combase.WindowsDeleteString.restype = HRESULT
_combase.RoGetActivationFactory.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p)]
_combase.RoGetActivationFactory.restype = HRESULT


class HString:
    """An HSTRING owned by Python (deleted when closed)."""

    def __init__(self, text: str) -> None:
        self.handle = c_void_p()
        _combase.WindowsCreateString(text, len(text), byref(self.handle))

    def close(self) -> None:
        if self.handle:
            _combase.WindowsDeleteString(self.handle)
            self.handle = c_void_p()

    def __enter__(self) -> c_void_p:
        return self.handle

    def __exit__(self, *_exc) -> None:
        self.close()


def call(pointer, slot: int, argtypes: Sequence = (), *args, restype=HRESULT):
    """Call vtable ``slot`` of the COM object at ``pointer``. HRESULT failures raise OSError."""
    address = pointer.value if isinstance(pointer, c_void_p) else pointer
    if not address:
        raise OSError("null COM pointer")
    vtable = ctypes.cast(c_void_p(address), POINTER(POINTER(c_void_p)))[0]
    function = WINFUNCTYPE(restype, c_void_p, *argtypes)(vtable[slot])
    return function(address, *args)


def release(pointer) -> None:
    if pointer:
        call(pointer, 2, restype=c_ulong)


def add_ref(pointer) -> None:
    call(pointer, 1, restype=c_ulong)


def query(pointer, iid: uuid.UUID) -> c_void_p:
    out = c_void_p()
    call(pointer, 0, [POINTER(GUID), POINTER(c_void_p)], byref(GUID.of(iid)), byref(out))
    return out


def get_object(pointer, slot: int) -> c_void_p:
    """A getter that returns an interface pointer (``get_X(T** value)``)."""
    out = c_void_p()
    call(pointer, slot, [POINTER(c_void_p)], byref(out))
    return out


def activation_factory(class_name: str, iid: uuid.UUID) -> c_void_p:
    factory = c_void_p()
    with HString(class_name) as name:
        _combase.RoGetActivationFactory(name, byref(GUID.of(iid)), byref(factory))
    return factory


def wait_for(operation: c_void_p, timeout_s: float = 10.0) -> c_void_p:
    """Wait for an IAsyncOperation<T> (T an interface) by polling IAsyncInfo.Status, then
    return GetResults (slot 8). No completion delegate is needed."""
    info = query(operation, IID_IASYNCINFO)
    try:
        status = c_uint32()
        deadline = time.monotonic() + timeout_s
        while True:
            call(info, 7, [POINTER(c_uint32)], byref(status))  # get_Status
            if status.value != ASYNC_STARTED:
                break
            if time.monotonic() > deadline:
                call(info, 9)  # Cancel
                raise TimeoutError("the Windows operation didn't finish in time")
            time.sleep(0.005)
        if status.value != ASYNC_COMPLETED:
            code = ctypes.c_int32()
            call(info, 8, [POINTER(ctypes.c_int32)], byref(code))  # get_ErrorCode
            raise OSError(code.value, "the Windows operation failed")
        return get_object(operation, 8)  # GetResults
    finally:
        release(info)


QI = WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))
REF = WINFUNCTYPE(c_ulong, c_void_p)
GET_IIDS = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_ulong), POINTER(c_void_p))
GET_NAME = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))
GET_TRUST = WINFUNCTYPE(HRESULT, c_void_p, POINTER(ctypes.c_int))


def _guarded(fn: Callable) -> Callable:
    """A COM method body: drops ``this``; an exception becomes E_FAIL (ctypes would otherwise
    print it and return 0, which COM reads as success)."""

    def method(_this, *args) -> int:
        try:
            return fn(*args)
        except Exception:
            log.exception("COM callback failed")
            return E_FAIL

    return method


class _Instance(ctypes.Structure):
    _fields_ = [("vtable", c_void_p)]


class ComObject:
    """A COM object written in Python.

    ``methods`` are (WINFUNCTYPE prototype, Python callable) pairs in vtable order after IUnknown
    (and after IInspectable when ``inspectable``). The callables receive the arguments without
    ``this``. The object answers QueryInterface for IUnknown, IAgileObject (it may be called from
    any thread), IInspectable when ``inspectable``, and ``iids``. Python keeps it alive while COM
    holds a reference.
    """

    _alive: ClassVar[dict[int, ComObject]] = {}
    _lock = threading.Lock()

    def __init__(self, iids: Sequence[uuid.UUID], methods: Sequence[tuple[type, Callable]],
                 inspectable: bool = False) -> None:
        self.iids = {IID_IUNKNOWN, IID_IAGILEOBJECT, *iids}
        if inspectable:
            self.iids.add(IID_IINSPECTABLE)
        self._refs = 0
        slots = [QI(self._query), REF(self._add_ref), REF(self._release)]
        if inspectable:
            slots += [GET_IIDS(self._get_iids), GET_NAME(self._get_name),
                      GET_TRUST(self._get_trust)]
        slots += [prototype(_guarded(fn)) for prototype, fn in methods]
        self._slots = slots  # the callbacks must outlive the object
        self._vtable = (c_void_p * len(slots))(*[ctypes.cast(s, c_void_p) for s in slots])
        self._instance = _Instance(ctypes.cast(self._vtable, c_void_p))

    @property
    def pointer(self) -> c_void_p:
        return c_void_p(ctypes.addressof(self._instance))

    def new_reference(self) -> c_void_p:
        """A pointer with one reference taken for the caller (for an out parameter)."""
        self._add_ref(None)
        return self.pointer

    def _query(self, _this, riid, out) -> int:
        if not out:
            return E_POINTER
        if riid.contents.uuid() in self.iids:
            out[0] = ctypes.addressof(self._instance)
            self._add_ref(None)
            return S_OK
        out[0] = None
        return E_NOINTERFACE

    def _add_ref(self, _this) -> int:
        with self._lock:
            self._refs += 1
            ComObject._alive[id(self)] = self
            return self._refs

    def _release(self, _this) -> int:
        with self._lock:
            self._refs -= 1
            if self._refs <= 0:
                ComObject._alive.pop(id(self), None)
            return max(self._refs, 0)

    @staticmethod
    def _get_iids(_this, count, iids) -> int:
        count[0] = 0
        iids[0] = None
        return S_OK

    @staticmethod
    def _get_name(_this, name) -> int:
        name[0] = None  # an empty HSTRING
        return S_OK

    @staticmethod
    def _get_trust(_this, level) -> int:
        level[0] = 0  # BaseTrust
        return S_OK
