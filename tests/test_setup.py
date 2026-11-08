"""Installer UI choices never invoke Wine or desktop interaction in tests."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.setup import choose_mode, setup


class SetupTests(unittest.TestCase):
    def test_dialog_maps_explicit_choices_and_cancel(self):
        with patch("tools.setup.subprocess.run") as run:
            for code, expected in [(0, "compatible"), (1, "sandboxed"), (2, None), (255, None)]:
                run.return_value = subprocess.CompletedProcess([], code)
                self.assertEqual(choose_mode("/usr/bin/kdialog"), expected)
            args = run.call_args.args[0]
            self.assertIn("--yesnocancel", args)
            self.assertIn("DISABLES", args[-1])

    def test_setup_detects_prefix_and_passes_choice_to_installer(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            prefix = home / "data/streamdeck-wine/prefix"
            app = prefix / "drive_c/Program Files/Elgato/StreamDeck/StreamDeck.exe"
            app.parent.mkdir(parents=True)
            app.write_text("fixture")
            (prefix / ".streamdeck-installer-owned").write_text(
                f"streamdeck-wine installer v1:{os.getuid()}"
            )
            launcher = home / ".local/bin/streamdeck-wine"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("fixture")
            launcher.chmod(0o700)
            with (
                patch("pathlib.Path.home", return_value=home),
                patch.dict(os.environ, {"XDG_DATA_HOME": str(home / "data")}),
                patch("tools.setup.choose_mode") as choice,
                patch("tools.setup.notify"),
                patch("tools.setup.subprocess.run") as run,
            ):
                choice.return_value = None
                self.assertEqual(setup(), 0)
                run.assert_not_called()
                choice.return_value = "compatible"
                self.assertEqual(setup(), 0)
                self.assertEqual(run.call_count, 2)
                args = run.call_args.args[0]
                self.assertIn(str(prefix), args)
                self.assertEqual(args[args.index("--webview-mode") + 1], "compatible")
                self.assertIn("--apply", args)
