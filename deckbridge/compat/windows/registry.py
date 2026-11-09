"""Bounded registry access and backups for the recognized user-owned Wine prefix."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

Backup = Callable[[str, bytes], None]


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
