#!/usr/bin/env python3
"""Standard installation: detect the Wine app and install SDeckLinux with its defaults."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def setup(mode: str | None = None) -> int:
    if os.getuid() == 0 or sys.version_info < (3, 11):
        print("Use Python 3.11 or newer as your desktop user; do not run as root.", file=sys.stderr)
        return 1
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    prefix = data / "streamdeck-wine/prefix"
    marker = prefix / ".streamdeck-installer-owned"
    launcher = Path.home() / ".local/bin/streamdeck-wine"
    try:
        if (
            not marker.is_file()
            or marker.is_symlink()
            or marker.read_text().strip() != f"streamdeck-wine installer v1:{os.getuid()}"
            or not (prefix / "drive_c/Program Files/Elgato/StreamDeck/StreamDeck.exe").is_file()
            or not launcher.is_file()
            or not stat.S_ISREG(launcher.lstat().st_mode)
            or launcher.stat().st_uid != os.getuid()
            or not os.access(launcher, os.X_OK)
        ):
            raise RuntimeError(
                "Install the official Stream Deck with the supported streamdeck-wine "
                "installer first. See docs/USAGE.md."
            )
        print("Installing SDeckLinux, including menu integration and built-in Wine fixes...")
        print("The default Wine mode uses software rendering with the renderer sandbox off.")
        subprocess.run(["make", "setup"], cwd=ROOT, check=True, timeout=600)  # noqa: S603,S607
        command = [
            sys.executable,
            str(ROOT / "tools/install.py"),
            "--prefix",
            str(prefix),
            "--apply",
        ]
        if mode is not None:
            command.extend(["--webview-mode", mode])
        subprocess.run(command, cwd=ROOT, check=True, timeout=180)  # noqa: S603 - fixed installer
        print(
            "Installed. Quit any running Stream Deck, then open Stream Deck (Wine) from the menu."
        )
        return 0
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        message = (
            str(exc)
            if isinstance(exc, RuntimeError)
            else "Installation could not finish. See terminal output."
        )
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--webview-mode",
        choices=("compatible", "sandboxed"),
        help="Optional override; ordinary installation needs no mode selection",
    )
    raise SystemExit(setup(parser.parse_args().webview_mode))
