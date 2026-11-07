"""Read-only local observations without device identifiers or log payloads."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from . import __version__
from .config import Config
from .protocol import IO_TIMEOUT
from .wine import running_instances


def hardware() -> list[dict]:
    devices = []
    for path in sorted(Path("/sys/class/hidraw").glob("hidraw*")):
        try:
            data = (path / "device/uevent").read_text()
        except FileNotFoundError:
            continue
        if "HID_ID=0003:00000FD9:00000080" in data.upper():
            node = Path("/dev") / path.name
            devices.append(
                {
                    "model": "MK.2",
                    "node": str(node),
                    "read_write": os.access(node, os.R_OK | os.W_OK),
                }
            )
    return devices


async def mime_handler() -> str:
    proc = await asyncio.create_subprocess_exec(
        "/usr/bin/xdg-mime",
        "query",
        "default",
        "x-scheme-handler/streamdeck",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(IO_TIMEOUT):
            stdout, _ = await proc.communicate()
    except (TimeoutError, asyncio.CancelledError):
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        raise
    # Report only a known desktop ID, never arbitrary tool output.
    result = stdout.strip()
    if not result:
        return "missing"
    return "deckbridge" if result == b"io.deckbridge.UrlHandler.desktop" else "other"


async def diagnose(config: Config) -> dict:
    return {
        "deckbridge_version": __version__,
        "protocol_version": 1,
        "application_installed": config.executable.is_file(),
        "wine_available": config.wine.is_file() and os.access(config.wine, os.X_OK),
        "prefix_present": (config.prefix / "system.reg").is_file(),
        "running_instances": len(await asyncio.to_thread(running_instances, config)),
        "deep_links_enabled": config.deep_links,
        "streamdeck_handler": await mime_handler(),
        "hardware": await asyncio.to_thread(hardware),
        "desktop": "KDE" if os.environ.get("XDG_CURRENT_DESKTOP") == "KDE" else "other",
        "session": os.environ.get("XDG_SESSION_TYPE", "unknown"),
        "application_ack": False,
    }
