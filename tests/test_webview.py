import dataclasses
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deckbridge.compat.sdeck.webview.launcher import launch, launch_environment
from deckbridge.compat.sdeck.webview.preferences import with_mode
from deckbridge.config import load
from deckbridge.protocol import BridgeError
from tests.test_core import config


class WebviewLaunchTests(unittest.TestCase):
    def test_mode_edit_rejects_a_fake_table_inside_an_application_argument(self):
        original = b'''version=1
[applications]
editor=["/usr/bin/editor", """
[compat.sdeck.webview]
renderer_sandbox=true
"""]
'''
        with self.assertRaisesRegex(RuntimeError, "Unsupported WebEngine config layout"):
            with_mode(original, "compatible")

    def test_software_rendering_preserves_existing_flags_and_is_independent_of_sandbox(self):
        original = {"QTWEBENGINE_CHROMIUM_FLAGS": '--disable-logging --lang="en-US"'}
        normal = launch_environment(True, original)
        software = launch_environment(True, original, software=True)
        self.assertEqual(normal, original)
        self.assertEqual(
            software["QTWEBENGINE_CHROMIUM_FLAGS"],
            original["QTWEBENGINE_CHROMIUM_FLAGS"] + " --disable-gpu",
        )
        self.assertNotIn("QTWEBENGINE_DISABLE_SANDBOX", software)
        self.assertEqual(launch_environment(True, software, software=True), software)

    def test_sandbox_default_and_opt_in_are_child_environment_only(self):
        original = {
            "DISPLAY": ":example",
            "WINE_FIX": "preserve",
            "QTWEBENGINE_DISABLE_SANDBOX": "1",
        }
        normal = launch_environment(True, original)
        opted = launch_environment(False, original)
        self.assertNotIn("QTWEBENGINE_DISABLE_SANDBOX", normal)
        self.assertEqual(opted["QTWEBENGINE_DISABLE_SANDBOX"], "1")
        self.assertEqual(normal["WINE_FIX"], original["WINE_FIX"])
        self.assertEqual(original["QTWEBENGINE_DISABLE_SANDBOX"], "1")
        self.assertNotIn("QTWEBENGINE_REMOTE_DEBUGGING", opted)
        with self.assertRaisesRegex(BridgeError, "webview_external_override"):
            launch_environment(True, {"QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox"})

    def test_only_audited_existing_launcher_is_executed_without_duplicate_or_file_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            data = home / "data"
            cfg = config(data / "streamdeck-wine/prefix")
            cfg.executable.parent.mkdir(parents=True)
            cfg.executable.write_text("fixture")
            (cfg.prefix / ".streamdeck-installer-owned").write_text(
                f"streamdeck-wine installer v1:{os.getuid()}"
            )
            wrapper = home / ".local/bin/streamdeck-wine"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text("# original launcher fixture\n")
            wrapper.chmod(0o700)
            before = {str(p): p.read_bytes() for p in home.rglob("*") if p.is_file()}
            with (
                patch("pathlib.Path.home", return_value=home),
                patch.dict(os.environ, {"XDG_DATA_HOME": str(data)}),
                patch(
                    "deckbridge.compat.sdeck.webview.launcher.running_instances", return_value=[]
                ) as instances,
                patch("os.execve") as execute,
            ):
                launch(cfg)
                self.assertNotIn("QTWEBENGINE_DISABLE_SANDBOX", execute.call_args.args[2])
                launch(
                    dataclasses.replace(
                        cfg, streamdeck_webview_sandbox=False, streamdeck_webview_software=True
                    )
                )
                self.assertEqual(execute.call_args.args[2]["QTWEBENGINE_DISABLE_SANDBOX"], "1")
                self.assertIn(
                    "--disable-gpu", execute.call_args.args[2]["QTWEBENGINE_CHROMIUM_FLAGS"]
                )
                self.assertEqual(execute.call_args.args[:2], (wrapper, [str(wrapper)]))
                instances.return_value = [123]
                with self.assertRaisesRegex(BridgeError, "instance_already_running"):
                    launch(cfg, no_sandbox=True)
                self.assertEqual(execute.call_count, 2)
            self.assertEqual(
                before, {str(p): p.read_bytes() for p in home.rglob("*") if p.is_file()}
            )

    def test_webview_preference_is_optional_strict_and_independent_of_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            body = (
                'version=1\n[wine]\nprefix="/prefix"\n'
                'executable="/prefix/drive_c/StreamDeck.exe"\ncommand="/usr/bin/wine"\n'
                "[features]\ndeep_links=true\n"
            )
            path.write_text(body)
            path.chmod(0o600)
            self.assertTrue(load(path).streamdeck_webview_sandbox)
            self.assertFalse(load(path).streamdeck_webview_software)
            path.write_text(
                body + "[compat.sdeck.webview]\nrenderer_sandbox=false\nsoftware_rendering=true\n"
            )
            self.assertFalse(load(path).streamdeck_webview_sandbox)
            self.assertTrue(load(path).streamdeck_webview_software)
            path.write_text(body + '[compat.sdeck.webview]\nrenderer_sandbox="false"\n')
            with self.assertRaisesRegex(BridgeError, "invalid_webview_config"):
                load(path)
