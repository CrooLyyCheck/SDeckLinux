"""Standard setup has no interactive repair step or desktop interaction in tests."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.setup import setup


class SetupTests(unittest.TestCase):
    def test_standard_install_and_explicit_override_use_one_installation_flow(self):
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
                patch("builtins.input", side_effect=AssertionError("No mode prompt allowed")),
                patch("tools.setup.subprocess.run") as run,
            ):
                self.assertEqual(setup(), 0)
                self.assertEqual(run.call_count, 2)
                args = run.call_args.args[0]
                self.assertIn(str(prefix), args)
                self.assertIn("--apply", args)
                self.assertNotIn("--webview-mode", args)
                self.assertFalse(any("kdialog" in str(call) for call in run.call_args_list))
                run.reset_mock()
                self.assertEqual(setup("sandboxed"), 0)
                args = run.call_args.args[0]
                self.assertEqual(args[args.index("--webview-mode") + 1], "sandboxed")

    def test_missing_wine_installation_does_not_run_installation_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            with (
                patch("pathlib.Path.home", return_value=home),
                patch.dict(os.environ, {"XDG_DATA_HOME": str(home / "data")}),
                patch("tools.setup.subprocess.run") as run,
            ):
                self.assertEqual(setup(), 1)
                run.assert_not_called()
