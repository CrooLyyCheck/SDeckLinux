"""Endpoint identities, policy and writes using synthetic native audio data."""

import dataclasses
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from deckbridge.backends.audio.devices import DeviceBackend, from_pulse
from deckbridge.backends.audio.pipewire import AudioBackend
from deckbridge.config import load
from deckbridge.protocol import BridgeError
from deckbridge.providers import execute
from tests.test_core import config


def info():
    return {
        "cookie": "epoch",
        "server_name": "PulseAudio (on PipeWire fixture)",
        "default_sink_name": "speaker",
        "default_source_name": "microphone",
    }


def endpoint(name="speaker", serial="99", index=12):
    return {
        "name": name,
        "index": index,
        "properties": {"object.serial": serial},
        "description": "Fixture",
        "mute": False,
        "volume": {"left": {"value": 65536}, "right": {"value": 32768}},
    }


def device():
    return from_pulse(info(), [endpoint()], [])[0]


class DeviceModelTests(unittest.TestCase):
    def test_input_output_default_and_channels_have_native_identities(self):
        devices = from_pulse(info(), [endpoint()], [endpoint("microphone", "100")])
        self.assertEqual([d.direction for d in devices], ["output", "input"])
        self.assertTrue(all(d.default for d in devices))
        self.assertNotEqual(devices[0].id, devices[1].id)
        self.assertEqual(devices[0].channels, (65536, 32768))
        self.assertEqual(devices[0].volume, 1)

    def test_server_and_serial_changes_produce_new_ids(self):
        original = device()
        self.assertNotEqual(
            original.id, from_pulse(dict(info(), cookie="new"), [endpoint()], [])[0].id
        )
        self.assertNotEqual(original.id, from_pulse(info(), [endpoint(serial="100")], [])[0].id)

    def test_invalid_and_duplicate_snapshots_fail(self):
        for entries in (
            [endpoint(index=True)],
            [endpoint(serial=False)],
            [dict(endpoint(), mute=1)],
            [dict(endpoint(), volume={})],
            [dict(endpoint(), name="bad\x00name")],
            [dict(endpoint(), volume={"x": {"value": True}})],
            [endpoint(), endpoint()],
        ):
            with self.subTest(entries=entries), self.assertRaises(BridgeError):
                from_pulse(info(), entries, [])

    def test_monitor_is_separate_from_physical_input(self):
        monitor = dict(endpoint("monitor"), monitor_of_sink=0)
        self.assertTrue(from_pulse(info(), [], [monitor])[0].monitor)
        normal = dict(endpoint("microphone"), monitor_of_sink=4294967295)
        self.assertFalse(from_pulse(info(), [], [normal])[0].monitor)


class DeviceWriteTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_gates_never_call_external_tools(self):
        with patch("deckbridge.backends.audio.devices.command", new_callable=AsyncMock) as cmd:
            with self.assertRaisesRegex(BridgeError, "audio_device_write_disabled"):
                await DeviceBackend().set_target(device().id, volume=0.25)
            cmd.assert_not_called()

    async def test_volume_preserves_balance_and_verifies_exact_endpoint(self):
        before = device()
        after = dataclasses.replace(before, channels=(16384, 8192))
        backend = DeviceBackend(allow_output=True)
        with (
            patch.object(
                backend,
                "inventory",
                new_callable=AsyncMock,
                side_effect=[[before], [before], [after]],
            ),
            patch("deckbridge.backends.audio.devices.command", new_callable=AsyncMock) as cmd,
        ):
            result = await backend.set_target(before.id, volume=0.25)
            cmd.assert_awaited_once_with(
                "/usr/bin/pactl", "set-sink-volume", "12", "16384", "8192", json_output=False
            )
            self.assertEqual(result["status"], "applied")

    async def test_input_requires_its_own_permission_and_uses_source_command(self):
        before = dataclasses.replace(device(), direction="input")
        for enabled in (False, True):
            backend = DeviceBackend(allow_output=True, allow_input=enabled)
            with (
                patch.object(
                    backend,
                    "inventory",
                    new_callable=AsyncMock,
                    side_effect=[[before], [before], [dataclasses.replace(before, mute=True)]],
                ),
                patch("deckbridge.backends.audio.devices.command", new_callable=AsyncMock) as cmd,
            ):
                if enabled:
                    await backend.set_target(before.id, mute=True)
                    cmd.assert_awaited_once_with(
                        "/usr/bin/pactl", "set-source-mute", "12", "1", json_output=False
                    )
                else:
                    with self.assertRaisesRegex(BridgeError, "audio_device_write_disabled"):
                        await backend.set_target(before.id, mute=True)
                    cmd.assert_not_called()

    async def test_reused_handle_changed_state_and_disappearance_prevent_write(self):
        before = device()
        for current in (
            None,
            dataclasses.replace(before, index=13),
            dataclasses.replace(before, channels=(32768, 16384)),
            dataclasses.replace(before, mute=True),
        ):
            backend = DeviceBackend(allow_output=True)
            with (
                patch.object(
                    backend,
                    "inventory",
                    new_callable=AsyncMock,
                    side_effect=[[before], [current] if current else []],
                ),
                patch("deckbridge.backends.audio.devices.command", new_callable=AsyncMock) as cmd,
            ):
                with self.assertRaisesRegex(BridgeError, "audio_device_changed"):
                    await backend.set_target(before.id, volume=0.25)
                cmd.assert_not_called()

    async def test_unverified_write_reports_unknown_and_is_not_retried(self):
        before = device()
        backend = DeviceBackend(allow_output=True)
        with (
            patch.object(backend, "inventory", new_callable=AsyncMock, return_value=[before]),
            patch("deckbridge.backends.audio.devices.command", new_callable=AsyncMock) as cmd,
        ):
            with self.assertRaisesRegex(BridgeError, "audio_device_outcome_unknown"):
                await backend.set_target(before.id, volume=0.25)
            self.assertEqual(cmd.await_count, 1)

    async def test_monitor_and_unallowlisted_targets_cannot_be_written(self):
        for before, allowed in (
            (dataclasses.replace(device(), monitor=True), ()),
            (device(), ("other",)),
        ):
            backend = DeviceBackend(allow_output=True, allowed_devices=allowed)
            with (
                patch.object(backend, "inventory", new_callable=AsyncMock, return_value=[before]),
                patch("deckbridge.backends.audio.devices.command", new_callable=AsyncMock) as cmd,
            ):
                with self.assertRaisesRegex(BridgeError, "audio_device_write_disabled"):
                    await backend.set_target(before.id, mute=True)
                cmd.assert_not_called()

    async def test_invalid_scalar_and_mute_never_write(self):
        backend = DeviceBackend(allow_output=True)
        for kwargs in ({"volume": math.nan}, {"volume": 1.1}, {"volume": True}, {"mute": 1}):
            with (
                patch.object(backend, "inventory", new_callable=AsyncMock, return_value=[device()]),
                patch("deckbridge.backends.audio.devices.command", new_callable=AsyncMock) as cmd,
            ):
                with self.assertRaises(BridgeError):
                    await backend.set_target(device().id, **kwargs)
                cmd.assert_not_called()

    async def test_server_restart_during_inventory_is_rejected(self):
        with patch(
            "deckbridge.backends.audio.devices.command",
            new_callable=AsyncMock,
            side_effect=[info(), [endpoint()], [], dict(info(), cookie="new")],
        ):
            with self.assertRaisesRegex(BridgeError, "audio_device_changed"):
                await DeviceBackend().inventory()

    async def test_device_provider_is_separate_from_session_and_system_policy(self):
        backend = AudioBackend(allow_write=True, allow_system_write=True)
        self.assertFalse(backend.devices.allow_output)
        self.assertFalse(backend.devices.allow_input)
        with patch.object(
            backend.devices, "snapshot", new_callable=AsyncMock, return_value={"devices": []}
        ) as snapshot:
            result = await execute(
                config(Path("/fixture")),
                {"capability": "audio.devices.list", "arguments": {}},
                audio=backend,
            )
            self.assertEqual(result, {"devices": []})
            snapshot.assert_awaited_once()

    async def test_config_device_policy_is_independent_and_strict(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            base = (
                'version=1\n[wine]\nprefix="/prefix"\nexecutable="/prefix/drive_c/app.exe"\n'
                'command="/usr/bin/wine"\n[features]\ndeep_links=true\n'
            )
            path.write_text(base + "[audio]\nenabled=true\nallow_system_write=true\n")
            path.chmod(0o600)
            cfg = load(path)
            self.assertFalse(cfg.audio.allow_output_write)
            self.assertFalse(cfg.audio.allow_input_write)
            path.write_text(
                base
                + '[audio]\nenabled=true\nallow_input_write=true\nallowed_devices=["fixture"]\n'
            )
            self.assertTrue(load(path).audio.allow_input_write)
            self.assertEqual(load(path).audio.allowed_devices, ("fixture",))
            path.write_text(base + '[audio]\nenabled=true\nallow_input_write="true"\n')
            with self.assertRaises(BridgeError):
                load(path)
