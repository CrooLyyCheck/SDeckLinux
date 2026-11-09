"""Own one audited Stream Deck preference; never patch vendor files or profiles."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path

from ...windows.registry import owned_prefix, reg, snapshot

APP_VERSION = "7.6.1.23033"
APP_SHA256 = "d9487481d42e5c8d13254c813d5c80158fb58d77c37e8c89036549f3aae38618"
KEY = r"HKCU\Software\Elgato Systems GmbH\StreamDeck"
VALUE = "platform_render_surface_enabled"
MANAGED = "native_renderer"
ZERO = {"type": "REG_DWORD", "value": 0}
Save = Callable[[], None]
Backup = Callable[[str, bytes], None]


def supported(prefix: Path, data: Path) -> bool:
    if not owned_prefix(prefix, data):
        return False
    app = prefix / "drive_c/Program Files/Elgato/StreamDeck/StreamDeck.exe"
    if not app.is_file() or app.is_symlink() or app.stat().st_size > 64 * 1024 * 1024:
        return False
    return hashlib.sha256(app.read_bytes()).hexdigest() == APP_SHA256


def valid_value(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {"type", "value"}:
        return False
    if value["type"] == "REG_DWORD":
        return type(value["value"]) is int and value["value"] in (0, 1)
    return value["type"] == "REG_SZ" and value["value"] in (
        "true",
        "false",
        "True",
        "False",
        "0",
        "1",
    )


def query(prefix: Path) -> dict | None:
    code, output = reg(prefix, ["query", KEY, "/v", VALUE])
    if code == 1:
        return None
    match = re.search(rb"platform_render_surface_enabled\s+(REG_DWORD|REG_SZ)\s+([^\r\n]+)", output)
    if code != 0 or match is None:
        raise RuntimeError("Cannot read native renderer preference")
    try:
        kind = match[1].decode("ascii")
        text = match[2].strip().decode("ascii")
        value = {"type": kind, "value": int(text, 0) if kind == "REG_DWORD" else text}
    except (UnicodeError, ValueError):
        raise RuntimeError("Unsupported native renderer preference; preserving it") from None
    if not valid_value(value):
        raise RuntimeError("Unsupported native renderer preference; preserving it")
    return value


def write(prefix: Path, value: dict | None) -> None:
    if not valid_value(value):
        raise RuntimeError("Invalid native renderer value")
    arguments = (
        ["delete", KEY, "/v", VALUE, "/f"]
        if value is None
        else ["add", KEY, "/v", VALUE, "/t", value["type"], "/d", str(value["value"]), "/f"]
    )
    if reg(prefix, arguments)[0] != 0 or query(prefix) != value:
        raise RuntimeError("Native renderer write could not be verified")


def record_prefix(record: dict, data: Path) -> Path:
    if (
        not isinstance(record, dict)
        or set(record) != {"v", "prefix", "previous", "phase"}
        or type(record["v"]) is not int
        or record["v"] != 1
        or not isinstance(record["prefix"], str)
        or record["phase"] not in ("pending", "applied")
        or not valid_value(record["previous"])
    ):
        raise RuntimeError("Invalid native renderer ownership record")
    prefix = Path(record["prefix"])
    if not owned_prefix(prefix, data):
        raise RuntimeError("Original Wine prefix unavailable; renderer backup retained")
    return prefix


def restore(data: Path, manifest: dict, save: Save, backup: Backup) -> None:
    record = manifest.get(MANAGED)
    if record is None:
        return
    prefix = record_prefix(record, data)
    snapshot(prefix, backup)
    current = query(prefix)
    if current == ZERO and record["previous"] != ZERO:
        write(prefix, record["previous"])
    elif current not in (ZERO, record["previous"]):
        print("Preserved user-changed native renderer preference.")
    manifest.pop(MANAGED)
    save()


def synchronize(
    prefix: Path, data: Path, enabled: bool, manifest: dict, save: Save, backup: Backup
) -> None:
    if not enabled:
        restore(data, manifest, save, backup)
        return
    if not supported(prefix, data):
        return  # No native preference writes for untested application builds.
    record = manifest.get(MANAGED)
    if record is not None and record_prefix(record, data) != prefix:
        raise RuntimeError("Native renderer record belongs to another prefix")
    snapshot(prefix, backup)
    current = query(prefix)
    if record is None:
        record = {"v": 1, "prefix": str(prefix), "previous": current, "phase": "pending"}
        manifest[MANAGED] = record
        save()  # Journal the exact original value before a possible prefix write.
    elif record["phase"] == "applied":
        if current != ZERO:
            print("Preserved user-changed native renderer preference.")
        return
    elif current not in (ZERO, record["previous"]):
        raise RuntimeError("Native renderer changed during installation; preserving it")
    if current != ZERO:
        write(prefix, ZERO)
    record["phase"] = "applied"
    save()
