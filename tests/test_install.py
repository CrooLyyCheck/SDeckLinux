"""Installer ownership and reversibility on a temporary filesystem, no systemd calls."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from deckbridge.compat.sdeck.oauth.portal import HANDLER, LEGACY
from deckbridge.config import load
from tools.install import MIME, ROOT, digest, install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.prefix = self.home / "prefix"
        app = self.prefix / "drive_c/Program Files/Elgato/StreamDeck/StreamDeck.exe"
        app.parent.mkdir(parents=True)
        app.write_text("fixture, not a third-party executable")
        (self.prefix / "system.reg").write_text("fixture")
        self.config = self.home / "config"
        self.config.mkdir()
        self.mime = self.config / "mimeapps.list"
        self.original = (
            f"[Default Applications]\n{MIME}=previous.desktop;\ntext/plain=editor.desktop;\n"
        )
        self.mime.write_text(self.original)
        self.launcher = self.home / ".local/bin/deckbridge"
        self.args = argparse.Namespace(prefix=self.prefix, apply=True, deactivate=False)
        self.permissions = {}

        def set_permission(app, values):
            self.permissions[app] = values

        for mock in (
            patch("pathlib.Path.home", return_value=self.home),
            patch.dict(
                os.environ,
                {
                    "XDG_CONFIG_HOME": str(self.config),
                    "XDG_DATA_HOME": str(self.home / "data"),
                    "XDG_STATE_HOME": str(self.home / "state"),
                },
            ),
            patch("tools.install.run"),
            patch("tools.install.fonts.synchronize"),
            patch(
                "deckbridge.compat.sdeck.oauth.portal.read_permissions",
                side_effect=lambda: dict(self.permissions),
            ),
            patch(
                "deckbridge.compat.sdeck.oauth.portal.set_permission", side_effect=set_permission
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock.__enter__()
            self.addCleanup(mock.__exit__, None, None, None)

    def test_dry_run_does_not_write(self):
        self.args.apply = False
        before = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        install(self.args)
        after = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_font_fallback_is_automatic_and_explicit_opt_out_is_preserved(self):
        with patch("tools.install.fonts.synchronize") as synchronize:
            install(self.args)
            self.assertTrue(synchronize.call_args.args[2])
            path = self.config / "deckbridge/config.toml"
            content = path.read_bytes().replace(
                b"[compat.windows.fonts]\nenabled = true",
                b"[compat.windows.fonts]\nenabled = false",
            )
            path.write_bytes(content)
            install(self.args)
            self.assertFalse(synchronize.call_args.args[2])
            self.assertEqual(path.read_bytes(), content)

    def test_native_renderer_is_builtin_respects_opt_out_and_restores_on_deactivation(self):
        with (
            patch("tools.install.native_renderer.synchronize") as synchronize,
            patch("tools.install.native_renderer.restore") as restore,
        ):
            self.args.apply = False
            install(self.args)
            synchronize.assert_not_called()
            self.args.apply = True
            install(self.args)
            self.assertTrue(synchronize.call_args.args[2])
            self.args.webview_mode = "sandboxed"
            install(self.args)
            self.assertFalse(synchronize.call_args.args[2])
            self.args.deactivate = True
            install(self.args)
            restore.assert_called_once()

    def obsolete_file(self):
        path = self.home / "data/deckbridge/runtime/deckbridge/portal.py"
        path.write_bytes(b"# previously owned module\n")
        manifest = self.home / "state/deckbridge/install.json"
        content = json.loads(manifest.read_text())
        content["files"][str(path)] = digest(path.read_bytes())
        manifest.write_text(json.dumps(content))
        return path

    def test_recursive_layout_and_contract_are_installed_and_old_owned_modules_removed(self):
        install(self.args)
        old = self.obsolete_file()
        install(self.args)
        runtime = self.home / "data/deckbridge/runtime"
        self.assertFalse(old.exists())
        for relative in (
            "deckbridge/compat/sdeck/oauth/portal.py",
            "deckbridge/compat/plugins/volume_controller/contract.json",
            "deckbridge/backends/audio/pipewire.py",
        ):
            self.assertEqual((runtime / relative).read_bytes(), (ROOT / relative).read_bytes())
        self.assertTrue((runtime / "dependencies/websockets/__init__.py").is_file())

    def test_modified_obsolete_module_blocks_update_before_any_managed_writes(self):
        install(self.args)
        old = self.obsolete_file()
        old.write_text("user modification")
        before = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(RuntimeError, "Modified obsolete runtime file preserved"):
            install(self.args)
        after = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_idempotent_install_and_scoped_restore(self):
        install(self.args)
        first_launcher = self.launcher.read_bytes()
        install(self.args)
        self.assertEqual(self.launcher.read_bytes(), first_launcher)
        self.mime.write_text(self.mime.read_text().replace("editor.desktop", "user-change.desktop"))
        self.args.deactivate = True
        install(self.args)
        self.assertFalse(self.launcher.exists())
        self.assertEqual(
            self.mime.read_text(), self.original.replace("editor.desktop", "user-change.desktop")
        )
        self.assertTrue((self.config / "deckbridge/config.toml").exists())
        self.assertTrue((self.prefix / "system.reg").exists())
        install(self.args)  # Repeated deactivation is harmless.

    def test_existing_unowned_file_preserved(self):
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text("user data")
        with self.assertRaisesRegex(RuntimeError, "unowned/modified"):
            install(self.args)
        self.assertEqual(self.launcher.read_text(), "user data")
        self.assertEqual(self.mime.read_text(), self.original)

    def test_modified_owned_file_preserved_on_update_and_deactivation(self):
        install(self.args)
        self.launcher.write_text("user customization")
        with self.assertRaisesRegex(RuntimeError, "unowned/modified"):
            install(self.args)
        self.args.deactivate = True
        install(self.args)
        self.assertEqual(self.launcher.read_text(), "user customization")

    def test_user_new_mime_default_preserved(self):
        install(self.args)
        self.mime.write_text(self.original.replace("previous.desktop", "user-new-default.desktop"))
        self.args.deactivate = True
        install(self.args)
        self.assertIn("user-new-default.desktop", self.mime.read_text())

    def test_remembered_legacy_portal_choice_restored_without_other_app_changes(self):
        self.permissions.update({"": [LEGACY, "2", "3"], "other.app": ["user-editor", "9", "10"]})
        original = dict(self.permissions)
        install(self.args)
        self.assertEqual(self.permissions[""], [HANDLER, "2", "3"])
        self.assertEqual(self.permissions["other.app"], original["other.app"])
        install(self.args)
        self.args.deactivate = True
        install(self.args)
        self.assertEqual(self.permissions, original)

    def test_user_changed_portal_choice_preserved_on_deactivation(self):
        self.permissions[""] = [LEGACY, "2", "3"]
        install(self.args)
        self.permissions[""] = ["user-new-handler", "1", "3"]
        self.args.deactivate = True
        install(self.args)
        self.assertEqual(self.permissions[""], ["user-new-handler", "1", "3"])

    def test_portal_dry_run_preserves_preferences(self):
        self.permissions[""] = [LEGACY, "2", "3"]
        self.args.apply = False
        install(self.args)
        self.assertEqual(self.permissions[""], [LEGACY, "2", "3"])

    def menu_fixture(self):
        data = self.home / "data"
        base = data / "streamdeck-wine"
        self.prefix = base / "prefix"
        app = self.prefix / "drive_c/Program Files/Elgato/StreamDeck/StreamDeck.exe"
        app.parent.mkdir(parents=True)
        app.write_text("fixture, never executed")
        (self.prefix / "system.reg").write_text("fixture")
        (self.prefix / ".streamdeck-installer-owned").write_text(
            f"streamdeck-wine installer v1:{os.getuid()}"
        )
        self.args.prefix = self.prefix
        wrapper = self.home / ".local/bin/streamdeck-wine"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text(
            f"#!{sys.executable}\nimport json, os, pathlib\n"
            "pathlib.Path(os.environ['MENU_RECEIPT']).write_text(json.dumps({"
            "'sandbox':os.environ.get('QTWEBENGINE_DISABLE_SANDBOX'),"
            "'chromium':os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS')}))\n"
        )
        wrapper.chmod(0o700)
        desktop = data / "applications/streamdeck-wine.desktop"
        desktop.parent.mkdir(parents=True)
        original = (
            "[Desktop Entry]\nType=Application\nName=Stream Deck (Wine)\n"
            f'Exec="{wrapper}"\nIcon=preserved-icon\nTerminal=false\n'
        ).encode()
        desktop.write_bytes(original)
        desktop.chmod(0o640)
        (base / "managed-files.json").write_text(json.dumps({str(desktop): digest(original)}))
        return desktop, original, wrapper

    def test_standard_install_menu_start_gets_builtin_fixes_without_mode_flags(self):
        desktop, _, _ = self.menu_fixture()
        install(self.args)
        cfg = load(self.config / "deckbridge/config.toml")
        self.assertFalse(cfg.streamdeck_webview_sandbox)
        self.assertTrue(cfg.streamdeck_webview_software)
        command = next(
            line[5:] for line in desktop.read_text().splitlines() if line.startswith("Exec=")
        )
        self.assertEqual(shlex.split(command), [str(self.launcher), "streamdeck"])
        runtime = self.home / "runtime"
        runtime.mkdir(mode=0o700)
        receipt = self.home / "menu-receipt.json"
        env = {
            key: value for key, value in os.environ.items() if not key.startswith("QTWEBENGINE_")
        }
        env.update(HOME=str(self.home), XDG_RUNTIME_DIR=str(runtime), MENU_RECEIPT=str(receipt))
        subprocess.run(  # noqa: S603 - installer-generated menu, only fixture executables
            shlex.split(command), env=env, check=True, capture_output=True, timeout=10
        )
        observed = json.loads(receipt.read_text())
        self.assertEqual(observed["sandbox"], "1")
        self.assertIn("--disable-gpu", observed["chromium"])

    def test_menu_install_update_and_deactivation_restore_original_bytes_and_mode(self):
        desktop, original, wrapper = self.menu_fixture()
        wrapper_before = wrapper.read_bytes()
        install(self.args)
        installed = desktop.read_bytes()
        install(self.args)
        self.assertEqual(desktop.read_bytes(), installed)
        backups = list((self.home / "state/deckbridge/backups").glob("streamdeck-menu-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.args.deactivate = True
        install(self.args)
        self.assertEqual(desktop.read_bytes(), original)
        self.assertEqual(desktop.stat().st_mode & 0o777, 0o640)
        self.assertEqual(wrapper.read_bytes(), wrapper_before)
        self.assertTrue((self.prefix / "system.reg").exists())

    def test_custom_menu_blocks_install_before_any_changes(self):
        desktop, _, _ = self.menu_fixture()
        desktop.write_text("user customization")
        self.args.webview_mode = "compatible"
        before = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(RuntimeError, "Custom menu entry preserved"):
            install(self.args)
        self.assertEqual(
            before, {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        )

    def test_user_modified_managed_menu_survives_deactivation(self):
        desktop, _, _ = self.menu_fixture()
        install(self.args)
        desktop.write_text("user replacement")
        self.args.deactivate = True
        install(self.args)
        self.assertEqual(desktop.read_text(), "user replacement")

    def test_modified_managed_menu_blocks_update_before_config_changes(self):
        desktop, _, _ = self.menu_fixture()
        install(self.args)
        desktop.write_text("user replacement")
        self.args.webview_mode = "compatible"
        before = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(RuntimeError, "Modified menu entry preserved"):
            install(self.args)
        self.assertEqual(
            before, {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        )

    def test_menu_update_recovers_when_journal_precedes_menu_write(self):
        desktop, original, _ = self.menu_fixture()
        install(self.args)
        desktop.write_bytes(original)
        install(self.args)
        self.assertIn(str(self.launcher), desktop.read_text())
        self.args.deactivate = True
        install(self.args)
        self.assertEqual(desktop.read_bytes(), original)

    def test_user_symlink_menu_is_preserved_on_deactivation(self):
        desktop, _, _ = self.menu_fixture()
        install(self.args)
        target = self.home / "custom-menu"
        target.write_text("user data")
        desktop.unlink()
        desktop.symlink_to(target)
        self.args.deactivate = True
        install(self.args)
        self.assertTrue(desktop.is_symlink())
        self.assertEqual(target.read_text(), "user data")

    def test_missing_original_menu_is_created_and_removed_on_deactivation(self):
        desktop, _, _ = self.menu_fixture()
        desktop.unlink()
        install(self.args)
        self.assertIn(" streamdeck\n", desktop.read_text())
        self.args.deactivate = True
        install(self.args)
        self.assertFalse(desktop.exists())

    def test_no_menu_switch_restores_original_and_preserves_unmanaged_menu(self):
        desktop, original, _ = self.menu_fixture()
        install(self.args)
        self.args.no_menu = True
        install(self.args)
        self.assertEqual(desktop.read_bytes(), original)
        desktop.write_text("new custom menu")
        install(self.args)
        self.assertEqual(desktop.read_text(), "new custom menu")

    def test_webview_mode_change_preserves_audio_and_keeps_verified_private_backup(self):
        self.menu_fixture()
        self.args.webview_mode = "sandboxed"
        install(self.args)
        path = self.config / "deckbridge/config.toml"
        extra = (
            '\n[audio]\nenabled=true\nallow_write=true\nallowed_apps=["app:fixture"]\n'
            '[compat.volume_controller]\nenabled=true\ndisplay="text"\n'
        )
        original = path.read_bytes() + extra.encode()
        path.write_bytes(original)
        self.args.webview_mode = "compatible"
        install(self.args)
        self.assertEqual(
            tomllib.loads(path.read_text())["audio"], tomllib.loads(original.decode())["audio"]
        )
        backups = list((self.home / "state/deckbridge/backups").glob("webview-config-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.args.webview_mode = "sandboxed"
        install(self.args)
        self.assertTrue(load(path).streamdeck_webview_sandbox)
        self.assertFalse(load(path).streamdeck_webview_software)

    def test_ordinary_update_applies_builtin_defaults_to_old_config_without_rewriting_it(self):
        self.menu_fixture()
        install(self.args)
        path = self.config / "deckbridge/config.toml"
        old = path.read_bytes().split(b"[compat.sdeck.webview]\n")[0]
        path.write_bytes(old)
        install(self.args)
        self.assertEqual(path.read_bytes(), old)
        self.assertFalse(load(path).streamdeck_webview_sandbox)
        self.assertTrue(load(path).streamdeck_webview_software)

    def test_ordinary_update_preserves_explicit_sandbox_preference(self):
        self.menu_fixture()
        self.args.webview_mode = "sandboxed"
        install(self.args)
        path = self.config / "deckbridge/config.toml"
        before = path.read_bytes()
        self.args.webview_mode = None
        install(self.args)
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(load(path).streamdeck_webview_sandbox)
        self.assertFalse(load(path).streamdeck_webview_software)

    def test_menu_and_mode_dry_run_does_not_write(self):
        self.menu_fixture()
        self.args.webview_mode = "compatible"
        self.args.apply = False
        before = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        install(self.args)
        self.assertEqual(
            before, {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        )
