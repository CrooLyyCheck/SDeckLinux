"""Reversible Wine DirectWrite family fallback, independent of any plugin."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .registry import Backup, owned_prefix, reg, snapshot

KEY = r"HKCU\Software\Wine\Fonts\Replacements"
VALUE = "Arial"
FAMILY = "Liberation Sans"
MANAGED = "wine_font_fallback"


def query(prefix: Path) -> str | None:
    code, output = reg(prefix, ["query", KEY, "/v", VALUE])
    if code == 1:
        return None
    match = re.search(rb"^\s*Arial\s+REG_SZ\s+([^\r\n]+)", output, re.M)
    if code or not match:
        raise RuntimeError("Unsupported font alias; preserving it")
    try:
        value = match[1].strip().decode("utf-8")
    except UnicodeError:
        raise RuntimeError("Unsupported font alias; preserving it") from None
    if not value or len(value) > 255:
        raise RuntimeError("Unsupported font alias; preserving it")
    return value


def write(prefix: Path, value: str | None) -> None:
    args = (
        ["delete", KEY, "/v", VALUE, "/f"]
        if value is None
        else ["add", KEY, "/v", VALUE, "/t", "REG_SZ", "/d", value, "/f"]
    )
    if reg(prefix, args)[0] or query(prefix) != value:
        raise RuntimeError("Font fallback write could not be verified")


def restore(data: Path, manifest: dict, save, backup: Backup) -> None:
    record = manifest.get(MANAGED)
    if record is None:
        return
    if (
        not isinstance(record, dict)
        or set(record) != {"prefix", "previous", "phase"}
        or not isinstance(record["prefix"], str)
        or record["previous"] not in (None, FAMILY)
        or record["phase"] not in ("pending", "applied")
    ):
        raise RuntimeError("Invalid font fallback ownership record")
    prefix = Path(record["prefix"])
    if not owned_prefix(prefix, data):
        raise RuntimeError("Original font fallback prefix unavailable")
    snapshot(prefix, backup)
    current = query(prefix)
    if current == FAMILY and record["previous"] is None:
        write(prefix, None)
    manifest.pop(MANAGED)
    save()


def synchronize(prefix: Path, data: Path, enabled: bool, manifest: dict, save, backup: Backup):
    if not enabled:
        restore(data, manifest, save, backup)
        return
    if not owned_prefix(prefix, data):
        return
    # Use an already installed font; never download or redistribute font files.
    result = subprocess.run(  # noqa: S603 - fixed read-only fontconfig query
        ["/usr/bin/fc-match", "Liberation Sans", "--format=%{family}"],
        capture_output=True,
        check=False,
        timeout=5,
    )
    if result.returncode or FAMILY.encode() not in result.stdout.strip().split(b","):
        raise RuntimeError("Liberation Sans unavailable; font fallback unchanged")
    record = manifest.get(MANAGED)
    if record is not None:
        if (
            not isinstance(record, dict)
            or set(record) != {"prefix", "previous", "phase"}
            or record["prefix"] != str(prefix)
            or record["previous"] not in (None, FAMILY)
            or record["phase"] not in ("pending", "applied")
        ):
            raise RuntimeError("Invalid font fallback ownership record")
    snapshot(prefix, backup)
    current = query(prefix)
    if record is None:
        if current not in (None, FAMILY):
            print("Preserved existing Arial font alias.")
            return
        record = {"prefix": str(prefix), "previous": current, "phase": "pending"}
        manifest[MANAGED] = record
        save()
    elif record["phase"] == "applied":
        return  # Preserve subsequent user changes on ordinary updates.
    elif current not in (record["previous"], FAMILY):
        raise RuntimeError("Font alias changed during installation; preserving it")
    if current != FAMILY:
        write(prefix, FAMILY)
    record["phase"] = "applied"
    save()
