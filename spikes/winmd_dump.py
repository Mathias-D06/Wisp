"""Dev helper: print WinRT interfaces from Windows' own metadata (C:\\Windows\\System32\\
WinMetadata\\*.winmd, the files the SDK headers are generated from): each interface's GUID and its
methods in vtable order (after IInspectable's six slots). Used to check the raw COM calls in
``wisp/winapi/share.py`` (D-051). Needs ``pip install dnfile`` (dev only).

Run: .venv\\Scripts\\python spikes\\winmd_dump.py Windows.ApplicationModel IDataPackage ...
"""

from __future__ import annotations

import struct
import sys
import uuid
from pathlib import Path

import dnfile

WINMD = Path(r"C:\Windows\System32\WinMetadata")


def guid_of(pe, typedef_index: int) -> str | None:
    for attribute in pe.net.mdtables.CustomAttribute:
        parent = attribute.Parent
        if parent.table is None or parent.table.name != "TypeDef":
            continue
        if parent.row_index != typedef_index:
            continue
        ctor = attribute.Type.row
        owner = getattr(ctor, "Class", None)
        name = owner.row.TypeName if owner is not None and owner.row is not None else ""
        if name == "GuidAttribute":
            blob = attribute.Value.value if hasattr(attribute.Value, "value") else attribute.Value
            data = bytes(blob)[2:18]  # prolog 0x0001, then uint32, uint16, uint16, 8 bytes
            a, b, c = struct.unpack("<IHH", data[:8])
            return str(uuid.UUID(fields=(a, b, c, data[8], data[9],
                                         int.from_bytes(data[10:16], "big"))))
    return None


def dump(module: str, names: list[str]) -> None:
    pe = dnfile.dnPE(str(WINMD / f"{module}.winmd"))
    typedefs = pe.net.mdtables.TypeDef
    for index, row in enumerate(typedefs, start=1):
        if row.TypeName not in names:
            continue
        print(f"{row.TypeNamespace}.{row.TypeName}  {{{guid_of(pe, index)}}}")
        for slot, method in enumerate(row.MethodList, start=6):
            params = [str(param.row.Name) for param in method.row.ParamList]
            print(f"  {slot:2d} {method.row.Name}({', '.join(params)})")


if __name__ == "__main__":
    dump(sys.argv[1], sys.argv[2:])
