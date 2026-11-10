"""Core Audio framing/policy on synthetic endpoints; no Wine or audio execution."""

import asyncio
import dataclasses
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from deckbridge.backends.audio.devices import DeviceBackend
from deckbridge.compat.windows.core_audio import transport as rpc
from tests.test_devices import device


class CoreAudioDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, backend, op=0, flow=0, name=b"speaker", value=0):
        header = rpc.REQUEST.pack(rpc.MAGIC, op, flow, len(name), value, rpc.NULL_CONTEXT)
        return rpc.RESPONSE.unpack(await rpc.dispatch(backend, header, name))

    async def test_reads_scalar_channels_and_default_alias(self):
        backend = DeviceBackend()
        with patch.object(backend, "inventory", new_callable=AsyncMock, return_value=[device()]):
            for name in (b"speaker", b""):
                frame = await self.request(backend, name=name)
                self.assertEqual(frame[:5], (rpc.MAGIC, 0, 1, 0, 2))
                self.assertEqual(frame[5:7], (1, 0.5))

    async def test_unknown_name_does_not_guess_and_flow_is_separate(self):
        backend = DeviceBackend()
        with patch.object(backend, "inventory", new_callable=AsyncMock, return_value=[device()]):
            self.assertEqual((await self.request(backend, name=b"Fixture"))[1], rpc.E_FAIL)
            self.assertEqual((await self.request(backend, flow=1))[1], rpc.E_FAIL)

    async def test_disabled_device_writes_are_denied(self):
        backend = DeviceBackend()
        with patch.object(backend, "inventory", new_callable=AsyncMock, return_value=[device()]):
            for op in (1, 2):
                result = await self.request(backend, op=op, value=0.25 if op == 1 else 1)
                self.assertEqual(result[1], rpc.E_ACCESSDENIED)

    async def test_mutation_maps_to_exact_native_id_and_scalar(self):
        backend = DeviceBackend()
        with (
            patch.object(backend, "inventory", new_callable=AsyncMock, return_value=[device()]),
            patch.object(backend, "set_target", new_callable=AsyncMock) as setter,
        ):
            self.assertEqual((await self.request(backend, op=1, value=0.25))[1], 0)
            setter.assert_awaited_once_with(device().id, volume=0.25)

    async def test_invalid_frames_never_reach_backend(self):
        backend = DeviceBackend()
        cases = (
            (9, 0, b"speaker", 0),
            (0, 2, b"speaker", 0),
            (0, 0, b"\xff", 0),
            (0, 0, b"nul\0", 0),
            (1, 0, b"speaker", math.nan),
            (1, 0, b"speaker", 1.1),
            (2, 0, b"speaker", 0.5),
        )
        with patch.object(backend, "inventory", new_callable=AsyncMock) as inventory:
            for op, flow, name, value in cases:
                self.assertEqual(
                    (await self.request(backend, op, flow, name, value))[1], rpc.E_INVALIDARG
                )
            inventory.assert_not_called()


class CoreAudioSocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.library = Path(self.temp.name) / "bridge.dll"
        self.library.write_bytes(b"synthetic module")
        self.backend = DeviceBackend()
        self.queue = asyncio.Queue()

        class Process:
            returncode = None

            def __init__(obj, queue):
                obj.stdout = type("Stdout", (), {"readline": lambda s: queue.get()})()

            def kill(obj):
                obj.returncode = -9

            async def wait(obj):
                return obj.returncode

        for mock in (
            patch.object(
                self.backend, "inventory", new_callable=AsyncMock, return_value=[device()]
            ),
            patch.object(
                rpc.asyncio,
                "create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=Process(self.queue),
            ),
            patch.object(rpc, "authorized_peer", return_value=True),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    async def test_handshake_and_real_socket_read(self):
        async with rpc.endpoint_server(Path("/prefix"), self.library, self.backend, port=0) as (
            port,
            stats,
        ):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            hello = await asyncio.wait_for(reader.readexactly(36), 2)
            self.assertEqual(hello, rpc.MAGIC + self.library.with_suffix(".token").read_bytes())
            writer.write(rpc.REQUEST.pack(rpc.MAGIC, 0, 0, 7, 0, rpc.NULL_CONTEXT) + b"speaker")
            await writer.drain()
            frame = rpc.RESPONSE.unpack(
                await asyncio.wait_for(reader.readexactly(rpc.RESPONSE.size), 2)
            )
            self.assertEqual(frame[1], 0)
            self.assertEqual(stats["reads"], 1)
            self.assertEqual(stats["writes"], 0)
            writer.close()
            await writer.wait_closed()

    async def test_rejected_peer_gets_no_token_or_backend_access(self):
        with patch.object(rpc, "authorized_peer", return_value=False):
            async with rpc.endpoint_server(Path("/prefix"), self.library, self.backend, port=0) as (
                port,
                stats,
            ):
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
                self.assertEqual(stats["rejected"], 1)
                self.backend.inventory.assert_not_called()
                writer.close()
                await writer.wait_closed()

    async def test_oversized_request_is_closed_without_dispatch(self):
        async with rpc.endpoint_server(Path("/prefix"), self.library, self.backend, port=0) as (
            port,
            stats,
        ):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.wait_for(reader.readexactly(36), 2)
            writer.write(rpc.REQUEST.pack(rpc.MAGIC, 0, 0, 4097, 0, rpc.NULL_CONTEXT))
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
            self.backend.inventory.assert_not_called()
            writer.close()
            await writer.wait_closed()

    async def test_subscription_receives_native_changes_and_closes_on_monitor_loss(self):
        async with rpc.endpoint_server(Path("/prefix"), self.library, self.backend, port=0) as (
            port,
            stats,
        ):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.wait_for(reader.readexactly(36), 2)
            writer.write(rpc.REQUEST.pack(rpc.MAGIC, 3, 0, 7, 0, rpc.NULL_CONTEXT) + b"speaker")
            await writer.drain()
            await asyncio.wait_for(reader.readexactly(rpc.RESPONSE.size), 2)
            self.backend.inventory.return_value = [
                dataclasses.replace(device(), channels=(16384, 8192))
            ]
            await self.queue.put(b"Event 'change' on sink #12\n")
            frame = rpc.RESPONSE.unpack(
                await asyncio.wait_for(reader.readexactly(rpc.RESPONSE.size), 2)
            )
            self.assertEqual(frame[2], 0.25)
            self.assertEqual(stats["subscribers"], 1)
            await self.queue.put(b"")
            self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
            self.assertTrue(stats["monitor_failed"])
            writer.close()
            await writer.wait_closed()

    async def test_setter_notifies_named_and_default_alias_once_with_context(self):
        context = bytes(range(16))

        async def change(target, **values):
            self.assertEqual(target, device().id)
            self.assertEqual(values, {"volume": 0.25})
            self.backend.inventory.return_value = [
                dataclasses.replace(device(), channels=(16384, 8192))
            ]

        async with rpc.endpoint_server(Path("/prefix"), self.library, self.backend, port=0) as (
            port,
            stats,
        ):
            subscriptions = []
            for name in (b"speaker", b""):
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                await asyncio.wait_for(reader.readexactly(36), 2)
                writer.write(
                    rpc.REQUEST.pack(rpc.MAGIC, 3, 0, len(name), 0, rpc.NULL_CONTEXT) + name
                )
                await writer.drain()
                await asyncio.wait_for(reader.readexactly(rpc.RESPONSE.size), 2)
                subscriptions.append((reader, writer))
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.wait_for(reader.readexactly(36), 2)
            with patch.object(self.backend, "set_target", side_effect=change):
                writer.write(rpc.REQUEST.pack(rpc.MAGIC, 1, 0, 7, 0.25, context) + b"speaker")
                await writer.drain()
                result = rpc.RESPONSE.unpack(
                    await asyncio.wait_for(reader.readexactly(rpc.RESPONSE.size), 2)
                )
                self.assertEqual(result[-1], context)
            for subscriber, _ in subscriptions:
                event = rpc.RESPONSE.unpack(
                    await asyncio.wait_for(subscriber.readexactly(rpc.RESPONSE.size), 2)
                )
                self.assertEqual((event[2], event[-1]), (0.25, context))
            await self.queue.put(b"Event 'change' on sink #12\n")
            # The corresponding Pulse event must not duplicate the setter notification.
            for subscriber, _ in subscriptions:
                with self.assertRaises(TimeoutError):
                    await asyncio.wait_for(subscriber.readexactly(rpc.RESPONSE.size), 0.04)
            self.backend.inventory.return_value = [dataclasses.replace(device(), mute=True)]
            await self.queue.put(b"Event 'change' on sink #12\n")
            for subscriber, _ in subscriptions:
                event = rpc.RESPONSE.unpack(
                    await asyncio.wait_for(subscriber.readexactly(rpc.RESPONSE.size), 2)
                )
                self.assertEqual((event[3], event[-1]), (1, rpc.NULL_CONTEXT))
            self.assertEqual(stats["writes"], 1)
            for _, connection in [*subscriptions, (reader, writer)]:
                connection.close()
                await connection.wait_closed()

    async def test_failed_monitor_refuses_new_registration(self):
        async with rpc.endpoint_server(Path("/prefix"), self.library, self.backend, port=0) as (
            port,
            stats,
        ):
            await self.queue.put(b"")
            for _ in range(100):
                if stats["monitor_failed"]:
                    break
                await asyncio.sleep(0)
            self.assertTrue(stats["monitor_failed"])
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.wait_for(reader.readexactly(36), 2)
            writer.write(rpc.REQUEST.pack(rpc.MAGIC, 3, 0, 7, 0, rpc.NULL_CONTEXT) + b"speaker")
            await writer.drain()
            result = rpc.RESPONSE.unpack(
                await asyncio.wait_for(reader.readexactly(rpc.RESPONSE.size), 2)
            )
            self.assertEqual(result[1], rpc.E_FAIL)
            self.assertEqual(stats["subscribers"], 0)
            writer.close()
            await writer.wait_closed()


class CoreAudioPeerTests(unittest.TestCase):
    def test_requires_socket_owner_prefix_and_exact_mapped_module(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            library = root / "bridge.dll"
            library.write_bytes(b"fixture")
            proc = root / "proc"
            (proc / "net").mkdir(parents=True)
            pid = proc / "123"
            (pid / "fd").mkdir(parents=True)
            (proc / "net/tcp").write_text(
                "header\n0: 0100007F:1234 0100007F:2345 01 0 0 0 " + str(os.getuid()) + " 0 555\n"
            )
            (pid / "fd/3").symlink_to("socket:[555]")
            (pid / "environ").write_bytes(b"WINEPREFIX=/prefix\0")
            maps = f"1000-2000 r--p 00000000 00:00 {library.stat().st_ino} {library}\n"
            (pid / "maps").write_text(maps)
            self.assertTrue(
                rpc.authorized_peer(Path("/prefix"), library, ("127.0.0.1", 0x1234), 0x2345, proc)
            )
            self.assertFalse(
                rpc.authorized_peer(Path("/other"), library, ("127.0.0.1", 0x1234), 0x2345, proc)
            )
            (pid / "maps").write_text(maps.replace(str(library), str(root / "other.dll")))
            self.assertFalse(
                rpc.authorized_peer(Path("/prefix"), library, ("127.0.0.1", 0x1234), 0x2345, proc)
            )

    def test_unsafe_token_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            library = Path(folder) / "bridge.dll"
            path = library.with_suffix(".token")
            path.write_bytes(b"x" * 32)
            path.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "Unsafe"):
                rpc.private_token(library)
            self.assertEqual(path.read_bytes(), b"x" * 32)
