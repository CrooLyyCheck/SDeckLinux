"""Bounded registry access and backups for the recognized user-owned Wine prefix."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

Backup = Callable[[str, bytes], None]


def query_string(prefix: Path, key: str, name: str) -> str | None:
    selector = ["/ve"] if name == "default" else ["/v", name]
    code, output = reg(prefix, ["query", key, *selector])
    if code == 1:
        return None
    matches = re.findall(rb"^\s+[^\r\n]+?\s+REG_SZ\s+([^\r\n]+)\r?$", output, re.M)
    if code or len(matches) != 1:
        raise RuntimeError("Unsupported registry string; preserving it")
    try:
        value = matches[0].strip().decode("utf-8")
    except UnicodeError:
        raise RuntimeError("Unsupported registry string; preserving it") from None
    if name == "default" and value == "(value not set)":
        return None
    if not value or len(value) > 32760:
        raise RuntimeError("Unsupported registry string; preserving it")
    return value


def key_empty(prefix: Path, key: str) -> bool | None:
    code, output = reg(prefix, ["query", key, "/s"])
    if code == 1:
        return None
    if code:
        raise RuntimeError("Registry ownership query failed")
    try:
        lines = [line.strip() for line in output.decode("utf-8").splitlines() if line.strip()]
    except UnicodeError:
        raise RuntimeError("Unsupported registry contents; preserving them") from None
    full = key.replace("HKLM\\", "HKEY_LOCAL_MACHINE\\", 1)
    return not lines or (len(lines) == 1 and lines[0].casefold() == full.casefold())


def owned_prefix(prefix: Path, data: Path) -> bool:
    expected = data / "streamdeck-wine/prefix"
    marker = prefix / ".streamdeck-installer-owned"
    return (
        prefix == expected.resolve()
        and not expected.is_symlink()
        and marker.is_file()
        and not marker.is_symlink()
        and marker.stat().st_uid == os.getuid()
        and marker.stat().st_size <= 128
        and marker.read_bytes().strip() == f"streamdeck-wine installer v1:{os.getuid()}".encode()
    )


def snapshot(prefix: Path, backup: Backup) -> None:
    # Wine can flush registry state even during a query. Snapshot before invoking it.
    paths = [prefix / name for name in ("user.reg", "system.reg", "userdef.reg")]
    paths = [path for path in paths if path.exists() or path.is_symlink()]
    size = 0
    for path in paths:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError("Unsafe Wine registry file; native preference unchanged")
        size += info.st_size
    if not paths or size > 16 * 1024 * 1024 or shutil.disk_usage(prefix).free < size * 2 + 1048576:
        raise RuntimeError("Cannot make bounded registry backup; native preference unchanged")
    actual_size = 0
    for path in paths:
        with path.open("rb") as stream:
            content = stream.read(16 * 1024 * 1024 + 1)
        actual_size += len(content)
        if actual_size > 16 * 1024 * 1024:
            raise RuntimeError("Wine registry grew beyond backup limit")
        backup("native-renderer-" + path.name.replace(".", "-"), content)


def reg(prefix: Path, arguments: list[str]) -> tuple[int, bytes]:
    env = dict(os.environ, WINEPREFIX=str(prefix), WINEARCH="win64", WINEDEBUG="-all")
    env["WINEDLLOVERRIDES"] = "winemenubuilder.exe=d"
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(  # noqa: S603 - fixed Wine tool and application preference
                ["/usr/bin/wine", "reg", *arguments],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
            if output.tell() > 16384:
                raise RuntimeError("Oversized native preference reply")
            output.seek(0)
            return result.returncode, output.read(16384)
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("Native preference operation failed; outcome unconfirmed") from None
