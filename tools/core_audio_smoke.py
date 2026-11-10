#!/usr/bin/env python3
"""Native COM observations; fixture writes require separate explicit approval."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import re
import stat
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deckbridge.backends.audio.devices import DeviceBackend  # noqa: E402
from deckbridge.client import call  # noqa: E402
from deckbridge.compat.plugins.volume_controller.peer import verify_plugin  # noqa: E402
from deckbridge.compat.windows.core_audio.transport import endpoint_server  # noqa: E402
from deckbridge.compat.windows.registry import owned_prefix, reg, snapshot  # noqa: E402
from deckbridge.config import default_config, load, socket_path  # noqa: E402
from deckbridge.protocol import BridgeError  # noqa: E402
from tools.audio_smoke import APPLICATION, pulse_state, state_directory, verify_isolation  # noqa: E402
from tools.install import atomic, private_backup  # noqa: E402


async def observe(*, _backend=None, _on_ready=None) -> dict:
    config = load(default_config())
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    state = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "deckbridge"
    if not owned_prefix(config.prefix, data):
        raise RuntimeError("Unsupported Wine prefix")
    library = ROOT / ".local/native/deckbridge-core-audio.dll"
    probe = ROOT / ".local/native/core_audio_probe.exe"
    for path in (library, probe):
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_size > 16 * 1024 * 1024
            or info.st_mode & 0o022
        ):
            raise RuntimeError("Unsafe native build artifact")
    await asyncio.to_thread(snapshot, config.prefix, lambda k, v: private_backup(state, k, v))
    directory = state / "diagnostics"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix="core-audio-", suffix=".json", dir=directory)
    os.close(fd)
    report = Path(name)
    backend = _backend or DeviceBackend()  # All input/output writes remain disabled.
    if backend.allow_input or backend.allow_output:
        raise RuntimeError("Observation requires disabled device writes")
    emitter = None
    try:
        async with endpoint_server(config.prefix, library, backend, port=0) as (port, stats):
            if _on_ready:
                emitter = asyncio.create_task(_on_ready(stats))
            process = await asyncio.create_subprocess_exec(
                "/usr/bin/wine",
                str(probe),
                "Z:" + str(report),
                "Z:" + str(library),
                *(["--wait-notify"] if _on_ready else []),
                env=dict(
                    os.environ,
                    WINEPREFIX=str(config.prefix),
                    WINEARCH="win64",
                    WINEDEBUG="-all",
                    WINEDLLOVERRIDES="winemenubuilder.exe=d",
                    DECKBRIDGE_CORE_AUDIO_PORT=str(port),
                ),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                async with asyncio.timeout(55):
                    code = await process.wait()
            except (TimeoutError, asyncio.CancelledError):
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise
            raw = await asyncio.to_thread(report.read_bytes)
            if not 0 < len(raw) < 16384:
                raise RuntimeError("Native observation unavailable")
            result = json.loads(raw)
            if (
                code
                or not result.get("lifetime_ok")
                or result.get("devices") != result.get("readable")
                or result.get("identity_checks") != result.get("devices")
                or result.get("callback_checks") != result.get("devices")
                or not result.get("callback_data_valid")
                or (_on_ready is not None and not result.get("notification_observed"))
                or result.get("setters_called") != 0
                or stats["writes"]
                or stats["rejected"]
                or stats["reads"] != 3 * result.get("devices", 0)
            ):
                raise RuntimeError("Native observation failed")
            evidence = {"result": result, "transport": dict(stats)}
            await asyncio.to_thread(
                atomic,
                directory
                / (
                    "core-audio-simulated-notifications.json"
                    if _on_ready
                    else "core-audio-com-bridge.json"
                ),
                json.dumps(evidence, indent=2).encode(),
            )
            return evidence
    finally:
        if emitter:
            emitter.cancel()
            await asyncio.gather(emitter, return_exceptions=True)
        await asyncio.to_thread(report.unlink, missing_ok=True)


async def observe_notification_contract() -> dict:
    """Exercise real Windows callbacks against memory-only models; no host setter."""
    backend = DeviceBackend()
    devices = await backend.inventory()
    inventory = AsyncMock(return_value=devices)
    queue = asyncio.Queue()
    real_create_process = asyncio.create_subprocess_exec

    class Process:
        returncode = None

        def __init__(self):
            self.stdout = type("Stdout", (), {"readline": lambda _: queue.get()})()

        def kill(self):
            self.returncode = -9

        async def wait(self):
            return self.returncode

    async def create_process(*args, **kwargs):
        if args == ("/usr/bin/pactl", "subscribe"):
            return Process()
        return await real_create_process(*args, **kwargs)

    async def emit(stats):
        async with asyncio.timeout(15):
            for _ in range(1500):
                if stats["subscribers"]:
                    break
                await asyncio.sleep(0.01)
            else:
                raise RuntimeError("Native callback did not subscribe")
            inventory.return_value = [
                dataclasses.replace(
                    d,
                    channels=tuple((32768 if d.volume != 0.5 else 16384) for _ in d.channels),
                )
                for d in devices
            ]
            await queue.put(b"Event 'change' on sink #0\n")

    with (
        patch.object(backend, "inventory", inventory),
        patch.object(asyncio, "create_subprocess_exec", side_effect=create_process),
    ):
        result = await observe(_backend=backend, _on_ready=emit)
    return dict(result, synthetic_native_state=True)


async def exercise_original_addon(approved: bool) -> dict:
    if not approved:
        raise RuntimeError("Original-addon device writes require explicit approval")
    config = load(default_config())
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "deckbridge"
    descriptor = state_directory() / "audio-fixture.json"
    metadata = descriptor.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
        or metadata.st_size > 16384
    ):
        raise RuntimeError("Unsafe fixture descriptor")
    fixture = json.loads(descriptor.read_bytes())
    name = fixture.get("virtual_sink")
    if (
        fixture.get("application") != APPLICATION
        or not fixture.get("hardware_isolated")
        or not isinstance(name, str)
        or not re.fullmatch(r"deckbridge_test_[0-9]+_[0-9a-f]+", name)
    ):
        raise RuntimeError("Expected owned silent fixture")

    async def isolated():
        inventory = await call(
            socket_path(),
            "actions.execute",
            {
                "capability": "audio.sessions.list",
                "arguments": {},
            },
        )
        app = next((a for a in inventory["applications"] if a["id"] == APPLICATION), None)
        if app is None:
            raise RuntimeError("Fixture disappeared")
        await verify_isolation(app, name)

    await isolated()
    await observe()  # Wine enumeration assigns the new fixture's backend GUID before lookup.
    backend = DeviceBackend()
    target = next(
        (d for d in await backend.inventory() if d.direction == "output" and d.name == name), None
    )
    if (
        target is None
        or target.default
        or target.monitor
        or not 0 <= target.volume <= 1
        or len(set(target.channels)) != 1
    ):
        raise RuntimeError("Unexpected fixture output")
    root = verify_plugin(config)
    library = ROOT / ".local/native/deckbridge-core-audio.dll"
    bootstrap = ROOT / ".local/native/core-audio-bootstrap.node"
    await asyncio.to_thread(snapshot, config.prefix, lambda k, v: private_backup(state, k, v))
    key = r"HKCU\Software\Wine\Drivers\winepulse.drv\devices\0," + name
    code, raw = await asyncio.to_thread(reg, config.prefix, ["query", key, "/v", "guid"])
    match = re.search(rb"guid\s+REG_BINARY\s+([0-9A-Fa-f]{32})", raw)
    if code or match is None:
        raise RuntimeError("Wine fixture identity unavailable")
    guid = str(uuid.UUID(bytes_le=bytes.fromhex(match[1].decode("ascii"))))
    backend.allow_output = True
    backend.allowed_devices = (target.id,)
    streams_before, sinks_before = await asyncio.to_thread(pulse_state)
    from deckbridge.backends.audio.command import command

    info_before = await command("/usr/bin/pactl", "-f", "json", "info")
    if any(
        info_before.get(k) != fixture["baseline_defaults"].get(k)
        for k in ("default_sink_name", "default_source_name")
    ):
        raise RuntimeError("Default audio changed since fixture creation")
    fd, filename = tempfile.mkstemp(
        prefix="original-addon-", suffix=".json", dir=state / "diagnostics"
    )
    os.close(fd)
    report = Path(filename)
    addon = "C:/" + str(
        (root / "bin/addons/winAudioDeviceService.node").relative_to(config.prefix / "drive_c")
    )
    script = """let a,d,original,result={},code=0;
try {require(BOOTSTRAP);if(process.env.DECKBRIDGE_CORE_AUDIO_ACTIVE!=='1')throw Error();
a=require(ADDON);d=a.getDevices().find(x=>x.dataFlow==='output'&&x.id.toLowerCase().endsWith('{'+GUID+'}'));
if(!d)throw Error();original={volume:d.volume,mute:d.isMuted};
a.setDeviceVolume(d.id,0.25);let v=a.getDeviceById(d.id);
result.volume_25_percent_verified=Math.abs(v.volume-0.25)<1/65536;
a.setDeviceMute(d.id,true);result.mute_verified=a.getDeviceById(d.id).isMuted===true;
} catch(e){result.operation_failed=true;code=1;}
finally {if(d&&original){try{
a.setDeviceVolume(d.id,original.volume);a.setDeviceMute(d.id,original.mute);
let v=a.getDeviceById(d.id);
result.fixture_restored=Math.abs(v.volume-original.volume)<1/65536&&v.isMuted===original.mute;
}catch(e){result.fixture_restored=false;code=1;}}}
require('fs').writeFileSync(REPORT,JSON.stringify(result));process.exit(code);"""
    for field, value in (
        ("BOOTSTRAP", "Z:" + str(bootstrap)),
        ("ADDON", addon),
        ("GUID", guid),
        ("REPORT", "Z:" + str(report)),
    ):
        script = script.replace(field, json.dumps(value))
    try:
        async with endpoint_server(config.prefix, library, backend, port=0) as (port, stats):
            await isolated()
            process = await asyncio.create_subprocess_exec(
                "/usr/bin/wine",
                str(root.parents[1] / "NodeJS/20.20.2/node.exe"),
                "-e",
                script,
                cwd=root,
                env=dict(
                    os.environ,
                    WINEPREFIX=str(config.prefix),
                    WINEARCH="win64",
                    WINEDEBUG="-all",
                    WINEDLLOVERRIDES="winemenubuilder.exe=d",
                    DECKBRIDGE_CORE_AUDIO_PORT=str(port),
                ),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                async with asyncio.timeout(55):
                    code = await process.wait()
            except (TimeoutError, asyncio.CancelledError):
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise
            raw = await asyncio.to_thread(report.read_bytes)
            if not 0 < len(raw) < 16384:
                raise RuntimeError("Original addon result unavailable")
            result = json.loads(raw)
            observed = next((d for d in await backend.inventory() if d.id == target.id), None)
            result["native_fixture_restored"] = observed is not None and (
                observed.channels,
                observed.mute,
            ) == (target.channels, target.mute)
            streams_after, sinks_after = await asyncio.to_thread(pulse_state)
            info_after = await command("/usr/bin/pactl", "-f", "json", "info")
            result["default_devices_unchanged"] = all(
                info_before.get(k) == info_after.get(k)
                for k in ("default_sink_name", "default_source_name")
            )
            result["other_sinks_unchanged"] = all(
                sinks_after[k] == v
                for k, v in sinks_before.items()
                if k in sinks_after and k != str(target.index)
            )
            result["surviving_streams_unchanged"] = all(
                streams_after[k] == v for k, v in streams_before.items() if k in streams_after
            )
            result["only_test_output_allowed"] = (
                backend.allowed_devices == (target.id,) and not backend.allow_input
            )
            evidence = {"observations": result, "transport": dict(stats)}
            await asyncio.to_thread(
                atomic,
                state / "diagnostics/core-audio-original-addon-write.json",
                json.dumps(evidence, indent=2).encode(),
            )
            if (
                code
                or result.get("operation_failed")
                or not all(result.values())
                or stats["writes"] != 4
            ):
                raise RuntimeError("Original addon device observation failed")
            return evidence
    finally:
        await asyncio.to_thread(report.unlink, missing_ok=True)


if __name__ == "__main__":
    os.umask(0o077)
    if os.getuid() == 0:
        raise SystemExit("Use the desktop user")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise-fixture", action="store_true")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--simulate-notifications", action="store_true")
    args = parser.parse_args()
    if args.simulate_notifications and (args.exercise_fixture or args.approved):
        parser.error("Simulated notifications cannot be combined with fixture writes")
    try:
        result = asyncio.run(
            observe_notification_contract()
            if args.simulate_notifications
            else exercise_original_addon(args.approved)
            if args.exercise_fixture
            else observe()
        )
        print(json.dumps(result, indent=2))
    except (RuntimeError, OSError, ValueError, TimeoutError, BridgeError):
        print('{"error":"core_audio_observation_failed"}', file=sys.stderr)
        sys.exit(1)
