"""Private, explicit, versioned configuration. No implicit Wine prefix."""

from __future__ import annotations

import os
import stat
import tomllib
from dataclasses import dataclass
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
class Config:
    prefix: Path
    executable: Path
    wine: Path
    deep_links: bool
    applications: dict[str, tuple[str, ...]]
    urls: dict[str, str]


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
        set(data) - {"version", "wine", "features", "applications", "urls"}
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
    return Config(
        prefix,
        exe,
        command,
        features["deep_links"],
        {k: tuple(v) for k, v in applications.items()},
        urls,
    )
