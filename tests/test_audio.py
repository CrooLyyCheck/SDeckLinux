from __future__ import annotations

import dataclasses
import json
import math
import unittest
from unittest.mock import AsyncMock, patch

from deckbridge.backends.audio.model import balanced_channels, group_sessions
from deckbridge.backends.audio.pipewire import AudioBackend, sessions_from_graph
from deckbridge.compat.plugins.volume_controller.protocol import Router
from deckbridge.protocol import BridgeError


def graph(serial=10, cookie=100):
    return [
        {"id": 0, "type": "PipeWire:Interface:Core", "info": {"cookie": cookie}},
        {
            "id": 42,
            "type": "PipeWire:Interface:Node",
            "info": {
                "props": {
                    "object.serial": serial,
                    "media.class": "Stream/Output/Audio",
                    "application.name": "Test player żółć",
                    "application.process.id": 183,
                    "application.process.binary": "test-player",
                    "pipewire.access.portal.app_id": "org.example.Player",
                },
                "params": {"Props": [{"channelVolumes": [0.125, 0.015625], "mute": False}]},
            },
        },
    ]


def pulse(serial=10, index=10):
    return [
        {
            "index": index,
            "properties": {"object.serial": str(serial)},
            "mute": False,
            "volume": {"front-left": {"value": 32768}, "front-right": {"value": 16384}},
        }
    ]


def prepared_backend(write=False):
    backend = AudioBackend(write)
    backend.sessions = sessions_from_graph(graph(), pulse(), 100)
    backend.applications = group_sessions(backend.sessions)
    backend.cookie = 100
    backend.ready.set()
    return backend


class AudioModelTests(unittest.TestCase):
    def test_real_schema_id_and_native_volume_mapping(self):
        session = sessions_from_graph(graph(), pulse(), 100)[0]
        self.assertEqual(session.id, "pw:100:10")
        self.assertEqual(session.volume, 0.5)
        self.assertEqual(session.flatpak_id, "org.example.Player")
        native = sessions_from_graph(graph(), [], 100)[0]
        self.assertIsNone(native.pulse_index)
        self.assertEqual(native.channels, (32768, 16384))

    def test_logical_grouping_does_not_merge_namespaced_pid_collisions(self):
        first = sessions_from_graph(graph(), pulse(), 100)[0]
        second = dataclasses.replace(
            first, id="pw:100:11", serial=11, reported_pid=999, channels=(16384, 8192), mute=True
        )
        other = dataclasses.replace(
            first, id="pw:100:12", serial=12, application_key="flatpak:org.example.Other"
        )
        groups = group_sessions([first, second, other])
        self.assertEqual(len(groups), 2)
        player = next(g for g in groups if g["id"] == first.application_key)
        self.assertEqual(len(player["sessions"]), 2)
        self.assertTrue(player["mixed_mute"])
        self.assertFalse(player["mute"])
        self.assertEqual(player["volume"], 0.5)

    def test_channel_balance_bounds_and_zero(self):
        self.assertEqual(balanced_channels((32768, 16384), 0.25), ["16384", "8192"])
        self.assertEqual(balanced_channels((0, 0), 0.5), ["32768", "32768"])
        for value in (True, -1, 1.1, math.nan, math.inf, "50"):
            with self.subTest(value=value), self.assertRaises(BridgeError):
                balanced_channels((65536,), value)

    def test_invalid_snapshots_fail_explicitly(self):
        for objects, controls in (
            ({}, []),
            ([None], []),
            (graph(), [None]),
            (graph(), pulse(index=-1)),
        ):
            with self.assertRaises(BridgeError):
                sessions_from_graph(objects, controls, 100)


class AudioMutationTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_graph_tool_reports_failure_instead_of_hanging_readiness(self):
        backend = AudioBackend()
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            await backend.run()
        self.assertTrue(backend.ready.is_set())
        with self.assertRaisesRegex(BridgeError, "audio_backend_failed"):
            await backend.snapshot()

    async def test_disabled_and_unallowlisted_targets_never_call_external_tools(self):
        backend = prepared_backend()
        with patch("deckbridge.backends.audio.pipewire.command", new_callable=AsyncMock) as command:
            with self.assertRaisesRegex(BridgeError, "audio_write_disabled"):
                await backend.set_target(backend.applications[0]["id"], volume=0.5)
            backend.allow_write = True
            backend.allowed_apps = ("app:another",)
            with self.assertRaisesRegex(BridgeError, "audio_write_disabled"):
                await backend.set_target(backend.sessions[0].id, volume=0.5)
            command.assert_not_called()

    async def test_old_serial_or_server_epoch_never_targets_reused_node(self):
        for fresh in (graph(serial=99), graph(cookie=101)):
            backend = prepared_backend(True)
            with patch(
                "deckbridge.backends.audio.pipewire.command",
                new_callable=AsyncMock,
                side_effect=[fresh, pulse()],
            ) as command:
                with self.assertRaisesRegex(BridgeError, "audio_stream_gone"):
                    await backend.set_target(backend.sessions[0].id, volume=0.5)
                self.assertEqual(command.await_count, 2)

    async def test_only_exact_stream_ids_are_mutated_and_verified(self):
        backend = prepared_backend(True)
        with (
            patch(
                "deckbridge.backends.audio.pipewire.command",
                new_callable=AsyncMock,
                side_effect=[graph(), pulse(), None, graph()],
            ) as command,
            patch.object(backend, "refresh", new_callable=AsyncMock),
        ):
            result = await backend.set_target(backend.sessions[0].id, volume=0.25)
        self.assertEqual(result["stream_count"], 1)
        self.assertEqual(
            command.await_args_list[2].args,
            ("/usr/bin/pactl", "set-sink-input-volume", "10", "16384", "8192"),
        )

    async def test_native_only_streams_and_vanished_apps_fail(self):
        backend = prepared_backend(True)
        backend.sessions = [dataclasses.replace(backend.sessions[0], pulse_index=None)]
        with self.assertRaisesRegex(BridgeError, "audio_stream_read_only"):
            await backend.set_target(backend.sessions[0].id, mute=True)
        with self.assertRaisesRegex(BridgeError, "audio_application_gone"):
            await backend.set_target("missing", mute=True)


class RouterContractTests(unittest.IsolatedAsyncioTestCase):
    async def rpc(self, router, method, params=None):
        request = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            request["params"] = params
        return await router.request(json.dumps(request))

    async def test_original_client_enumeration_and_fallback_image_contract(self):
        backend = prepared_backend()
        router = Router(backend)
        self.assertEqual(
            (await self.rpc(router, "getApplicationInstanceCount"))["result"], {"count": 1}
        )
        app = (await self.rpc(router, "getApplicationInstanceAtIndex", {"index": 0}))["result"]
        self.assertEqual(app["volume"], 0.5)
        self.assertEqual(app["activity"], 2)
        self.assertEqual(app["displayName"], "Test player żółć")
        image = await self.rpc(
            router,
            "getApplicationInstanceImage",
            {"processID": app["processID"], "imageSize": 262244},
        )
        self.assertIsNone(image["result"]["image"])

    async def test_no_global_volume_or_arbitrary_shell(self):
        router = Router(prepared_backend(True))
        for method in (
            "setSystemDefaultDeviceVolume",
            "setSystemDefaultDeviceMute",
            "shell.execute",
        ):
            response = await self.rpc(router, method, {"processID": 0, "volume": 10})
            self.assertIn("error", response)

    async def test_plugin_scalar_is_preserved_through_a_five_point_button_step(self):
        backend = prepared_backend(True)
        router = Router(backend)
        await self.rpc(router, "getApplicationInstanceCount")
        with patch.object(
            backend, "set_target", new_callable=AsyncMock, return_value={"status": "applied"}
        ) as action:
            # The observed client adds step/100 to its current scalar (0..1).
            app = (await self.rpc(router, "getApplicationInstanceAtIndex", {"index": 0}))["result"]
            stepped = round(app["volume"] - 5 / 100, 2)
            await self.rpc(
                router, "setApplicationInstanceVolume", {"processID": 1, "volume": stepped}
            )
        action.assert_awaited_once_with("flatpak:org.example.Player", volume=0.45)

    async def test_removed_ids_are_not_reused_and_events_have_real_contract_names(self):
        backend = prepared_backend()
        router = Router(backend)
        _, old = router.notifications({})
        backend.applications[0]["volume"] = 0.25
        events, old = router.notifications(old)
        self.assertEqual(events[0]["method"], "preferredSessionInstanceVolumeChanged")
        self.assertEqual(events[0]["params"]["volume"], 0.25)
        backend.applications = []
        events, _ = router.notifications(old)
        self.assertEqual(events[0]["params"]["appAddedRemoved"], "Removed")
        self.assertIsNone(router.by_id(1))

    async def test_system_notifications_are_read_only_and_use_scalars(self):
        backend = prepared_backend()
        router = Router(backend)
        _, old = router.notifications({})
        backend.system = {"volume": 0.65, "mute": True}
        events, _ = router.notifications(old)
        self.assertEqual(
            [(e["method"], e["params"]) for e in events],
            [
                ("currentSystemDefaultDeviceVolumeChanged", {"processID": 0, "volume": 0.65}),
                ("currentSystemDefaultDeviceMuteChanged", {"processID": 0, "mute": True}),
            ],
        )

    async def test_malformed_and_nan_requests_are_errors_without_payload_echo(self):
        router = Router(prepared_backend())
        for raw in (
            '{"jsonrpc":"2.0","id":true,"method":"x"}',
            '{"jsonrpc":"2.0","id":1,"method":"x","params":{"volume":NaN}}',
            '{"id":1,"id":2}',
            "SYNTHETICSECRET",
            "x" * 17000,
        ):
            response = await router.request(raw)
            self.assertIn("error", response)
            self.assertNotIn("SYNTHETICSECRET", json.dumps(response))
