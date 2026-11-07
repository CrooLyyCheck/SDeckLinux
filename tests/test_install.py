"""Installer ownership and reversibility on a temporary filesystem, no systemd calls."""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deckbridge.portal import HANDLER, LEGACY
from tools.install import MIME, install


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
            patch("deckbridge.portal.read_permissions", side_effect=lambda: dict(self.permissions)),
            patch("deckbridge.portal.set_permission", side_effect=set_permission),
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
