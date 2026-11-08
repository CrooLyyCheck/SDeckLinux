#!/usr/bin/env python3
"""Idempotent user-only installation alongside the existing Wine installer.

Does not install Stream Deck or edit its prefix. The recognized installer's menu
entry can be handed over with a verified backup and restored on deactivation.
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

from deckbridge.compat.sdeck.oauth import portal  # noqa: E402 - standalone repository tool
from deckbridge.compat.sdeck.webview import desktop as menu  # noqa: E402
from deckbridge.compat.sdeck.webview.preferences import with_mode  # noqa: E402
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


def private_backup(state: Path, kind: str, content: bytes) -> None:
    path = state / "backups" / (kind + "-" + digest(content))
    if path.is_symlink() or (path.exists() and path.read_bytes() != content):
        raise RuntimeError("Existing integration backup is modified; preserving it")
    if not path.exists():
        atomic(path, content)
    if path.read_bytes() != content:
        raise RuntimeError("Integration backup verification failed")


def apply_menu(plan: menu.MenuPlan, manifest: dict, state: Path) -> None:
    if menu.read_owned(plan.path) != plan.before:
        raise RuntimeError("Menu entry changed during installation; preserving it")
    if plan.record is not None:
        original, _ = menu.previous(plan.record)
        if original is not None:
            private_backup(state, "streamdeck-menu", original)
        manifest["menu_entry"] = plan.record
        atomic(state / "install.json", json.dumps(manifest, indent=2).encode())
    if plan.content is None:
        plan.path.unlink(missing_ok=True)
    else:
        atomic(plan.path, plan.content, plan.mode)
    if plan.record is None:
        manifest.pop("menu_entry", None)
        atomic(state / "install.json", json.dumps(manifest, indent=2).encode())


def refresh_desktop(data: Path) -> None:
    run(["/usr/bin/update-desktop-database", str(data / "applications")])
    if os.access("/usr/bin/kbuildsycoca6", os.X_OK):
        run(["/usr/bin/kbuildsycoca6", "--noincremental"])


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
            and not manifest.get("menu_entry")
        ):
            print("Already deactivated; private config and backups retained.")
            return
        run(["/usr/bin/systemctl", "--user", "disable", "--now", "deckbridge.service"])
        if manifest.get("menu_entry"):
            restore_menu = menu.restore(data, manifest["menu_entry"])
            if restore_menu is not None:
                apply_menu(restore_menu, manifest, state)
            else:
                print("Preserved user-changed Stream Deck menu entry.")
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
        refresh_desktop(data)
        return
    if args.prefix is None:
        raise RuntimeError("Specify the audited --prefix explicitly")
    prefix = args.prefix.resolve(strict=True)
    executable = prefix / "drive_c/Program Files/Elgato/StreamDeck/StreamDeck.exe"
    if not executable.is_file() or not (prefix / "system.reg").is_file():
        raise RuntimeError("Expected existing Stream Deck installation not found")
    files = {
        runtime / "deckbridge" / p.relative_to(ROOT / "deckbridge"): (p.read_bytes(), 0o600)
        for p in sorted((ROOT / "deckbridge").rglob("*"))
        if p.is_file() and p.suffix in {".py", ".json"}
    }
    dependencies = ROOT / ".local/runtime-dependencies"
    if not (dependencies / "websockets/__init__.py").is_file():
        raise RuntimeError("Run make setup to prepare the hash-verified runtime dependency")
    for path in sorted(dependencies.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            files[runtime / "dependencies" / path.relative_to(dependencies)] = (
                path.read_bytes(),
                0o600,
            )
    launcher_text = (
        "#!/usr/bin/python3\nimport sys\nsys.dont_write_bytecode = True\n"
        f"sys.path.insert(0, {str(runtime)!r})\n"
        f"sys.path.insert(0, {str(runtime / 'dependencies')!r})\n"
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
    obsolete_files = []
    for name, expected in manifest["files"].items():
        obsolete = Path(name)
        if obsolete.is_relative_to(runtime) and obsolete not in files:
            if obsolete.is_symlink() or (
                obsolete.exists() and digest(obsolete.read_bytes()) != expected
            ):
                raise RuntimeError("Modified obsolete runtime file preserved: " + str(obsolete))
            obsolete_files.append(obsolete)
    config_path = config / "deckbridge/config.toml"
    if config_path.is_symlink():
        raise RuntimeError("Config symlink refused")
    config_original = None
    if config_path.exists():
        if load(config_path).prefix != prefix:
            raise RuntimeError("Existing config names a different prefix; preserving it")
        config_original = config_path.read_bytes()
        if len(config_original) > 65536:
            raise RuntimeError("Oversized configuration; preserving it")
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
    config_content = config_original if config_original is not None else cfg.encode()
    mode = getattr(args, "webview_mode", None)
    if mode is not None:
        config_content = with_mode(config_content, mode)
    menu_plan = None
    if getattr(args, "no_menu", False):
        if manifest.get("menu_entry"):
            menu_plan = menu.restore(data, manifest["menu_entry"])
    else:
        menu_plan = menu.prepare(
            data,
            prefix,
            quote_exec(str(launcher)) + " streamdeck",
            quote_exec(str(home / ".local/bin/streamdeck-wine")),
            manifest.get("menu_entry"),
        )
    print(
        f"Install/update {len(files)} owned files; private config {config_path}; "
        f"streamdeck:// -> {DESKTOP}."
    )
    print("Existing Wine prefix, original launcher, profiles and plugins are not modified.")
    print("Stream Deck menu integration: " + ("managed" if menu_plan is not None else "unchanged"))
    if mode == "compatible":
        print("Selected plugin-settings fix: app-local software rendering, renderer sandbox OFF.")
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
        temporary_config = temporary / "config.toml"
        atomic(temporary_config, config_content)
        load(temporary_config)
        run(["/usr/bin/desktop-file-validate", str(temporary / DESKTOP)])
        if menu_plan is not None and menu_plan.content is not None:
            temporary_menu = temporary / "streamdeck-wine.desktop"
            temporary_menu.write_bytes(menu_plan.content)
            run(["/usr/bin/desktop-file-validate", str(temporary_menu)])
        # ExecStart must already exist for systemd-analyze; validate after managed copy.
    if (
        config_path.is_symlink()
        or (config_original is None and config_path.exists())
        or (config_original is not None and config_path.read_bytes() != config_original)
    ):
        raise RuntimeError("Configuration changed during installation; preserving it")
    if config_content != config_original:
        if config_original is not None:
            private_backup(state, "webview-config", config_original)
        atomic(config_path, config_content)
    text = mime.read_text() if mime.exists() else ""
    if "previous_mime_line" not in manifest:
        manifest["previous_mime_line"] = default_line(text)
        atomic(state / "backups/mimeapps-before-deckbridge", text.encode())
        atomic(manifest_path, json.dumps(manifest, indent=2).encode())
    for path, (content, mode) in files.items():
        atomic(path, content, mode)
        manifest["files"][str(path)] = digest(content)
        atomic(manifest_path, json.dumps(manifest, indent=2).encode())
    for obsolete in obsolete_files:
        obsolete.unlink(missing_ok=True)
        del manifest["files"][str(obsolete)]
    atomic(manifest_path, json.dumps(manifest, indent=2).encode())
    if menu_plan is not None:
        apply_menu(menu_plan, manifest, state)
    run(["/usr/bin/systemd-analyze", "--user", "verify", str(service)])
    atomic(mime, replace_default(text, MIME + "=" + DESKTOP + ";\n").encode())
    refresh_desktop(data)
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
    parser.add_argument(
        "--no-menu", action="store_true", help="Keep or restore the original menu entry"
    )
    parser.add_argument(
        "--webview-mode",
        choices=("compatible", "sandboxed"),
        help="Explicit choice: plugin settings fix (reduced renderer isolation) or sandboxed mode",
    )
    try:
        install(parser.parse_args())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, BridgeError) as error:
        print(f"Installation stopped: {error}", file=sys.stderr)
        sys.exit(1)
