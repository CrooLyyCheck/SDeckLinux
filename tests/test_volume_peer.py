import json
import os
import tempfile
import unittest
from pathlib import Path

from deckbridge.compat.plugins.volume_controller.peer import (
    authenticate,
    matching_inodes,
    plugin_pids,
)
from tests.test_core import config


class VolumePeerTests(unittest.TestCase):
    def test_tcp_tuple_and_uid_must_match(self):
        line = f"0: 0100007F:ABCD 0100007F:0734 01 0:0 0:0 0 {os.getuid()} 0 12345"
        table = "header\n" + line
        self.assertEqual(matching_inodes(table, 0xABCD, 1844, os.getuid()), {"12345"})
        self.assertEqual(matching_inodes(table, 0xABCE, 1844, os.getuid()), set())
        self.assertEqual(matching_inodes(table, 0xABCD, 1844, os.getuid() + 1), set())

    def test_only_exact_version_prefix_script_and_socket_owner_are_authenticated(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            cfg = config(base / "prefix")
            root = (
                cfg.prefix
                / "drive_c/users/test/AppData/Roaming/Elgato/StreamDeck/Plugins"
                / "com.elgato.volume-controller.sdPlugin"
            )
            node = root.parents[1] / "NodeJS/20.20.2/node.exe"
            proc = base / "proc/123"
            (proc / "fd").mkdir(parents=True)
            (base / "proc/net").mkdir()
            (base / "proc/net/tcp").write_text(
                f"header\n0: 0100007F:ABCD 0100007F:0734 01 0:0 0:0 0 {os.getuid()} 0 12345\n"
            )
            args = [
                str(node),
                "--no-global-search-paths",
                str(root / "bin/plugin.js"),
                "-info",
                json.dumps(
                    {"plugin": {"uuid": "com.elgato.volume-controller", "version": "2.0.5.201"}}
                ),
            ]
            (proc / "cmdline").write_bytes(b"\0".join(os.fsencode(a) for a in args) + b"\0")
            (proc / "environ").write_bytes(b"WINEPREFIX=" + os.fsencode(cfg.prefix) + b"\0")
            (proc / "fd/3").symlink_to("socket:[12345]")
            self.assertEqual(plugin_pids(cfg, root, base / "proc"), [123])
            self.assertEqual(
                authenticate(cfg, root, ("127.0.0.1", 0xABCD), proc_root=base / "proc"), 123
            )
            self.assertIsNone(authenticate(cfg, root, ("127.0.0.1", 1), proc_root=base / "proc"))
            (proc / "environ").write_bytes(b"WINEPREFIX=/other-prefix\0")
            self.assertIsNone(
                authenticate(cfg, root, ("127.0.0.1", 0xABCD), proc_root=base / "proc")
            )
