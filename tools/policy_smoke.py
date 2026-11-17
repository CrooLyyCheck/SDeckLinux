#!/usr/bin/env python3
"""Observe policy COM reads or simulate default changes entirely in memory."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deckbridge.backends.audio.defaults import DefaultOutputBackend  # noqa: E402
from deckbridge.backends.audio.devices import DeviceBackend  # noqa: E402
from deckbridge.compat.windows.core_audio.transport import endpoint_server  # noqa: E402
from deckbridge.compat.windows.registry import owned_prefix, snapshot  # noqa: E402
from deckbridge.config import default_config, load  # noqa: E402
from deckbridge.protocol import BridgeError  # noqa: E402
from tools.install import atomic, private_backup  # noqa: E402


def read_report(path):
    with path.open("rb") as stream:
        return stream.read(16385)


async def observe(simulate=False):
    config = load(default_config())
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "deckbridge"
    if not owned_prefix(config.prefix, data):
        raise RuntimeError("Unsupported policy probe prefix")
    library = ROOT / ".local/native/deckbridge-core-audio.dll"
    probe = ROOT / ".local/native/policy_probe.exe"
    for path in (library, probe):
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o022
            or not 0 < metadata.st_size < 4 * 1024 * 1024
        ):
            raise RuntimeError("Unsafe policy probe artifact")
    backend = DeviceBackend()
    before = await backend.inventory()
    models = list(before)
    calls = []

    class MemoryPolicy:
        async def set_target(self, target):
            nonlocal models
            if not any(d.id == target and d.direction == "output" for d in models):
                raise BridgeError("audio_device_gone")
            calls.append(target)
            models = [
                dataclasses.replace(d, default=d.id == target) if d.direction == "output" else d
                for d in models
            ]

    await asyncio.to_thread(snapshot, config.prefix, lambda k, v: private_backup(state, k, v))
    directory = state / "diagnostics"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=directory, prefix="policy-", suffix=".json")
    os.close(fd)
    report = Path(name)
    try:

        async def memory_inventory():
            return list(models)

        with (
            patch.object(backend, "inventory", side_effect=memory_inventory)
            if simulate
            else patch.object(backend, "inventory", wraps=backend.inventory),
            patch(
                "deckbridge.backends.audio.defaults.command",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Policy probe must never execute a host setter"),
            ) as host_setter,
        ):
            defaults = MemoryPolicy() if simulate else DefaultOutputBackend(backend)
            async with endpoint_server(
                config.prefix, library, backend, port=0, defaults=defaults
            ) as (port, stats):
                process = await asyncio.create_subprocess_exec(
                    "/usr/bin/wine",
                    str(probe),
                    "Z:" + str(report),
                    "Z:" + str(library),
                    *(["--memory-exercise"] if simulate else []),
                    env=dict(
                        os.environ,
                        WINEPREFIX=str(config.prefix),
                        WINEARCH="win64",
                        WINEDEBUG="-all",
                        WINEDLLOVERRIDES="winemenubuilder.exe=d",
                        DECKBRIDGE_CORE_AUDIO_PORT=str(port),
                        DECKBRIDGE_POLICY_MEMORY_TEST="1" if simulate else "0",
                    ),
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    async with asyncio.timeout(40):
                        code = await process.wait()
                except (TimeoutError, asyncio.CancelledError):
                    if process.returncode is None:
                        process.kill()
                    await process.wait()
                    raise
                raw = await asyncio.to_thread(read_report, report)
                if not 0 < len(raw) < 16384:
                    raise RuntimeError("Policy probe result unavailable")
                result = json.loads(raw)
                host_setter.assert_not_awaited()
                if code or not all(
                    result.get(k) for k in ("physical_default", "identity_ok", "lifetime_ok")
                ):
                    raise RuntimeError("Policy COM probe failed")
                if simulate and (
                    len(calls) != 2
                    or stats["writes"] != 2
                    or not all(
                        result.get(k)
                        for k in (
                            "changed",
                            "notification",
                            "restored",
                            "communications_denied",
                            "input_denied",
                        )
                    )
                ):
                    raise RuntimeError("Memory policy observation failed")
                transport = dict(stats)
        after = await backend.inventory()
        native_unchanged = {d.direction: d.id for d in before if d.default} == {
            d.direction: d.id for d in after if d.default
        }
        evidence = {
            "simulated": simulate,
            "result": result,
            "transport": transport,
            "native_defaults_unchanged": native_unchanged,
            "host_setters_called": 0,
        }
        atomic(
            directory
            / ("audio-policy-simulated.json" if simulate else "audio-policy-readonly.json"),
            json.dumps(evidence, indent=2).encode(),
        )
        if not native_unchanged:
            raise RuntimeError("Native defaults changed outside the probe")
        return evidence
    finally:
        await asyncio.to_thread(report.unlink, missing_ok=True)


if __name__ == "__main__":
    os.umask(0o077)
    if os.getuid() == 0:
        raise SystemExit("Use the desktop user")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(observe(args.simulate)), indent=2))
    except (RuntimeError, OSError, ValueError, TimeoutError, BridgeError, AssertionError):
        raise SystemExit("Policy observation failed") from None
