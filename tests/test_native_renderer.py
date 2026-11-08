"""Native renderer ownership with a synthetic registry; never execute Wine."""

from __future__ import annotations

import copy
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deckbridge.compat.sdeck.webview import native_renderer as renderer


class NativeRendererTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.data = Path(self.folder.name)
        self.prefix = self.data / "streamdeck-wine/prefix"
        app = self.prefix / "drive_c/Program Files/Elgato/StreamDeck/StreamDeck.exe"
        app.parent.mkdir(parents=True)
        app.write_bytes(b"synthetic executable, never run")
        (self.prefix / ".streamdeck-installer-owned").write_text(
            f"streamdeck-wine installer v1:{os.getuid()}"
        )
        self.registry = self.prefix / "user.reg"
        self.registry.write_bytes(b"synthetic registry")
        self.value = None
        self.manifest = {}
        self.events = []
        self.writes = []
        for mock in (
            patch.object(renderer, "APP_SHA256", hashlib.sha256(app.read_bytes()).hexdigest()),
            patch.object(renderer, "reg", side_effect=self.reg),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def backup(self, kind, content):
        self.assertEqual(kind, "native-renderer-user-reg")
        self.assertEqual(content, b"synthetic registry")
        self.events.append("backup")

    def save(self):
        self.events.append(copy.deepcopy(self.manifest.get(renderer.MANAGED)))

    def reg(self, prefix, arguments):
        self.assertEqual(prefix, self.prefix)
        self.assertIn("backup", self.events)  # Includes Wine's read/flush boundary.
        self.assertEqual(arguments[1:4], [renderer.KEY, "/v", renderer.VALUE])
        if arguments[0] == "query":
            if self.value is None:
                return 1, b""
            value = self.value["value"]
            text = hex(value) if self.value["type"] == "REG_DWORD" else value
            return 0, f"    {renderer.VALUE}    {self.value['type']}    {text}\r\n".encode()
        self.assertIn(renderer.MANAGED, self.manifest)  # Journal precedes every write.
        self.writes.append(arguments)
        self.value = (
            None
            if arguments[0] == "delete"
            else {
                "type": arguments[5],
                "value": int(arguments[7]) if arguments[5] == "REG_DWORD" else arguments[7],
            }
        )
        return 0, b""

    def sync(self, enabled=True):
        renderer.synchronize(self.prefix, self.data, enabled, self.manifest, self.save, self.backup)

    def restore(self):
        renderer.restore(self.data, self.manifest, self.save, self.backup)

    def test_absent_value_is_journaled_before_write_and_removed_on_restore(self):
        self.sync()
        self.assertEqual(self.events[1]["phase"], "pending")
        self.assertIsNone(self.events[1]["previous"])
        self.assertEqual(self.value, renderer.ZERO)
        self.assertEqual(self.manifest[renderer.MANAGED]["phase"], "applied")
        self.sync()
        self.assertEqual(len(self.writes), 1)
        self.restore()
        self.assertIsNone(self.value)
        self.assertNotIn(renderer.MANAGED, self.manifest)
        self.assertEqual(self.writes[-1], ["delete", renderer.KEY, "/v", renderer.VALUE, "/f"])

    def test_restore_preserves_original_type_and_value(self):
        for original in (
            {"type": "REG_DWORD", "value": 1},
            {"type": "REG_SZ", "value": "true"},
            {"type": "REG_SZ", "value": "false"},
        ):
            with self.subTest(original=original):
                self.value = original
                self.sync()
                self.assertEqual(self.value, renderer.ZERO)
                self.sync(enabled=False)
                self.assertEqual(self.value, original)
                self.assertNotIn(renderer.MANAGED, self.manifest)

    def test_preexisting_zero_is_not_deleted(self):
        self.value = dict(renderer.ZERO)
        self.sync()
        self.restore()
        self.assertEqual(self.value, renderer.ZERO)
        self.assertEqual(self.writes, [])

    def test_user_changes_survive_updates_and_deactivation(self):
        self.sync()
        self.value = {"type": "REG_DWORD", "value": 1}
        self.sync()
        self.restore()
        self.assertEqual(self.value, {"type": "REG_DWORD", "value": 1})
        self.assertEqual(len(self.writes), 1)

    def test_unrecognized_build_never_invokes_wine_or_backup(self):
        with patch.object(renderer, "APP_SHA256", "0" * 64):
            self.sync()
        self.assertEqual(self.events, [])
        self.assertEqual(self.manifest, {})

    def test_pending_journal_recovers_before_or_after_interrupted_write(self):
        for current in (None, renderer.ZERO):
            with self.subTest(current=current):
                self.value = current
                self.manifest[renderer.MANAGED] = {
                    "v": 1,
                    "prefix": str(self.prefix),
                    "previous": None,
                    "phase": "pending",
                }
                self.sync()
                self.assertEqual(self.value, renderer.ZERO)
                self.assertEqual(self.manifest[renderer.MANAGED]["phase"], "applied")

    def test_pending_journal_conflict_preserves_value(self):
        self.manifest[renderer.MANAGED] = {
            "v": 1,
            "prefix": str(self.prefix),
            "previous": None,
            "phase": "pending",
        }
        self.value = {"type": "REG_DWORD", "value": 1}
        with self.assertRaisesRegex(RuntimeError, "changed during installation"):
            self.sync()
        self.assertEqual(self.writes, [])

    def test_registry_symlink_is_rejected_before_wine(self):
        self.registry.unlink()
        self.registry.symlink_to(self.prefix / ".streamdeck-installer-owned")
        with self.assertRaisesRegex(RuntimeError, "Unsafe Wine registry"):
            self.sync()
        self.assertEqual(self.events, [])

    def test_oversized_registry_is_rejected_before_wine(self):
        with self.registry.open("wb") as stream:
            stream.truncate(16 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(RuntimeError, "bounded registry backup"):
            self.sync()
        self.assertEqual(self.events, [])

    def test_backup_failure_prevents_wine_and_ownership_writes(self):
        def failed_backup(kind, content):
            raise RuntimeError("fixture backup failed")

        with self.assertRaisesRegex(RuntimeError, "fixture backup failed"):
            renderer.synchronize(
                self.prefix, self.data, True, self.manifest, self.save, failed_backup
            )
        self.assertEqual(self.events, [])
        self.assertEqual(self.manifest, {})

    def test_restore_rejects_record_pointing_outside_owned_prefix(self):
        self.sync()
        self.manifest[renderer.MANAGED]["prefix"] = str(self.data / "other-prefix")
        self.events.clear()
        with self.assertRaisesRegex(RuntimeError, "prefix unavailable"):
            self.restore()
        self.assertEqual(self.events, [])

    def test_parser_rejects_unsupported_boolean_or_type(self):
        for kind, value in (("REG_DWORD", "0x2"), ("REG_SZ", "surprise"), ("REG_BINARY", "00")):
            with self.subTest(kind=kind):
                reply = f"    {renderer.VALUE}    {kind}    {value}\r\n".encode()
                with patch.object(renderer, "reg", return_value=(0, reply)):
                    with self.assertRaises(RuntimeError):
                        renderer.query(self.prefix)

    def test_failed_readback_retains_pending_journal(self):
        def no_write(prefix, arguments):
            if arguments[0] == "add":
                return 0, b""
            return self.reg(prefix, arguments)

        with patch.object(renderer, "reg", side_effect=no_write):
            with self.assertRaisesRegex(RuntimeError, "could not be verified"):
                self.sync()
        self.assertIsNone(self.value)
        self.assertEqual(self.manifest[renderer.MANAGED]["phase"], "pending")
