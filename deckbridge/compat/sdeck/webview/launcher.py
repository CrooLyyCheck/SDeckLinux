"""Launch through the existing audited installer with process-local preferences.

Renderer sandboxing stays enabled by default. Disabling it requires a deliberate
local preference or command-line flag; no registry, vendor or old launcher edits.
"""

from __future__ import annotations

import os
import shlex
import stat
from pathlib import Path

from ....config import Config
from ....protocol import BridgeError
from ....wine import running_instances


def launch_environment(
    sandbox: bool, source: dict[str, str], *, software: bool = False
) -> dict[str, str]:
    env = dict(source)
    try:
        flags = shlex.split(env.get("QTWEBENGINE_CHROMIUM_FLAGS", ""))
    except ValueError:
        raise BridgeError("webview_external_override") from None
    if sandbox:
        if any(flag.split("=", 1)[0] == "--no-sandbox" for flag in flags):
            raise BridgeError("webview_external_override")
        env.pop("QTWEBENGINE_DISABLE_SANDBOX", None)
    else:
        env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    if software and not any(flag.split("=", 1)[0] == "--disable-gpu" for flag in flags):
        existing = env.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
        env["QTWEBENGINE_CHROMIUM_FLAGS"] = (existing + " " if existing else "") + "--disable-gpu"
    return env


def launch(config: Config, *, no_sandbox: bool = False, software: bool = False) -> None:
    if running_instances(config):
        raise BridgeError("instance_already_running")
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    expected = data / "streamdeck-wine/prefix"
    launcher = Path.home() / ".local/bin/streamdeck-wine"
    marker = config.prefix / ".streamdeck-installer-owned"
    if (
        config.prefix.resolve() != expected.resolve()
        or not config.executable.is_file()
        or not marker.is_file()
        or marker.read_text().strip() != f"streamdeck-wine installer v1:{os.getuid()}"
    ):
        raise BridgeError("streamdeck_launcher_unavailable")
    info = launcher.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or not os.access(launcher, os.X_OK)
    ):
        raise BridgeError("streamdeck_launcher_unavailable")
    env = launch_environment(
        config.streamdeck_webview_sandbox and not no_sandbox,
        dict(os.environ),
        software=config.streamdeck_webview_software or software,
    )
    # Existing installer retains all Wine fixes and its original foreground lifecycle.
    os.execve(launcher, [str(launcher)], env)  # noqa: S606 - fixed owned launcher, no caller argv
