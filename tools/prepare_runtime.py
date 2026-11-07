#!/usr/bin/env python3
"""Prepare a hash-verified, portable pure-Python dependency tree for installation."""

import hashlib
import io
import stat
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = (
    "https://files.pythonhosted.org/packages/eb/27/"
    "9db924cb0dbf22eade78d98fbae77790f9bf6bc729e6ab29aef9d68e4156/"
    "websockets-17.4-py3-none-any.whl"
)
SHA256 = "c6bd2c9781915592b209160d0f017d4c7c82ad53075e6b0c24d2a89299e7f9e9"


def prepare() -> None:
    target = ROOT / ".local/runtime-dependencies"
    cache = ROOT / ".local/websockets-17.4.whl"
    if cache.is_symlink() or target.is_symlink():
        raise RuntimeError("Dependency cache symlink refused")
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        data = cache.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=20) as response:  # noqa: S310 - fixed HTTPS URL
            data = response.read(1024 * 1024)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("Dependency wheel SHA256 mismatch")
    if not cache.exists():
        cache.write_bytes(data)
    with zipfile.ZipFile(io.BytesIO(data)) as wheel:
        for entry in wheel.infolist():
            name = Path(entry.filename)
            if (
                name.is_absolute()
                or ".." in name.parts
                or name.parts[0] not in {"websockets", "websockets-17.4.dist-info"}
                or stat.S_ISLNK(entry.external_attr >> 16)
            ):
                raise RuntimeError("Unexpected wheel member")
            if entry.is_dir():
                continue
            destination = target / name
            content = wheel.read(entry)
            if destination.is_symlink() or (
                destination.exists() and destination.read_bytes() != content
            ):
                raise RuntimeError("Modified generated dependency preserved: " + str(destination))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                destination.write_bytes(content)
    print("Verified portable websockets 17.4 runtime dependency.")


if __name__ == "__main__":
    prepare()
