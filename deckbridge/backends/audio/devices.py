"""Native input/output endpoints; no Windows IDs or plugin wire fields."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass

from ...protocol import BridgeError
from .command import command
from .model import balanced_channels


@dataclass(frozen=True)
class Device:
    id: str
    direction: str
    name: str
    description: str
    serial: int
    index: int
    channels: tuple[int, ...]
    mute: bool
    default: bool
    monitor: bool

    @property
    def volume(self) -> float:
        return max(self.channels) / 65536

    @property
    def identity(self) -> tuple:
        return self.id, self.name, self.index

    def describe(self) -> dict:
        return {**asdict(self), "volume": self.volume}


def from_pulse(info: dict, sinks: list, sources: list) -> list[Device]:
    if not isinstance(info, dict) or not str(info.get("server_name", "")).startswith(
        "PulseAudio (on PipeWire "
    ):
        raise BridgeError("pipewire_pulse_required")
    cookie = info.get("cookie")
    if type(cookie) not in (int, str) or not str(cookie) or len(str(cookie)) > 128:
        raise BridgeError("audio_invalid_snapshot")
    devices = []
    for direction, entries, default in (
        ("output", sinks, info.get("default_sink_name")),
        ("input", sources, info.get("default_source_name")),
    ):
        if not isinstance(entries, list) or len(entries) > 128:
            raise BridgeError("audio_invalid_snapshot")
        for item in entries:
            try:
                name, index = item["name"], item["index"]
                serial = item["properties"]["object.serial"]
                channels = tuple(v["value"] for v in item["volume"].values())
                mute = item["mute"]
                if (
                    not isinstance(name, str)
                    or not name
                    or len(name) > 4096
                    or "\x00" in name
                    or type(index) is not int
                    or index < 0
                    or type(serial) not in (str, int)
                    or not str(serial).isdigit()
                    or not 1 <= len(channels) <= 64
                    or any(type(v) is not int or not 0 <= v < 2**31 for v in channels)
                    or type(mute) is not bool
                ):
                    raise BridgeError("audio_invalid_snapshot")
                monitor = direction == "input" and (
                    item["properties"].get("device.class") == "monitor"
                    or item.get("monitor_of_sink") not in (None, 4294967295, "4294967295")
                )
                devices.append(
                    Device(
                        f"pulse:{direction}:{cookie}:{int(serial)}",
                        direction,
                        name,
                        str(item.get("description") or name)[:256],
                        int(serial),
                        index,
                        channels,
                        mute,
                        name == default,
                        monitor,
                    )
                )
            except (KeyError, TypeError, AttributeError, ValueError):
                raise BridgeError("audio_invalid_snapshot") from None
    if len({d.id for d in devices}) != len(devices) or len(
        {(d.direction, d.name) for d in devices}
    ) != len(devices):
        raise BridgeError("audio_invalid_snapshot")
    return devices


class DeviceBackend:
    def __init__(
        self,
        *,
        allow_output: bool = False,
        allow_input: bool = False,
        allowed_devices: tuple[str, ...] = (),
    ):
        self.allow_output, self.allow_input = allow_output, allow_input
        self.allowed_devices = allowed_devices
        self.lock = asyncio.Lock()

    async def inventory(self) -> list[Device]:
        before = await command("/usr/bin/pactl", "-f", "json", "info")
        sinks = await command("/usr/bin/pactl", "-f", "json", "list", "sinks")
        sources = await command("/usr/bin/pactl", "-f", "json", "list", "sources")
        after = await command("/usr/bin/pactl", "-f", "json", "info")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise BridgeError("audio_invalid_snapshot")
        if any(
            before.get(k) != after.get(k)
            for k in ("cookie", "default_sink_name", "default_source_name")
        ):
            raise BridgeError("audio_device_changed")
        return from_pulse(after, sinks, sources)

    async def snapshot(self) -> dict:
        devices = await self.inventory()
        return {
            "version": 1,
            "devices": [d.describe() for d in devices],
            "output_write_enabled": self.allow_output,
            "input_write_enabled": self.allow_input,
        }

    async def set_target(self, target: str, *, volume=None, mute=None) -> dict:
        if not isinstance(target, str) or not target:
            raise BridgeError("invalid_params")
        if not (self.allow_input or self.allow_output):
            raise BridgeError("audio_device_write_disabled")
        if (volume is None) == (mute is None) or (mute is not None and type(mute) is not bool):
            raise BridgeError("invalid_params")
        async with self.lock:
            device = next((d for d in await self.inventory() if d.id == target), None)
            if device is None:
                raise BridgeError("audio_device_gone")
            if (
                not (self.allow_output if device.direction == "output" else self.allow_input)
                or device.monitor
                or (self.allowed_devices and device.id not in self.allowed_devices)
            ):
                raise BridgeError("audio_device_write_disabled")
            values = balanced_channels(device.channels, volume) if volume is not None else []
            current = next((d for d in await self.inventory() if d.id == target), None)
            if current is None or current.identity != device.identity:
                raise BridgeError("audio_device_changed")
            # A concurrent desktop volume change must not be overwritten with an old balance.
            if current.channels != device.channels or current.mute != device.mute:
                raise BridgeError("audio_device_changed")
            kind = "sink" if device.direction == "output" else "source"
            await command(
                "/usr/bin/pactl",
                f"set-{kind}-volume" if volume is not None else f"set-{kind}-mute",
                str(device.index),
                *(values if volume is not None else ["1" if mute else "0"]),
                json_output=False,
            )
            observed = next((d for d in await self.inventory() if d.id == target), None)
            if observed is None or observed.identity != device.identity:
                raise BridgeError("audio_device_outcome_unknown")
            if (volume is not None and observed.channels != tuple(int(v) for v in values)) or (
                mute is not None and observed.mute != mute
            ):
                raise BridgeError("audio_device_outcome_unknown")
            return {"status": "applied", "device": observed.describe()}
