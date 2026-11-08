"""Private, explicit, versioned configuration. No implicit Wine prefix."""

from __future__ import annotations

import os
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import BridgeError


def default_config() -> Path:
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "deckbridge/config.toml"
    )


def socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise BridgeError("runtime_dir_missing")
    root = Path(runtime)
    info = root.lstat()
    if (
        not root.is_absolute()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise BridgeError("runtime_dir_unsafe")
    return root / "deckbridge/control.sock"


@dataclass(frozen=True)
class AudioConfig:
    enabled: bool = False
    allow_write: bool = False
    allowed_apps: tuple[str, ...] = ()
    allow_system_write: bool = False


@dataclass(frozen=True)
class Config:
    prefix: Path
    executable: Path
    wine: Path
    deep_links: bool
    applications: dict[str, tuple[str, ...]]
    urls: dict[str, str]
    audio: AudioConfig = field(default_factory=AudioConfig)
    volume_controller: bool = False
    volume_controller_display: str = "icons"
    volume_controller_hide_events: bool = True
    streamdeck_webview_sandbox: bool = False
    streamdeck_webview_software: bool = True


def absolute(value: object) -> Path:
    if not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute():
        raise BridgeError("invalid_config_path")
    return Path(value)


def load(path: Path) -> Config:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise BridgeError("config_not_private")
    try:
        data = tomllib.loads(path.read_text())
    except (ValueError, UnicodeError):
        raise BridgeError("invalid_config") from None
    if (
        set(data) - {"version", "wine", "features", "applications", "urls", "audio", "compat"}
        or type(data.get("version")) is not int
        or data["version"] != 1
    ):
        raise BridgeError("unsupported_config")
    wine, features = data.get("wine", {}), data.get("features", {})
    if not isinstance(wine, dict) or set(wine) != {"prefix", "executable", "command"}:
        raise BridgeError("invalid_wine_config")
    if not isinstance(features, dict) or set(features) != {"deep_links"}:
        raise BridgeError("invalid_feature_config")
    if type(features["deep_links"]) is not bool:
        raise BridgeError("invalid_feature_config")
    prefix, exe, command = (absolute(wine[key]) for key in ("prefix", "executable", "command"))
    if not exe.is_relative_to(prefix / "drive_c"):
        raise BridgeError("executable_outside_prefix")
    applications, urls = data.get("applications", {}), data.get("urls", {})
    if not isinstance(applications, dict) or not isinstance(urls, dict):
        raise BridgeError("invalid_mappings")
    for name, argv in applications.items():
        if (
            not name
            or not isinstance(argv, list)
            or not argv
            or any(not isinstance(arg, str) or "\x00" in arg for arg in argv)
        ):
            raise BridgeError("invalid_application_mapping")
        absolute(argv[0])
        if argv[0].lower().endswith(".exe"):
            raise BridgeError("native_executable_required")
    from .uri import validate_url

    for name, url in urls.items():
        if not name:
            raise BridgeError("invalid_url_mapping")
        validate_url(url)
    audio, compat = data.get("audio", {}), data.get("compat", {})
    if (
        not isinstance(audio, dict)
        or set(audio) - {"enabled", "allow_write", "allowed_apps", "allow_system_write"}
        or not isinstance(compat, dict)
        or set(compat) - {"volume_controller", "sdeck"}
    ):
        raise BridgeError("invalid_audio_config")
    adapter = compat.get("volume_controller", {})
    if not isinstance(adapter, dict) or set(adapter) - {"enabled", "display", "hide_event_streams"}:
        raise BridgeError("invalid_audio_config")
    sdeck = compat.get("sdeck", {})
    if not isinstance(sdeck, dict) or set(sdeck) - {"webview"}:
        raise BridgeError("invalid_webview_config")
    webview = sdeck.get("webview", {})
    if not isinstance(webview, dict) or set(webview) - {"renderer_sandbox", "software_rendering"}:
        raise BridgeError("invalid_webview_config")
    webview_sandbox = webview.get("renderer_sandbox", False)
    webview_software = webview.get("software_rendering", True)
    if type(webview_sandbox) is not bool or type(webview_software) is not bool:
        raise BridgeError("invalid_webview_config")
    enabled = audio.get("enabled", False)
    write, adapter_enabled = audio.get("allow_write", False), adapter.get("enabled", False)
    allowed_apps = audio.get("allowed_apps", [])
    system_write = audio.get("allow_system_write", False)
    display = adapter.get("display", "icons")
    hide_events = adapter.get("hide_event_streams", True)
    if (
        any(
            type(v) is not bool
            for v in (enabled, write, adapter_enabled, system_write, hide_events)
        )
        or display not in ("icons", "text")
        or not isinstance(allowed_apps, list)
        or any(not isinstance(v, str) or not v or len(v) > 512 for v in allowed_apps)
        or (adapter_enabled and not enabled)
        or (write and not enabled)
        or (system_write and not enabled)
    ):
        raise BridgeError("invalid_audio_config")
    return Config(
        prefix,
        exe,
        command,
        features["deep_links"],
        {k: tuple(v) for k, v in applications.items()},
        urls,
        AudioConfig(enabled, write, tuple(allowed_apps), system_write),
        adapter_enabled,
        display,
        hide_events,
        webview_sandbox,
        webview_software,
    )
