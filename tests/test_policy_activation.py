"""Policy COM install/rollback with a synthetic registry, never real Wine."""

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deckbridge.compat.windows import registry
from deckbridge.compat.windows.core_audio import policy_activation as policy


class PolicyActivationTests(unittest.TestCase):
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
        self.keys = {}
        self.manifest = {"files": {}}
        self.events = []
        self.fail_after_default = False
        mock = patch.object(registry, "reg", side_effect=self.reg)
        mock.start()
        self.addCleanup(mock.stop)

    def reg(self, prefix, args):
        self.assertEqual(prefix, self.prefix)
        self.assertIn("backup", self.events)
        op, key = args[:2]
        self.assertIn(key, (policy.KEY, policy.CLASS))
        name = "default" if "/ve" in args else args[args.index("/v") + 1] if "/v" in args else None
        if op == "query":
            if key not in self.keys:
                return 1, b""
            if name:
                value = self.keys[key].get(name)
                if value is None:
                    return (
                        (0, b"    (Default)    REG_SZ    (value not set)\r\n")
                        if name == "default"
                        else (1, b"")
                    )
                return 0, f"    {name}    REG_SZ    {value}\r\n".encode()
            lines = []
            for path, values in sorted(self.keys.items()):
                if path == key or path.startswith(key + "\\"):
                    lines.append(path.replace("HKLM\\", "HKEY_LOCAL_MACHINE\\", 1))
                    lines.extend(f"    {n}    REG_SZ    {v}" for n, v in values.items())
            return 0, "\r\n".join(lines).encode()
        self.assertIn(policy.MANAGED, self.manifest)
        if op == "add":
            self.assertEqual(self.manifest[policy.MANAGED]["phase"], "pending")
            self.keys.setdefault(policy.CLASS, {})
            self.keys.setdefault(policy.KEY, {})[name] = args[args.index("/d") + 1]
            if name == "default" and self.fail_after_default:
                return 1, b""
        elif name:
            self.keys[key].pop(name)
        else:
            for path in list(self.keys):
                if path == key or path.startswith(key + "\\"):
                    del self.keys[path]
        return 0, b""

    def backup(self, kind, content):
        self.assertEqual(content, b"fixture")
        self.events.append("backup")

    def save(self):
        self.events.append(copy.deepcopy(self.manifest))

    def sync(self, enabled=True, shared=True):
        policy.synchronize(
            self.prefix,
            self.data,
            enabled,
            self.manifest,
            self.save,
            self.backup,
            shared_enabled=shared,
        )

    def test_apply_idempotent_update_and_exact_absence_restored(self):
        self.sync()
        self.assertEqual(self.keys[policy.KEY], policy.desired(self.data))
        self.assertEqual(self.events[1][policy.MANAGED]["phase"], "pending")
        self.sync()
        self.sync(False)
        self.assertEqual(self.keys, {})
        self.assertNotIn(policy.MANAGED, self.manifest)

    def test_unknown_existing_registration_is_preserved(self):
        self.keys = {
            policy.CLASS: {},
            policy.KEY: {"default": r"C:\Other\policy.dll", "ThreadingModel": "Both"},
        }
        before = copy.deepcopy(self.keys)
        with self.assertRaisesRegex(RuntimeError, "preserved"):
            self.sync()
        self.assertEqual(self.keys, before)
        self.assertNotIn(policy.MANAGED, self.manifest)

    def test_partial_write_can_resume_or_restore(self):
        self.fail_after_default = True
        with self.assertRaisesRegex(RuntimeError, "unverified"):
            self.sync()
        self.assertEqual(self.manifest[policy.MANAGED]["phase"], "pending")
        self.fail_after_default = False
        self.sync()
        self.assertEqual(self.keys[policy.KEY], policy.desired(self.data))
        self.sync(False)
        self.assertEqual(self.keys, {})

    def test_existing_empty_keys_and_foreign_metadata_are_not_deleted(self):
        self.keys = {policy.CLASS: {"UserMetadata": "keep"}, policy.KEY: {}}
        before = copy.deepcopy(self.keys)
        self.sync()
        self.sync(False)
        self.assertEqual(self.keys, before)

    def test_user_override_and_shared_library_remain_owned_until_full_deactivation(self):
        self.sync()
        self.keys[policy.KEY]["default"] = r"C:\User\custom.dll"
        library = policy.library_path(self.data)
        self.manifest["files"] = {str(library): "hash", str(library.with_suffix(".token")): "hash"}
        before = copy.deepcopy(self.keys)
        self.sync(False)
        self.assertEqual(self.keys, before)
        self.assertIn(policy.MANAGED, self.manifest)
        self.assertIn(str(library), self.manifest["files"])
        self.sync(False, shared=False)
        self.assertEqual(self.keys, before)
        self.assertNotIn(policy.MANAGED, self.manifest)
        self.assertEqual(self.manifest["files"], {})
