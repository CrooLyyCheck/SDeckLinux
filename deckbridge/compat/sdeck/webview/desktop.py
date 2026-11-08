"""Plan a reversible menu handoff without changing the original Wine launcher."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

LIMIT = 32768


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_owned(path: Path, limit: int = LIMIT) -> bytes | None:
    if not path.exists() and not path.is_symlink():
        return None
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > limit:
        raise RuntimeError("Unsafe or oversized menu integration file; preserving it")
    return path.read_bytes()


@dataclass(frozen=True)
class MenuPlan:
    path: Path
    before: bytes | None
    content: bytes | None
    mode: int
    record: dict | None


def previous(record: dict) -> tuple[bytes | None, int]:
    if not isinstance(record, dict) or set(record) != {"previous", "mode", "installed_sha256"}:
        raise RuntimeError("Invalid saved menu integration")
    text, mode, installed = record["previous"], record["mode"], record["installed_sha256"]
    if (
        (text is not None and (not isinstance(text, str) or len(text.encode()) > LIMIT))
        or type(mode) is not int
        or not 0 <= mode <= 0o777
        or not isinstance(installed, str)
        or len(installed) != 64
        or any(c not in "0123456789abcdef" for c in installed)
    ):
        raise RuntimeError("Invalid saved menu integration")
    return text.encode() if text is not None else None, mode


def prepare(
    data: Path, prefix: Path, command: str, original_command: str, record: dict | None
) -> MenuPlan | None:
    base = data / "streamdeck-wine"
    if prefix != (base / "prefix").resolve():
        if record is not None:
            raise RuntimeError("Saved menu belongs to a different Wine installation")
        return None
    marker = read_owned(prefix / ".streamdeck-installer-owned", 128)
    if marker is None or marker.strip() != f"streamdeck-wine installer v1:{os.getuid()}".encode():
        return None
    path = data / "applications/streamdeck-wine.desktop"
    current = read_owned(path)
    if record is not None:
        original, mode = previous(record)
        # An interrupted install can have saved its journal before the menu write.
        if current != original and (
            current is None or digest(current) != record["installed_sha256"]
        ):
            raise RuntimeError("Modified menu entry preserved; restore it or use --no-menu")
    else:
        original = current
        mode = path.stat().st_mode & 0o777 if current is not None else 0o600
        if current is not None:
            raw = read_owned(base / "managed-files.json", 262144)
            try:
                owned = json.loads(raw) if raw is not None else {}
            except (ValueError, UnicodeError):
                raise RuntimeError("Invalid Wine installer ownership manifest") from None
            if not isinstance(owned, dict) or owned.get(str(path)) != digest(current):
                raise RuntimeError(
                    "Custom menu entry preserved; use --no-menu to leave it unchanged"
                )
    try:
        text = (
            original.decode()
            if original is not None
            else (
                "[Desktop Entry]\nType=Application\nName=Stream Deck (Wine)\n"
                f"Exec={original_command}\nIcon=applications-multimedia\n"
                "Terminal=false\nCategories=Utility;\nStartupWMClass=streamdeck.exe\n"
            )
        )
    except UnicodeError:
        raise RuntimeError("Menu entry is not UTF-8; preserving it") from None
    lines = text.splitlines(keepends=True)
    entries = [i for i, line in enumerate(lines) if line.startswith("Exec=")]
    if len(entries) != 1 or lines[entries[0]].strip() not in {
        "Exec=" + original_command,
        "Exec=" + original_command + " --menu",
    }:
        raise RuntimeError("Unexpected original menu command; preserving it")
    lines[entries[0]] = f"Exec={command}\n"
    content = "".join(lines).encode()
    saved = {
        "previous": original.decode() if original is not None else None,
        "mode": mode,
        "installed_sha256": digest(content),
    }
    return MenuPlan(path, current, content, mode, saved)


def restore(data: Path, record: dict) -> MenuPlan | None:
    original, mode = previous(record)
    path = data / "applications/streamdeck-wine.desktop"
    try:
        current = read_owned(path)
    except RuntimeError:
        return None  # A user's symlink or other replacement is never followed.
    if current == original or (
        current is not None and digest(current) == record["installed_sha256"]
    ):
        return MenuPlan(path, current, original, mode, None)
    return None  # Preserve a user's replacement or deletion.
