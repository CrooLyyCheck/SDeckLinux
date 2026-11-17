"""Reversible COM activation inside one owned Wine prefix, not the Linux system.

Wine 11.20's combase reads Classes from that prefix's Machine hive directly;
HKCU registration is ineffective. Preserve the exact stock registration and
delegate to the system32 Wine factory from our separate library.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..registry import Backup, owned_prefix, reg, snapshot

KEY = r"HKLM\Software\Classes\CLSID\{BCDE0395-E52F-467C-8E3D-C4579291692E}\InprocServer32"
MANAGED = "windows_core_audio"
RELATIVE_LIBRARY = Path("deckbridge/runtime/native/deckbridge-core-audio.dll")
NATIVE_DEFAULT = r"C:\windows\system32\mmdevapi.dll"


def library_path(data: Path) -> Path:
    return data / RELATIVE_LIBRARY


def desired(data: Path) -> dict[str, str]:
    return {"default": "Z:" + str(library_path(data)), "ThreadingModel": "Both"}


def native_registration(values) -> bool:
    return (
        isinstance(values, dict)
        and set(values) == {"default", "ThreadingModel"}
        and isinstance(values["default"], str)
        and values["default"].replace("/", "\\").casefold()
        in {NATIVE_DEFAULT.casefold(), "mmdevapi.dll"}
        and values["ThreadingModel"] == "Both"
    )


def query(prefix: Path, name: str) -> str | None:
    selector = ["/ve"] if name == "default" else ["/v", name]
    code, output = reg(prefix, ["query", KEY, *selector])
    if code == 1:
        return None
    matches = re.findall(rb"^\s+[^\r\n]+?\s+REG_SZ\s+([^\r\n]+)\r?$", output, re.M)
    if code or len(matches) != 1:
        raise RuntimeError("Unsupported Core Audio registration; preserving it")
    try:
        value = matches[0].strip().decode("utf-8")
    except UnicodeError:
        raise RuntimeError("Unsupported Core Audio registration; preserving it") from None
    if not value or len(value) > 32760:
        raise RuntimeError("Unsupported Core Audio registration; preserving it")
    if name == "default" and value == "(value not set)":
        return None  # Wine reg /ve reports an unset default with exit status zero.
    return value


def write(prefix: Path, name: str, value: str) -> None:
    selector = ["/ve"] if name == "default" else ["/v", name]
    args = ["add", KEY, *selector, "/t", "REG_SZ", "/d", value, "/f"]
    if reg(prefix, args)[0] or query(prefix, name) != value:
        raise RuntimeError("Core Audio registration write could not be verified")


def validate(record, prefix: Path) -> None:
    if (
        not isinstance(record, dict)
        or set(record) != {"version", "prefix", "key", "phase", "previous"}
        or record["version"] != 1
        or record["prefix"] != str(prefix)
        or record["key"] != KEY
        or record["phase"] not in ("pending", "applied")
        or not native_registration(record["previous"])
    ):
        raise RuntimeError("Invalid Core Audio activation ownership")


def restore(data: Path, manifest: dict, save, backup: Backup) -> None:
    record = manifest.get(MANAGED)
    if record is None:
        return
    if not isinstance(record, dict) or not isinstance(record.get("prefix"), str):
        raise RuntimeError("Invalid Core Audio activation ownership")
    prefix = Path(record["prefix"])
    validate(record, prefix)
    if not owned_prefix(prefix, data):
        raise RuntimeError("Original Core Audio prefix unavailable")
    snapshot(prefix, backup)
    values = {name: query(prefix, name) for name in desired(data)}
    if values["default"] not in (record["previous"]["default"], desired(data)["default"]):
        # Preserve binaries too: a user-modified registration might still refer to them.
        for path in (library_path(data), library_path(data).with_suffix(".token")):
            manifest.get("files", {}).pop(str(path), None)
        print("Preserved user-modified Core Audio registration and native files.")
    for name, value in desired(data).items():
        if values[name] == value and value != record["previous"][name]:
            write(prefix, name, record["previous"][name])
    manifest.pop(MANAGED)
    save()


def synchronize(prefix: Path, data: Path, enabled: bool, manifest: dict, save, backup: Backup):
    if not enabled:
        restore(data, manifest, save, backup)
        return
    if not owned_prefix(prefix, data):
        raise RuntimeError("Unsupported Core Audio prefix")
    record = manifest.get(MANAGED)
    if record is not None:
        validate(record, prefix)
    snapshot(prefix, backup)
    current = {name: query(prefix, name) for name in desired(data)}
    if record is None:
        if not native_registration(current):
            raise RuntimeError("Existing Core Audio registration preserved")
        record = {
            "version": 1,
            "prefix": str(prefix),
            "key": KEY,
            "phase": "pending",
            "previous": current,
        }
        manifest[MANAGED] = record
        save()
    elif record["phase"] == "applied":
        if current == desired(data):
            return
        if current != record["previous"]:
            print("Preserved user-modified Core Audio registration.")
            return
        # Wine can restore its stock factory during prefix maintenance. The
        # enabled preference authorizes this exact known-stock transition only.
        record["phase"] = "pending"
        save()
    for name, value in desired(data).items():
        if current[name] not in (record["previous"][name], value):
            raise RuntimeError("Core Audio activation changed during install; preserving it")
    for name, value in desired(data).items():
        if current[name] != value:
            write(prefix, name, value)
    record["phase"] = "applied"
    save()
