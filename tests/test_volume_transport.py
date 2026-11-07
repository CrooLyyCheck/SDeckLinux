import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError, InvalidStatus

from deckbridge.compat.plugins.volume_controller.server import run_adapter
from tests.test_audio import prepared_backend
from tests.test_core import config


class VolumeTransportTests(unittest.IsolatedAsyncioTestCase):
    async def start(self, accepted):
        backend = prepared_backend()
        listening = asyncio.Event()

        def log(event, *args, **kwargs):
            if event == "volume_controller_listening":
                listening.set()

        patches = [
            patch(
                "deckbridge.compat.plugins.volume_controller.server.verify_plugin",
                return_value=Path("/fixture"),
            ),
            patch(
                "deckbridge.compat.plugins.volume_controller.server.authenticate",
                return_value=123 if accepted else None,
            ),
            patch("deckbridge.server.log", side_effect=log),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        task = asyncio.create_task(run_adapter(config(Path("/fixture-prefix")), backend, port=0))

        async def stop():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        self.addAsyncCleanup(stop)
        async with asyncio.timeout(2):
            await listening.wait()
        return backend, f"ws://127.0.0.1:{backend.adapter_status['port']}/"

    async def test_authorized_client_contract_and_disabled_mutation(self):
        backend, uri = await self.start(True)
        async with connect(uri, proxy=None) as connection:
            await connection.send(
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getApplicationInstanceCount"})
            )
            self.assertEqual(json.loads(await connection.recv())["result"], {"count": 1})
            await connection.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "getApplicationInstanceAtIndex",
                        "params": {"index": 0},
                    }
                )
            )
            app = json.loads(await connection.recv())["result"]
            self.assertEqual(app["displayName"], "Test player żółć")
            await connection.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "setApplicationInstanceVolume",
                        "params": {"processID": app["processID"], "volume": 25},
                    }
                )
            )
            self.assertEqual(
                json.loads(await connection.recv())["error"]["message"], "audio_write_disabled"
            )
        self.assertEqual(backend.adapter_status["enumerated_applications"], 1)

    async def test_unattributed_native_peer_rejected(self):
        _, uri = await self.start(False)
        with self.assertRaises(InvalidStatus) as caught:
            async with connect(uri, proxy=None):
                self.fail("Unauthenticated peer accepted")
        self.assertEqual(caught.exception.response.status_code, 403)

    async def test_browser_origin_rejected_even_with_matching_process(self):
        _, uri = await self.start(True)
        with self.assertRaises(InvalidStatus) as caught:
            async with connect(uri, origin="https://example.com", proxy=None):
                self.fail("Browser origin accepted")
        self.assertEqual(caught.exception.response.status_code, 403)

    async def test_backend_failure_closes_connection_without_leaving_a_stale_ui(self):
        backend, uri = await self.start(True)
        async with connect(uri, proxy=None) as connection:
            # Start the request loop before failing the notification backend.
            await connection.send(
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getApplicationInstanceCount"})
            )
            await connection.recv()
            backend.failure = "audio_backend_disconnected"
            async with backend.changed:
                backend.revision += 1
                backend.changed.notify_all()
            with self.assertRaises(ConnectionClosedError) as caught:
                async with asyncio.timeout(2):
                    await connection.recv()
            self.assertEqual(caught.exception.rcvd.code, 1011)
