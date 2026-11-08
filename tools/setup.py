#!/usr/bin/env python3
"""Small KDE/terminal installer: choose a mode, then apply all host integration."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESSAGE = (
    "Install SDeckLinux for your existing Stream Deck under Wine.\n\n"
    "The plugin settings fix uses software rendering and DISABLES the WebEngine "
    "renderer sandbox only inside Stream Deck. Plugin pages run with your account's "
    "permissions. Choose this mode only if you accept the reduced isolation.\n\n"
    "Keeping the sandbox may leave plugin settings blank on the tested Wine setup.\n"
    "The installer sets up the menu icon automatically and keeps your profiles."
)


def choose_mode(dialog: str | None) -> str | None:
    if dialog:
        result = subprocess.run(  # noqa: S603 - fixed dialog, buttons and text
            [
                dialog,
                "--title",
                "SDeckLinux setup",
                "--yes-label",
                "Install with plugin settings fix",
                "--no-label",
                "Install with sandbox",
                "--cancel-label",
                "Cancel",
                "--yesnocancel",
                MESSAGE,
            ],
            check=False,
            timeout=1800,
        )  # noqa: S603 - fixed dialog and fixed text, no external commands
        return {0: "compatible", 1: "sandboxed"}.get(result.returncode)
    if not sys.stdin.isatty():
        raise RuntimeError("Run ./install.sh from a terminal, or use KDE with kdialog available")
    print(MESSAGE)
    print("1: Install with plugin settings fix\n2: Install with sandbox\nEnter: Cancel")
    return {"1": "compatible", "2": "sandboxed"}.get(input("Choice: ").strip())


def notify(dialog: str | None, text: str, *, error: bool = False) -> None:
    print(text)
    if dialog:
        subprocess.run(  # noqa: S603 - fixed dialog and status text
            [dialog, "--title", "SDeckLinux setup", "--error" if error else "--msgbox", text],
            check=False,
            timeout=1800,
        )  # noqa: S603 - fixed dialog, fixed status text


def setup() -> int:
    if os.getuid() == 0 or sys.version_info < (3, 11):
        print("Use Python 3.11 or newer as your desktop user; do not run as root.", file=sys.stderr)
        return 1
    dialog = (
        shutil.which("kdialog")
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        else None
    )
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
        mode = choose_mode(dialog)
        if mode is None:
            print("Installation cancelled; no changes made.")
            return 0
        print("Preparing isolated dependencies and applying SDeckLinux integration...")
        subprocess.run(["make", "setup"], cwd=ROOT, check=True, timeout=600)  # noqa: S603,S607
        subprocess.run(  # noqa: S603 - fixed repository installer and selected mode
            [
                sys.executable,
                str(ROOT / "tools/install.py"),
                "--prefix",
                str(prefix),
                "--webview-mode",
                mode,
                "--apply",
            ],
            cwd=ROOT,
            check=True,
            timeout=180,
        )  # noqa: S603 - fixed repository installer, explicit known prefix and mode
        notify(
            dialog,
            "SDeckLinux installed. Quit any running Stream Deck, then open "
            "Stream Deck (Wine) from your application menu.",
        )
        return 0
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        message = (
            str(exc)
            if isinstance(exc, RuntimeError)
            else "Installation could not finish. See terminal output; "
            "existing profiles are preserved."
        )
        notify(dialog, message, error=True)
        return 1


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    raise SystemExit(setup())
