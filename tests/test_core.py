from __future__ import annotations

import asyncio
import dataclasses
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from deckbridge.config import Config, load
from deckbridge.protocol import MAX_FRAME, BridgeError, decode_request, encode
from deckbridge.providers import execute
from deckbridge.uri import from_desktop, validate_deep_link, validate_url
from deckbridge.wine import forward, run_bounded, running_instances
from tools.install import MIME, default_line, quote_exec, replace_default


def config(prefix: Path) -> Config:
    return Config(
        prefix,
        prefix / "drive_c/Program Files/Elgato/StreamDeck/StreamDeck.exe",
        Path("/usr/bin/wine"),
        True,
        {"editor": ("/usr/bin/kate",)},
        {"docs": "https://docs.elgato.com/streamdeck/"},
    )


class URITests(unittest.TestCase):
    def test_observed_kde_percent_u_transport(self):
        pretty = (
            "streamdeck://plugins/message/com.example/a b%2Fc%25%2B%22%5C"
            "?probe=a%26b%3Dc+z&state=ż#zażółć"
        )
        encoded = (
            "streamdeck://plugins/message/com.example/a%20b%2Fc%25%2B%22%5C"
            "?probe=a%26b%3Dc+z&state=%C5%BC#za%C5%BC%C3%B3%C5%82%C4%87"
        )
        self.assertEqual(from_desktop(pretty), encoded)
        self.assertEqual(from_desktop(encoded), encoded)
        with self.assertRaises(BridgeError):
            from_desktop("streamdeck://x/\nsecret")

    def test_preserves_full_uri(self):
        values = [
            "streamdeck://plugins/message/com.example.plugin/callback?code=a%26b%2Fc&state=x+y#%23",
            "streamdeck://oauth?code=%25%252F&state=%C5%BC%C3%B3%C5%82%C4%87#fragment",
            "STREAMDECK://plugins/message/com.example.plugin/zażółć?x=%22%5C%00",
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(validate_deep_link(value), value)

    def test_rejects_malformed_unsafe_or_wrong_scheme(self):
        values = [
            None,
            [],
            "",
            "https://example.com",
            "streamdeck://",
            "streamdeck://x:123",
            "streamdeck://user:pass@x",
            "streamdeck://x/abc%",
            "streamdeck://x/%zz",
            "streamdeck://x/\nsecret",
            'streamdeck://x/"arg',
            "streamdeck://x/\\",
            "streamdeck://x/\ud800",
            "streamdeck://x/" + "a" * 8192,
        ]
        for value in values:
            with self.subTest(value=repr(value)[:80]), self.assertRaises(BridgeError):
                validate_deep_link(value)

    def test_native_url_policy(self):
        self.assertEqual(
            validate_url("https://example.com/?a=%26#x"), "https://example.com/?a=%26#x"
        )
        for value in ("file:///etc/passwd", "javascript:alert(1)", "streamdeck://x"):
            with self.assertRaises(BridgeError):
                validate_url(value)


class ProtocolTests(unittest.TestCase):
    def test_valid_contract(self):
        req = decode_request(
            encode({"v": 1, "id": "abc-123", "method": "capabilities.list", "params": {}})
        )
        self.assertEqual((req.id, req.method, req.params), ("abc-123", "capabilities.list", {}))

    def test_invalid_contract(self):
        obj = {"v": 1, "id": "abc", "method": "actions.execute", "params": {}}
        values = [
            b"{}",
            b"[]\n",
            b"{invalid}\n",
            b"x" * (MAX_FRAME + 1),
            b'{"v":1,"v":2,"id":"x","method":"diagnostics.get","params":{}}\n',
        ]
        for key, value in (
            ("v", True),
            ("v", 1.0),
            ("v", 2),
            ("id", "x\nsecret"),
            ("method", []),
            ("method", "shell.execute"),
            ("params", []),
        ):
            values.append(encode({**obj, key: value}))
        for value in values:
            with self.subTest(value=value[:80]), self.assertRaises(BridgeError):
                decode_request(value)


class WineProcessTests(unittest.TestCase):
    def test_exact_executable_and_prefix_even_with_renamed_main_thread(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = config(root / "prefix")
            for pid, exe, prefix in (
                ("10", str(cfg.executable), cfg.prefix),
                ("20", str(cfg.executable), root / "other"),
                ("30", str(root / "unrelated/StreamDeck.exe"), cfg.prefix),
                ("40", r"C:\Program Files\Elgato\StreamDeck\StreamDeck.exe", cfg.prefix),
                ("50", str(cfg.executable).swapcase(), cfg.prefix),
            ):
                proc = root / pid
                proc.mkdir()
                (proc / "cmdline").write_bytes(os.fsencode(exe) + b"\0")
                (proc / "comm").write_text("CrBrowserMain\n")
                (proc / "environ").write_bytes(b"WINEPREFIX=" + os.fsencode(prefix) + b"\0")
            self.assertEqual(running_instances(cfg, root), [10, 40])


class ActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_hung_real_helper_is_bounded_and_reaped(self):
        with patch("deckbridge.wine.ACTION_TIMEOUT", 0.05):
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(
                    run_bounded([sys.executable, "-c", "import signal; signal.pause()"]),
                    timeout=2,
                )

    async def test_exact_uri_is_one_wine_argument(self):
        cfg = config(Path("/audited/prefix"))
        uri = "streamdeck://plugins/message/com.example/auth?code=a%26b&state=%25#x"
        with (
            patch("deckbridge.wine.running_instances", return_value=[42]),
            patch("deckbridge.wine.run_bounded", new_callable=AsyncMock) as run,
        ):
            result = await forward(cfg, uri)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/wine", str(cfg.executable), uri])
        self.assertEqual(run.call_args.kwargs["env"]["WINEPREFIX"], str(cfg.prefix))
        self.assertFalse(result["application_ack"])

    async def test_missing_ambiguous_and_disabled_never_launch(self):
        cfg = config(Path("/audited/prefix"))
        for instances in ([], [1, 2]):
            with (
                patch("deckbridge.wine.running_instances", return_value=instances),
                patch("deckbridge.wine.run_bounded", new_callable=AsyncMock) as run,
            ):
                with self.assertRaises(BridgeError):
                    await forward(cfg, "streamdeck://oauth?code=synthetic")
                run.assert_not_called()
        with self.assertRaisesRegex(BridgeError, "capability_disabled"):
            await forward(dataclasses.replace(cfg, deep_links=False), "streamdeck://oauth")

    async def test_native_mappings_and_no_arbitrary_argv(self):
        cfg = config(Path("/audited/prefix"))
        with patch("deckbridge.providers.run_bounded", new_callable=AsyncMock) as run:
            await execute(cfg, {"capability": "desktop.launch", "arguments": {"target": "editor"}})
            self.assertEqual(run.call_args.args[0][-2:], ["--", "/usr/bin/kate"])
            await execute(cfg, {"capability": "desktop.openUrl", "arguments": {"target": "docs"}})
            self.assertEqual(run.call_args.args[0][-2:], ["/usr/bin/xdg-open", cfg.urls["docs"]])
            for params in (
                {"capability": "desktop.launch", "arguments": {"target": "/bin/sh"}},
                {
                    "capability": "desktop.launch",
                    "arguments": {"target": "editor", "argv": ["secret"]},
                },
                {"capability": "shell.execute", "arguments": {"command": "sh"}},
            ):
                with self.assertRaises(BridgeError):
                    await execute(cfg, params)
            self.assertEqual(run.await_count, 2)


class ConfigTests(unittest.TestCase):
    def test_private_versioned_explicit_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            body = (
                'version = 1\n[wine]\nprefix="/prefix"\n'
                'executable="/prefix/drive_c/StreamDeck.exe"\ncommand="/usr/bin/wine"\n'
                "[features]\ndeep_links=false\n"
            )
            path.write_text(body)
            path.chmod(0o600)
            self.assertFalse(load(path).deep_links)
            path.chmod(0o644)
            with self.assertRaisesRegex(BridgeError, "config_not_private"):
                load(path)
            path.chmod(0o600)
            for changed in (
                body.replace("version = 1", "version = true"),
                body.replace("/prefix/drive_c/StreamDeck.exe", "/other/StreamDeck.exe"),
                body + '[applications]\nbad=["relative.exe"]\n',
            ):
                path.write_text(changed)
                with self.assertRaises(BridgeError):
                    load(path)


class MIMEEditTests(unittest.TestCase):
    def test_roundtrip_preserves_unrelated_changes(self):
        original = (
            "# comment\n[Default Applications]\ntext/plain=kate.desktop;\n"
            + MIME
            + "=previous.desktop;\n"
        )
        old = default_line(original)
        installed = replace_default(original, MIME + "=io.deckbridge.UrlHandler.desktop;\n")
        changed = installed.replace("kate.desktop", "kwrite.desktop")
        restored = replace_default(changed, old)
        self.assertEqual(restored, original.replace("kate.desktop", "kwrite.desktop"))

    def test_missing_default_key_removed_without_overwriting_other_sections(self):
        original = "[Added Associations]\ntext/plain=kate.desktop;\n"
        installed = replace_default(original, MIME + "=io.deckbridge.UrlHandler.desktop;\n")
        restored = replace_default(installed, None)
        self.assertNotIn(MIME, restored)
        self.assertIn(original, restored)

    def test_duplicate_key_rejected(self):
        with self.assertRaises(RuntimeError):
            default_line(f"[Default Applications]\n{MIME}=a\n{MIME}=b\n")

    def test_exec_path_quoting(self):
        self.assertEqual(quote_exec('/path with space/100%/"x'), '"/path with space/100%%/\\"x"')
