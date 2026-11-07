import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deckbridge.compat.plugins.volume_controller.settings import set_display
from deckbridge.config import load


class DisplayPreferenceTests(unittest.TestCase):
    def test_display_switch_preserves_other_preferences_and_keeps_private_backup(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"XDG_STATE_HOME": folder}),
        ):
            path = Path(folder) / "config.toml"
            body = (
                'version=1\n[wine]\nprefix="/prefix"\n'
                'executable="/prefix/drive_c/StreamDeck.exe"\ncommand="/usr/bin/wine"\n'
                "[features]\ndeep_links=true\n[audio]\nenabled=true\nallow_system_write=true\n"
                "[compat.volume_controller]\nenabled=true\nhide_event_streams=false\n"
            )
            path.write_text(body)
            path.chmod(0o600)
            self.assertTrue(set_display(path, "text"))
            cfg = load(path)
            self.assertEqual(cfg.volume_controller_display, "text")
            self.assertFalse(cfg.volume_controller_hide_events)
            self.assertTrue(cfg.audio.allow_system_write)
            backups = list((Path(folder) / "deckbridge/backups").glob("*.toml"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), body)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
            self.assertFalse(set_display(path, "text"))
            self.assertTrue(set_display(path, "icons"))
            self.assertEqual(load(path).volume_controller_display, "icons")
