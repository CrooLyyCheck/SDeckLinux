"""Wine family aliases with synthetic registry state; no Wine/audio execution."""

import copy
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deckbridge.compat.windows import fonts
from deckbridge.config import load
from deckbridge.protocol import BridgeError


class FontFallbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.prefix = self.data / "streamdeck-wine/prefix"
        self.prefix.mkdir(parents=True)
        (self.prefix / ".streamdeck-installer-owned").write_text(
            f"streamdeck-wine installer v1:{os.getuid()}"
        )
        (self.prefix / "user.reg").write_bytes(b"fixture")
        self.value = None
        self.manifest = {}
        self.events = []
        self.writes = 0
        for mock in (
            patch.object(fonts, "reg", side_effect=self.reg),
            patch.object(
                fonts.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, b"Liberation Sans", b""),
            ),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def reg(self, prefix, args):
        self.assertEqual(prefix, self.prefix)
        self.assertEqual(args[1:4], [fonts.KEY, "/v", "Arial"])
        self.assertIn("backup", self.events)
        if args[0] == "query":
            return (
                (1, b"")
                if self.value is None
                else (0, f"    Arial    REG_SZ    {self.value}\r\n".encode())
            )
        self.assertEqual(
            self.manifest[fonts.MANAGED]["phase"], "pending" if args[0] == "add" else "applied"
        )
        self.writes += 1
        self.value = None if args[0] == "delete" else args[7]
        return 0, b""

    def backup(self, kind, data):
        self.assertEqual(data, b"fixture")
        self.events.append("backup")

    def save(self):
        self.events.append(copy.deepcopy(self.manifest))

    def sync(self, enabled=True):
        fonts.synchronize(self.prefix, self.data, enabled, self.manifest, self.save, self.backup)

    def test_install_update_and_restore_original_absence(self):
        self.sync()
        self.assertEqual(self.events[1][fonts.MANAGED]["phase"], "pending")
        self.assertEqual(self.value, fonts.FAMILY)
        self.sync()
        self.assertEqual(self.writes, 1)
        self.sync(False)
        self.assertIsNone(self.value)
        self.assertNotIn(fonts.MANAGED, self.manifest)

    def test_existing_custom_alias_is_preserved(self):
        self.value = "User Font"
        self.sync()
        self.assertEqual(self.value, "User Font")
        self.assertEqual(self.manifest, {})
        self.assertEqual(self.writes, 0)

    def test_later_user_change_survives_update_and_removal(self):
        self.sync()
        self.value = "User Font"
        self.sync()
        self.sync(False)
        self.assertEqual(self.value, "User Font")
        self.assertEqual(self.writes, 1)

    def test_preexisting_fallback_is_not_deleted(self):
        self.value = fonts.FAMILY
        self.sync()
        self.sync(False)
        self.assertEqual(self.value, fonts.FAMILY)
        self.assertEqual(self.writes, 0)

    def test_interrupted_write_recovers(self):
        self.manifest[fonts.MANAGED] = {
            "prefix": str(self.prefix),
            "previous": None,
            "phase": "pending",
        }
        self.value = fonts.FAMILY
        self.sync()
        self.assertEqual(self.manifest[fonts.MANAGED]["phase"], "applied")
        self.assertEqual(self.writes, 0)

    def test_unavailable_font_prevents_registry_access(self):
        with patch.object(
            fonts.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, b"Other Font", b""),
        ):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                self.sync()
        self.assertEqual(self.events, [])

    def test_font_config_defaults_opt_out_and_strict_boolean(self):
        path = self.data / "config.toml"
        body = (
            'version=1\n[wine]\nprefix="/prefix"\nexecutable="/prefix/drive_c/app.exe"\n'
            'command="/usr/bin/wine"\n[features]\ndeep_links=true\n'
        )
        path.write_text(body)
        path.chmod(0o600)
        self.assertTrue(load(path).wine_font_fallback)
        path.write_text(body + "[compat.windows.fonts]\nenabled=false\n")
        self.assertFalse(load(path).wine_font_fallback)
        path.write_text(body + '[compat.windows.fonts]\nenabled="false"\n')
        with self.assertRaises(BridgeError):
            load(path)
