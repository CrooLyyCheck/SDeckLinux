#!/usr/bin/env python3
"""Idempotent user-only installation alongside the existing Wine installer.

Does not install Stream Deck, edit its prefix, or adopt existing unowned files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = "io.deckbridge.UrlHandler.desktop"
MIME = "x-scheme-handler/streamdeck"
sys.path.insert(0, str(ROOT))

from deckbridge import portal  # noqa: E402 - standalone repository tool
from deckbridge.config import load  # noqa: E402
from deckbridge.protocol import BridgeError  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic(path: Path, data: bytes, mode: int = 0o600) -> None:
    if path.is_symlink():
        raise RuntimeError("Refusing destination symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".deckbridge-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def default_line(text: str) -> str | None:
    section, matches = "", []
    for line in text.splitlines(keepends=True):
        if line.strip().startswith("["):
            section = line.strip()
        if section == "[Default Applications]" and line.startswith(MIME + "="):
            matches.append(line)
    if len(matches) > 1:
        raise RuntimeError("Ambiguous streamdeck MIME configuration; preserving it")
    return matches[0] if matches else None


def replace_default(text: str, replacement: str | None) -> str:
    old = default_line(text)
    lines = text.splitlines(keepends=True)
    if old is not None:
        section = ""
        for index, line in enumerate(lines):
            if line.strip().startswith("["):
                section = line.strip()
            if section == "[Default Applications]" and line == old:
                lines[index] = replacement or ""
                return "".join(lines)
    if replacement is None:
        return text
    headers = [i for i, line in enumerate(lines) if line.strip() == "[Default Applications]"]
    if len(headers) > 1:
        raise RuntimeError("Duplicate MIME default sections; preserving them")
    if headers:
        index = headers[0]
        lines[index] = lines[index].rstrip("\r\n") + "\n"
        lines.insert(index + 1, replacement)
        return "".join(lines)
    return (
        text
        + ("\n" if text and not text.endswith("\n") else "")
        + "[Default Applications]\n"
        + replacement
    )


def quote_exec(value: str) -> str:
    # Desktop Entry Exec quoting, also usable for these absolute systemd paths.
    return '"' + re.sub(r'([\\"`$])', r"\\\1", value.replace("%", "%%")) + '"'


def run(argv: list[str]) -> None:
    subprocess.run(argv, check=True, timeout=15)  # noqa: S603 - fixed tools/arguments


def install(args: argparse.Namespace) -> None:
    os.umask(0o077)
    if os.getuid() == 0:
        raise RuntimeError("Run as the desktop user, never root")
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    state = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "deckbridge"
    manifest_path = state / "install.json"
    if manifest_path.is_symlink():
        raise RuntimeError("Manifest symlink refused")
    manifest = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else {"version": 1, "files": {}}
    )
    if manifest.get("version") != 1:
        raise RuntimeError("Unknown installation manifest")
    permissions = portal.read_permissions()
    portal_changes = portal.legacy_choices(permissions)
    launcher = home / ".local/bin/deckbridge"
    runtime = data / "deckbridge/runtime"
    service = config / "systemd/user/deckbridge.service"
    desktop = data / "applications" / DESKTOP
    mime = config / "mimeapps.list"
    if mime.is_symlink():
        raise RuntimeError("MIME configuration symlink refused")
    if args.deactivate:
        print(
            "Stop/disable DeckBridge, restore its MIME key, remove unchanged owned files; "
            "retain config/backups."
        )
        if not args.apply:
            return
        if not manifest_path.exists():
            raise RuntimeError("No managed installation to deactivate")
        if (
            not manifest["files"]
            and "previous_mime_line" not in manifest
            and not manifest.get("portal_choices")
        ):
            print("Already deactivated; private config and backups retained.")
            return
        run(["/usr/bin/systemctl", "--user", "disable", "--now", "deckbridge.service"])
        for app, entry in manifest.get("portal_choices", {}).items():
            current = permissions.get(app, [])
            if current and current[0] == portal.HANDLER:
                portal.set_permission(app, entry["previous"])
            else:
                print("Preserved user-changed portal application choice.")
        manifest.pop("portal_choices", None)
        text = mime.read_text() if mime.exists() else ""
        line = default_line(text)
        if line is not None and line.strip() == MIME + "=" + DESKTOP + ";":
            atomic(mime, replace_default(text, manifest.get("previous_mime_line")).encode())
        for name, expected in list(manifest["files"].items()):
            path = Path(name)
            allowed = path.is_relative_to(runtime) or path in {launcher, service, desktop}
            if not allowed:
                raise RuntimeError("Manifest contains unexpected destination")
            if path.is_symlink() or (path.exists() and digest(path.read_bytes()) != expected):
                print("Preserved modified managed file:", path)
                continue
            path.unlink(missing_ok=True)
            del manifest["files"][name]
        manifest.pop("previous_mime_line", None)
        atomic(manifest_path, json.dumps(manifest, indent=2).encode())
        run(["/usr/bin/systemctl", "--user", "daemon-reload"])
        run(["/usr/bin/update-desktop-database", str(data / "applications")])
        return
    if args.prefix is None:
        raise RuntimeError("Specify the audited --prefix explicitly")
    prefix = args.prefix.resolve(strict=True)
    executable = prefix / "drive_c/Program Files/Elgato/StreamDeck/StreamDeck.exe"
    if not executable.is_file() or not (prefix / "system.reg").is_file():
        raise RuntimeError("Expected existing Stream Deck installation not found")
    files = {
        runtime / "deckbridge" / p.name: (p.read_bytes(), 0o600)
        for p in sorted((ROOT / "deckbridge").glob("*.py"))
    }
    launcher_text = (
        "#!/usr/bin/python3\nimport sys\nsys.dont_write_bytecode = True\n"
        f"sys.path.insert(0, {str(runtime)!r})\n"
        "from deckbridge.__main__ import entrypoint\n"
        "raise SystemExit(entrypoint())\n"
    )
    files[launcher] = (launcher_text.encode(), 0o700)
    service_text = f"""[Unit]
Description=DeckBridge local Linux capability daemon
After=graphical-session.target
PartOf=graphical-session.target
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=exec
ExecStart={quote_exec(str(launcher))} serve
UMask=0077
NoNewPrivileges=yes
LimitCORE=0
Restart=on-failure
RestartSec=2
TimeoutStopSec=5

[Install]
WantedBy=default.target
"""
    files[service] = (service_text.encode(), 0o600)
    files[desktop] = (
        (
            "[Desktop Entry]\nType=Application\nName=DeckBridge Stream Deck URL Handler\n"
            f"Exec={quote_exec(str(launcher))} handle-uri %u\n"
            f"NoDisplay=true\nTerminal=false\nMimeType={MIME};\n"
        ).encode(),
        0o600,
    )
    for path in files:
        if path.is_symlink() or (
            path.exists() and digest(path.read_bytes()) not in {manifest["files"].get(str(path))}
        ):
            raise RuntimeError(f"Existing unowned/modified file preserved: {path}")
    config_path = config / "deckbridge/config.toml"
    # JSON string quoting is a subset of TOML basic-string quoting for these paths.
    cfg = f"""version = 1
[wine]
prefix = {json.dumps(str(prefix))}
executable = {json.dumps(str(executable))}
command = "/usr/bin/wine"
[features]
deep_links = true
[applications]
[urls]
"""
    print(
        f"Install/update {len(files)} owned files; private config {config_path}; "
        f"streamdeck:// -> {DESKTOP}."
    )
    print("Existing Wine prefix, installer, profiles and plugins are not modified.")
    print(
        f"Remembered legacy portal choices to update: {len(portal_changes)}; "
        "counters/consent retained."
    )
    if not args.apply:
        return
    for command in (
        "/usr/bin/systemctl",
        "/usr/bin/xdg-mime",
        "/usr/bin/desktop-file-validate",
        "/usr/bin/update-desktop-database",
        "/usr/bin/systemd-analyze",
        "/usr/bin/busctl",
    ):
        if not os.access(command, os.X_OK):
            raise RuntimeError("Missing required integration tool: " + command)
    # Validate generated configuration before changing user integration files.
    with tempfile.TemporaryDirectory(prefix="deckbridge-validate-") as folder:
        temporary = Path(folder)
        (temporary / "deckbridge.service").write_bytes(files[service][0])
        (temporary / DESKTOP).write_bytes(files[desktop][0])
        run(["/usr/bin/desktop-file-validate", str(temporary / DESKTOP)])
        # ExecStart must already exist for systemd-analyze; validate after managed copy.
    if config_path.is_symlink():
        raise RuntimeError("Config symlink refused")
    if not config_path.exists():
        atomic(config_path, cfg.encode())
    if load(config_path).prefix != prefix:
        raise RuntimeError("Existing config names a different prefix; preserving it")
    text = mime.read_text() if mime.exists() else ""
    if "previous_mime_line" not in manifest:
        manifest["previous_mime_line"] = default_line(text)
        atomic(state / "backups/mimeapps-before-deckbridge", text.encode())
        atomic(manifest_path, json.dumps(manifest, indent=2).encode())
    for path, (content, mode) in files.items():
        atomic(path, content, mode)
        manifest["files"][str(path)] = digest(content)
        atomic(manifest_path, json.dumps(manifest, indent=2).encode())
    run(["/usr/bin/systemd-analyze", "--user", "verify", str(service)])
    atomic(mime, replace_default(text, MIME + "=" + DESKTOP + ";\n").encode())
    run(["/usr/bin/update-desktop-database", str(data / "applications")])
    run(["/usr/bin/systemctl", "--user", "daemon-reload"])
    run(["/usr/bin/systemctl", "--user", "enable", "deckbridge.service"])
    run(["/usr/bin/systemctl", "--user", "restart", "deckbridge.service"])
    for app, replacement in portal_changes.items():
        if portal.read_permissions().get(app) != permissions[app]:
            raise BridgeError("portal_choice_changed")
        saved = manifest.setdefault("portal_choices", {})
        if app in saved:
            raise BridgeError("portal_choice_changed")  # User changed a previously managed choice.
        saved[app] = {"previous": permissions[app], "installed": replacement}
        atomic(manifest_path, json.dumps(manifest, indent=2).encode())
        portal.set_permission(app, replacement)
    print(
        "Installed. Run: deckbridge diagnose. "
        "After config changes: systemctl --user restart deckbridge."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path)
    parser.add_argument("--apply", action="store_true", help="Apply changes; default is dry-run")
    parser.add_argument("--deactivate", action="store_true")
    try:
        install(parser.parse_args())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, BridgeError) as error:
        print(f"Installation stopped: {error}", file=sys.stderr)
        sys.exit(1)
