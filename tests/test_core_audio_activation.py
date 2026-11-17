"""Synthetic per-prefix COM registry and owned runtime; never executes Wine."""

import asyncio
import copy
import hashlib
import json
import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from deckbridge.compat.windows.core_audio import activation as com
from deckbridge.compat.windows.core_audio import runtime
from deckbridge.config import Config, load
from deckbridge.protocol import BridgeError


class ActivationTests(unittest.TestCase):
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
        self.keys = {com.KEY: {"default": com.NATIVE_DEFAULT, "ThreadingModel": "Both"}}
        self.original = copy.deepcopy(self.keys)
        self.manifest = {"files": {}}
        self.events = []
        self.mutations = 0
        self.fail_write = False
        mock = patch.object(com, "reg", side_effect=self.reg)
        mock.start()
        self.addCleanup(mock.stop)

    def reg(self, prefix, args):
        self.assertEqual(prefix, self.prefix)
        self.assertIn("backup", self.events)
        operation, key = args[:2]
        self.assertEqual(key, com.KEY)
        name = "default" if "/ve" in args else args[args.index("/v") + 1] if "/v" in args else None
        if operation == "query":
            if key not in self.keys:
                return 1, b""
            if name:
                value = self.keys[key].get(name)
                if value is None and name == "default":
                    return 0, b"    (Default)    REG_SZ    (value not set)\r\n"
                return (0, f"    {name}    REG_SZ    {value}\r\n".encode()) if value else (1, b"")
        self.assertIn(com.MANAGED, self.manifest)  # Write-ahead ownership exists.
        self.mutations += 1
        if operation == "add":
            self.assertIn(self.manifest[com.MANAGED]["phase"], ("pending", "applied"))
            self.keys.setdefault(com.KEY, {})[name] = args[args.index("/d") + 1]
            if self.fail_write:
                return 1, b""  # Simulate an applied write with an uncertain return.
        else:
            self.fail("The manager must never delete a stock class/key/value")
        return 0, b""

    def backup(self, kind, content):
        self.assertEqual(content, b"fixture")
        self.events.append("backup")

    def save(self):
        self.events.append(copy.deepcopy(self.manifest))

    def sync(self, enabled=True):
        com.synchronize(self.prefix, self.data, enabled, self.manifest, self.save, self.backup)

    def test_scoped_apply_update_and_exact_stock_registration_restoration(self):
        self.sync()
        self.assertEqual(self.keys[com.KEY], com.desired(self.data))
        self.assertEqual(self.events[1][com.MANAGED]["phase"], "pending")
        self.assertEqual(self.mutations, 1)
        self.sync()
        self.assertEqual(self.mutations, 1)
        self.sync(False)
        self.assertEqual(self.keys, self.original)
        self.assertNotIn(com.MANAGED, self.manifest)

    def test_existing_custom_registration_never_taken_over(self):
        self.keys[com.KEY] = {"default": r"C:\User\custom.dll"}
        previous = copy.deepcopy(self.keys)
        with self.assertRaisesRegex(RuntimeError, "preserved"):
            self.sync()
        self.assertEqual(self.keys, previous)
        self.assertEqual(self.mutations, 0)
        self.assertNotIn(com.MANAGED, self.manifest)

    def test_enabled_update_repairs_only_the_exact_recorded_stock_registration(self):
        self.sync()
        self.keys = copy.deepcopy(self.original)
        self.sync()
        self.assertEqual(self.keys[com.KEY], com.desired(self.data))
        self.assertEqual(self.manifest[com.MANAGED]["previous"], self.original[com.KEY])
        self.sync(False)
        self.assertEqual(self.keys, self.original)

    def test_preexisting_keys_and_foreign_values_are_preserved(self):
        self.keys[com.KEY]["Foreign"] = "keep"
        previous = copy.deepcopy(self.keys)
        self.sync()
        self.sync(False)
        self.assertEqual(self.keys, previous)

    def test_interrupted_activation_resumes_without_overwriting_first_value(self):
        self.fail_write = True
        with self.assertRaisesRegex(RuntimeError, "verified"):
            self.sync()
        self.assertEqual(self.manifest[com.MANAGED]["phase"], "pending")
        self.assertEqual(self.keys[com.KEY], com.desired(self.data))
        self.fail_write = False
        self.sync()
        self.assertEqual(self.mutations, 1)
        self.sync(False)
        self.assertEqual(self.keys, self.original)

    def test_interrupted_activation_can_be_deactivated_directly(self):
        self.fail_write = True
        with self.assertRaises(RuntimeError):
            self.sync()
        self.fail_write = False
        self.sync(False)
        self.assertEqual(self.keys, self.original)

    def test_user_changes_survive_update_and_deactivation(self):
        self.sync()
        self.keys[com.KEY]["default"] = r"C:\User\replacement.dll"
        library = com.library_path(self.data)
        self.manifest["files"] = {str(library): "hash", str(library.with_suffix(".token")): "hash"}
        self.sync()
        self.sync(False)
        self.assertEqual(
            self.keys[com.KEY], {"default": r"C:\User\replacement.dll", "ThreadingModel": "Both"}
        )
        self.assertEqual(self.manifest["files"], {})

    def test_missing_default_marker_is_not_a_valid_stock_registration(self):
        del self.keys[com.KEY]["default"]
        with self.assertRaisesRegex(RuntimeError, "preserved"):
            self.sync()
        self.assertEqual(self.mutations, 0)

    def test_config_is_default_off_strict_and_requires_audio(self):
        path = self.data / "config.toml"
        body = (
            'version=1\n[wine]\nprefix="/prefix"\nexecutable="/prefix/drive_c/app.exe"\n'
            'command="/usr/bin/wine"\n[features]\ndeep_links=true\n'
        )
        path.write_text(body)
        path.chmod(0o600)
        self.assertFalse(load(path).windows_core_audio)
        for suffix in (
            "[compat.windows.core_audio]\nenabled=true\n",
            '[audio]\nenabled=true\n[compat.windows.core_audio]\nenabled="true"\n',
        ):
            path.write_text(body + suffix)
            with self.assertRaises(BridgeError):
                load(path)
        path.write_text(body + "[audio]\nenabled=true\n[compat.windows.core_audio]\nenabled=true\n")
        self.assertTrue(load(path).windows_core_audio)
        self.assertFalse(load(path).audio.allow_output_write)
        self.assertFalse(load(path).audio.allow_input_write)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_library_requires_private_regular_file_and_owned_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            library = com.library_path(data)
            library.parent.mkdir(parents=True)
            library.write_bytes(b"MZ synthetic library")
            library.chmod(0o600)
            manifest = data / "install.json"
            manifest.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "files": {str(library): hashlib.sha256(library.read_bytes()).hexdigest()},
                    }
                )
            )
            manifest.chmod(0o600)
            self.assertEqual(runtime.installed_library(data, data), library)
            library.write_bytes(b"MZ changed")
            with self.assertRaisesRegex(RuntimeError, "hash"):
                runtime.installed_library(data, data)
            library.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "ownership"):
                runtime.installed_library(data, data)

    async def test_service_failure_is_fixed_and_closes_listener(self):
        config = Config(Path("/prefix"), Path("/app.exe"), Path("/wine"), False, {}, {})
        status = {}
        closed = False

        @asynccontextmanager
        async def endpoint(*args, on_failure, **kwargs):
            nonlocal closed
            asyncio.get_running_loop().call_soon(on_failure)
            try:
                yield 1845, {"monitor_failed": True}
            finally:
                closed = True

        with (
            patch.object(runtime, "installed_library", return_value=Path("/library")),
            patch.object(runtime, "endpoint_server", side_effect=endpoint),
        ):
            await asyncio.wait_for(runtime.run(config, object(), status), 2)
        self.assertTrue(closed)
        self.assertFalse(status["listening"])
        self.assertEqual(status["error"], "core_audio_monitor_failed")
