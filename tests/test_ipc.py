"""Real Unix socket integration; no Wine, hardware, desktop or audio mutations."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deckbridge.client import call
from deckbridge.protocol import MAX_FRAME, BridgeError
from deckbridge.server import Server, lock_socket
from tests.test_core import config


class IPCTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "control.sock"
        self.logs = io.StringIO()
        self.redirect = contextlib.redirect_stderr(self.logs)
        self.redirect.__enter__()
        self.handler = Server(config(Path(self.temp.name) / "prefix"))
        self.server = await asyncio.start_unix_server(
            self.handler.handle, path=str(self.path), limit=MAX_FRAME
        )
        self.path.chmod(0o600)

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        for task in tuple(self.handler.clients):
            task.cancel()
        await asyncio.gather(*tuple(self.handler.clients), return_exceptions=True)
        self.redirect.__exit__(None, None, None)
        self.temp.cleanup()

    async def exchange(self, payload: bytes) -> dict:
        reader, writer = await asyncio.open_unix_connection(str(self.path))
        try:
            writer.write(payload)
            await writer.drain()
            async with asyncio.timeout(2):
                return json.loads(await reader.readline())
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_discovery_and_reconnection(self):
        for _ in range(2):
            result = await call(self.path, "capabilities.list", {})
            self.assertEqual(result["capabilities"][0]["name"], "oauth.deepLink")
            self.assertFalse(result["events"]["supported"])

    async def test_invalid_payload_does_not_leak_or_crash(self):
        secret = "SYNTHETIC-OAUTH-SECRET"  # noqa: S105 - deliberate redaction-test sentinel
        for payload in (
            b"{broken " + secret.encode() + b"}\n",
            b"x" * (MAX_FRAME + 100) + b"\n",
            json.dumps(
                {
                    "v": 1,
                    "id": "safe",
                    "method": "actions.execute",
                    "params": {
                        "capability": "oauth.deepLink",
                        "arguments": {"uri": "streamdeck://x/\ud800"},
                    },
                }
            ).encode()
            + b"\n",
        ):
            reply = await self.exchange(payload)
            self.assertIn("error", reply)
            self.assertNotIn(secret, json.dumps(reply))
        self.assertNotIn(secret, self.logs.getvalue())
        self.assertIn("capabilities", await call(self.path, "capabilities.list", {}))

    async def test_client_rejects_invalid_responses_and_arbitrary_error_text(self):
        path = self.path.with_name("malformed.sock")
        for fields in (
            {"v": True, "result": {}},
            {"error": {"code": "SYNTHETICSECRET"}},
            {"result": {}, "error": {"code": "invalid_frame"}},
        ):

            async def reply(reader, writer, fields=fields):
                request = json.loads(await reader.readline())
                writer.write(json.dumps({"v": 1, "id": request["id"], **fields}).encode() + b"\n")
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            fake = await asyncio.start_unix_server(reply, path=str(path))
            try:
                with self.assertRaisesRegex(BridgeError, "invalid_response"):
                    await call(path, "capabilities.list", {})
            finally:
                fake.close()
                await fake.wait_closed()
                path.unlink(missing_ok=True)

    async def test_unknown_command_has_no_fallback(self):
        result = await self.exchange(b'{"v":1,"id":"safe","method":"shell.execute","params":{}}\n')
        self.assertEqual(result["error"]["code"], "unsupported_method")

    async def test_client_frame_deadline(self):
        with patch("deckbridge.server.IO_TIMEOUT", 0.02):
            reader, writer = await asyncio.open_unix_connection(str(self.path))
            try:
                async with asyncio.timeout(2):
                    reply = json.loads(await reader.readline())
                self.assertEqual(reply["error"]["code"], "timeout_outcome_unknown")
            finally:
                writer.close()
                await writer.wait_closed()

    async def test_partial_frame_is_rejected(self):
        reader, writer = await asyncio.open_unix_connection(str(self.path))
        try:
            writer.write(b'{"v":1')
            await writer.drain()
            writer.write_eof()
            async with asyncio.timeout(2):
                reply = json.loads(await reader.readline())
            self.assertEqual(reply["error"]["code"], "invalid_frame")
        finally:
            writer.close()
            await writer.wait_closed()


class SocketOwnershipTests(unittest.TestCase):
    def test_public_directory_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root / "public"
            directory.mkdir(mode=0o755)
            directory.chmod(0o755)
            with self.assertRaisesRegex(BridgeError, "socket_directory_unsafe"):
                lock_socket(directory / "control.sock")
            private = root / "private"
            private.mkdir(mode=0o700)
            target = root / "user-data"
            target.write_text("preserve")
            (private / "control.sock").symlink_to(target)
            with self.assertRaisesRegex(BridgeError, "socket_path_unsafe"):
                lock_socket(private / "control.sock")
            self.assertEqual(target.read_text(), "preserve")

    def test_single_daemon_lock_and_regular_file_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "deckbridge/control.sock"
            fd = lock_socket(path)
            try:
                with self.assertRaisesRegex(BridgeError, "daemon_already_running"):
                    lock_socket(path)
            finally:
                os.close(fd)
            path.write_text("user data")
            with self.assertRaisesRegex(BridgeError, "socket_path_unsafe"):
                lock_socket(path)
            self.assertEqual(path.read_text(), "user data")
