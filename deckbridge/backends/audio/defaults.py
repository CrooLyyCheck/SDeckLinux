"""Native default-output selection, independent of volume and Windows roles."""

from __future__ import annotations

from ...protocol import BridgeError
from .command import command
from .devices import DeviceBackend


class DefaultOutputBackend:
    def __init__(self, devices: DeviceBackend, *, allow_write=False, allowed_targets=()):
        self.devices = devices
        self.allow_write = allow_write
        self.allowed_targets = tuple(allowed_targets)

    async def set_target(self, target: str) -> dict:
        if not isinstance(target, str) or not target:
            raise BridgeError("invalid_params")
        if not self.allow_write or (self.allowed_targets and target not in self.allowed_targets):
            raise BridgeError("audio_default_write_disabled")
        async with self.devices.lock:
            before = await self.devices.inventory()
            selected = next((d for d in before if d.id == target and d.direction == "output"), None)
            previous = next((d for d in before if d.direction == "output" and d.default), None)
            if selected is None or selected.monitor:
                raise BridgeError("audio_device_gone")
            if previous is None:
                raise BridgeError("audio_default_changed")
            current = await self.devices.inventory()
            candidate = next((d for d in current if d.id == target), None)
            active = next((d for d in current if d.direction == "output" and d.default), None)
            if (
                candidate is None
                or candidate.identity != selected.identity
                or active is None
                or active.identity != previous.identity
            ):
                raise BridgeError("audio_default_changed")
            if active.id == target:
                return {"status": "already_applied", "device": candidate.describe()}
            await command(
                "/usr/bin/pactl", "set-default-sink", str(selected.index), json_output=False
            )
            observed = next(
                (d for d in await self.devices.inventory() if d.id == target and d.default), None
            )
            if observed is None or observed.identity != selected.identity:
                raise BridgeError("audio_default_outcome_unknown")
            return {"status": "applied", "device": observed.describe()}
