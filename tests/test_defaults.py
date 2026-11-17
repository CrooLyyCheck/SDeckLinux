"""Default-output routing policy on synthetic endpoints; no host routing changes."""

import dataclasses
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from deckbridge.backends.audio.defaults import DefaultOutputBackend
from deckbridge.backends.audio.devices import DeviceBackend
from deckbridge.config import load
from deckbridge.protocol import BridgeError
from tests.test_devices import device


def other():
    return dataclasses.replace(
        device(), id="pulse:output:epoch:100", name="other", index=13, serial=100, default=False
    )


class DefaultOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_and_unallowlisted_never_observe_or_write(self):
        backend = DeviceBackend(allow_input=True, allow_output=True)
        with patch.object(backend, "inventory", new_callable=AsyncMock) as inventory:
            for policy in (
                DefaultOutputBackend(backend),
                DefaultOutputBackend(backend, allow_write=True, allowed_targets=("different",)),
            ):
                with self.assertRaisesRegex(BridgeError, "audio_default_write_disabled"):
                    await policy.set_target(other().id)
            inventory.assert_not_called()

    async def test_exact_named_output_revalidated_and_verified_without_volume_commands(self):
        backend = DeviceBackend()
        before = [device(), other()]
        after = [
            dataclasses.replace(device(), default=False),
            dataclasses.replace(other(), default=True),
        ]
        with (
            patch.object(
                backend, "inventory", new_callable=AsyncMock, side_effect=[before, before, after]
            ),
            patch("deckbridge.backends.audio.defaults.command", new_callable=AsyncMock) as command,
        ):
            result = await DefaultOutputBackend(backend, allow_write=True).set_target(other().id)
            self.assertEqual(result["status"], "applied")
            command.assert_awaited_once_with(
                "/usr/bin/pactl", "set-default-sink", "13", json_output=False
            )

    async def test_already_selected_is_verified_noop(self):
        backend = DeviceBackend()
        with (
            patch.object(
                backend, "inventory", new_callable=AsyncMock, return_value=[device(), other()]
            ),
            patch("deckbridge.backends.audio.defaults.command", new_callable=AsyncMock) as command,
        ):
            result = await DefaultOutputBackend(backend, allow_write=True).set_target(device().id)
            self.assertEqual(result["status"], "already_applied")
            command.assert_not_called()

    async def test_reused_target_or_changed_previous_default_prevents_write(self):
        before = [device(), other()]
        for current in (
            [device()],
            [device(), dataclasses.replace(other(), index=99)],
            [dataclasses.replace(device(), id="changed-epoch"), other()],
            [
                dataclasses.replace(device(), default=False),
                dataclasses.replace(other(), default=True),
            ],
        ):
            backend = DeviceBackend()
            with (
                patch.object(
                    backend, "inventory", new_callable=AsyncMock, side_effect=[before, current]
                ),
                patch(
                    "deckbridge.backends.audio.defaults.command", new_callable=AsyncMock
                ) as command,
            ):
                with self.assertRaisesRegex(BridgeError, "audio_default_changed"):
                    await DefaultOutputBackend(backend, allow_write=True).set_target(other().id)
                command.assert_not_called()

    async def test_unverified_outcome_is_never_retried_or_restored_automatically(self):
        backend = DeviceBackend()
        with (
            patch.object(
                backend, "inventory", new_callable=AsyncMock, return_value=[device(), other()]
            ),
            patch("deckbridge.backends.audio.defaults.command", new_callable=AsyncMock) as command,
        ):
            with self.assertRaisesRegex(BridgeError, "audio_default_outcome_unknown"):
                await DefaultOutputBackend(backend, allow_write=True).set_target(other().id)
            self.assertEqual(command.await_count, 1)

    async def test_input_and_gone_targets_are_rejected_before_commands(self):
        backend = DeviceBackend()
        with (
            patch.object(
                backend,
                "inventory",
                new_callable=AsyncMock,
                return_value=[device(), dataclasses.replace(other(), direction="input")],
            ),
            patch("deckbridge.backends.audio.defaults.command", new_callable=AsyncMock) as command,
        ):
            for target in (other().id, "missing"):
                with self.assertRaisesRegex(BridgeError, "audio_device_gone"):
                    await DefaultOutputBackend(backend, allow_write=True).set_target(target)
            command.assert_not_called()

    async def test_configuration_requires_explicit_audio_and_core_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            base = (
                'version=1\n[wine]\nprefix="/prefix"\nexecutable="/prefix/drive_c/app.exe"\n'
                'command="/usr/bin/wine"\n[features]\ndeep_links=true\n'
            )
            for suffix in (
                "[audio]\nallow_default_output_write=true\n",
                '[audio]\nenabled=true\nallow_default_output_write="true"\n',
                "[audio]\nenabled=true\n[compat.windows.core_audio]\ndefault_output=true\n",
            ):
                path.write_text(base + suffix)
                path.chmod(0o600)
                with self.assertRaises(BridgeError):
                    load(path)
            path.write_text(
                base + "[audio]\nenabled=true\nallow_output_write=true\nallow_system_write=true\n"
            )
            self.assertFalse(load(path).audio.allow_default_output_write)
            self.assertFalse(load(path).windows_default_output)
            path.write_text(
                base + "[audio]\nenabled=true\nallow_default_output_write=true\n"
                'allowed_default_outputs=["output-id"]\n[compat.windows.core_audio]\n'
                "enabled=true\ndefault_output=true\n"
            )
            cfg = load(path)
            self.assertTrue(cfg.windows_default_output)
            self.assertTrue(cfg.audio.allow_default_output_write)
            self.assertEqual(cfg.audio.allowed_default_outputs, ("output-id",))
