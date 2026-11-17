#!/usr/bin/env python3
"""Prepare the pinned isolated compiler only for opted-in native compatibility."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".local/toolchains"
NAME = "llvm-mingw-20261104-ucrt-ubuntu-22.04-x86_64"
SIZE = 84_104_244
SHA256 = "919380403de87dca3c581c2053230cd298af5e891286628ba0613b7fed370926"
URL = f"https://github.com/mstorsjo/llvm-mingw/releases/download/20261104/{NAME}.tar.xz"
MAX_UNPACKED = 1536 * 1024 * 1024


def compiler_ready(folder: Path) -> bool:
    compiler = folder / "bin/x86_64-w64-mingw32-gcc"
    if not folder.exists():
        return False
    info = folder.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise RuntimeError("Existing native toolchain preserved: unsafe ownership")
    try:
        resolved = compiler.resolve(strict=True)
    except FileNotFoundError:
        raise RuntimeError("Existing incomplete native toolchain preserved") from None
    info = resolved.stat()
    if (
        not resolved.is_relative_to(folder.resolve())
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o022
        or not os.access(resolved, os.X_OK)
    ):
        raise RuntimeError("Existing native compiler preserved: unsafe ownership")
    return True


def prepare() -> None:
    if os.getuid() == 0 or platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError(
            "Native compiler preparation supports the audited Linux x64 desktop user"
        )
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = CACHE.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise RuntimeError("Unsafe native toolchain cache")
    destination = CACHE / NAME
    if compiler_ready(destination):
        return
    if shutil.disk_usage(CACHE).free < MAX_UNPACKED + SIZE + 64 * 1024 * 1024:
        raise RuntimeError("Insufficient space for the isolated native compiler")
    with tempfile.TemporaryDirectory(prefix=".prepare-native-", dir=CACHE) as directory:
        temporary = Path(directory)
        archive = temporary / "compiler.tar.xz"
        digest, count = hashlib.sha256(), 0
        deadline = time.monotonic() + 120
        print("Downloading the pinned isolated Windows compiler (84 MB)...", flush=True)
        with urllib.request.urlopen(URL, timeout=30) as response, archive.open("xb") as output:  # noqa: S310 - fixed HTTPS release URL
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > SIZE or time.monotonic() > deadline:
                    raise RuntimeError("Native compiler download exceeded its bound")
                digest.update(chunk)
                output.write(chunk)
        if count != SIZE or digest.hexdigest() != SHA256:
            raise RuntimeError("Native compiler release checksum mismatch")
        with tarfile.open(archive, "r:xz") as source:
            members, unpacked = [], 0
            for member in source:
                members.append(member)
                unpacked += max(0, member.size)
                if len(members) > 25000 or unpacked > MAX_UNPACKED:
                    raise RuntimeError("Native compiler archive exceeded its bound")
                path = PurePosixPath(member.name)
                if (
                    path.is_absolute()
                    or not path.parts
                    or path.parts[0] != NAME
                    or ".." in path.parts
                    or not (member.isfile() or member.isdir() or member.issym() or member.islnk())
                ):
                    raise RuntimeError("Unsafe native compiler archive")
            source.extractall(temporary, members=members, filter="data")  # noqa: S202 - hash verified and data-filtered
        if not compiler_ready(temporary / NAME):
            raise RuntimeError("Native compiler archive is incomplete")
        if destination.exists() or destination.is_symlink():
            raise RuntimeError("Native compiler destination changed; preserving it")
        os.rename(temporary / NAME, destination)
    print("Isolated native compiler prepared.", flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    try:
        prepare()
    except (OSError, RuntimeError, ValueError, tarfile.TarError):
        raise SystemExit("Could not prepare the pinned isolated native compiler") from None
