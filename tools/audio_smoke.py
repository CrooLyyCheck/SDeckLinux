#!/usr/bin/env python3
"""Explicit harmless audio fixture and separately authorized volume/mute checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deckbridge.backends.audio.pipewire import command  # noqa: E402
from deckbridge.client import call  # noqa: E402
from deckbridge.config import socket_path  # noqa: E402
from deckbridge.protocol import BridgeError  # noqa: E402

APPLICATION = "app:io.deckbridge.audio-test"
PROPERTIES = "application.id=io.deckbridge.audio-test"


def state_directory() -> Path:
    path = (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        / "deckbridge/diagnostics"
    )
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def pulse_state() -> tuple[dict, dict]:
    def read(kind):
        return json.loads(
            subprocess.run(  # noqa: S603 - fixed read-only pactl arguments
                ["/usr/bin/pactl", "-f", "json", "list", kind],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
        )

    return (
        {str(s["index"]): {"volume": s["volume"], "mute": s["mute"]} for s in read("sink-inputs")},
        {str(s["index"]): {"volume": s["volume"], "mute": s["mute"]} for s in read("sinks")},
    )


async def start_fixture(sink_name: str):
    return await asyncio.create_subprocess_exec(
        *[
            "/usr/bin/pacat",
            "--playback",
            "--raw",
            "--format=float32le",
            "--rate=48000",
            "--channels=2",
            "--client-name=DeckBridge Test",
            "--stream-name=DeckBridge Test",
            "--property=" + PROPERTIES,
            "--device=" + sink_name,
        ],
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )


async def verify_isolation(app: dict, sink_name: str) -> None:
    graph = await command("/usr/bin/pw-dump", "--no-colors")
    sink_ids = {
        o["id"]
        for o in graph
        if o.get("type") == "PipeWire:Interface:Node"
        and o.get("info", {}).get("props", {}).get("node.name") == sink_name
        and o.get("info", {}).get("props", {}).get("factory.name") == "support.null-audio-sink"
    }
    stream_ids = {s["node_id"] for s in app["sessions"]}
    allowed = sink_ids | stream_ids
    links = [
        o["info"]
        for o in graph
        if o.get("type") == "PipeWire:Interface:Link"
        and (
            o.get("info", {}).get("output-node-id") in allowed
            or o.get("info", {}).get("input-node-id") in allowed
        )
    ]
    if (
        len(sink_ids) != 1
        or not links
        or any(
            link["output-node-id"] not in allowed or link["input-node-id"] not in allowed
            for link in links
        )
    ):
        raise RuntimeError("Fixture is not isolated to its owned null sink")


async def unload_owned_module(module: int, sink_name: str, cookie: str) -> None:
    info = await command("/usr/bin/pactl", "-f", "json", "info")
    modules = await command("/usr/bin/pactl", "-f", "json", "list", "modules")
    sinks = await command("/usr/bin/pactl", "-f", "json", "list", "sinks")
    owned = any(
        m["name"] == "module-null-sink" and "sink_name=" + sink_name in shlex.split(m["argument"])
        for m in modules
    )
    if (
        info.get("cookie") == cookie
        and owned
        and any(s["name"] == sink_name and s["owner_module"] == module for s in sinks)
    ):
        await command("/usr/bin/pactl", "unload-module", str(module), json_output=False)
    else:
        raise RuntimeError("Null-sink ownership changed; unrelated modules preserved")


async def feed_zeroes(process):
    try:
        while process.returncode is None:
            process.stdin.write(bytes(4096))
            await process.stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        return


async def fixture(duration: float) -> None:
    if not 1 <= duration <= 3600:
        raise RuntimeError("Fixture duration must be 1..3600 seconds")
    descriptor = state_directory() / "audio-fixture.json"
    if descriptor.exists() or descriptor.is_symlink():
        raise RuntimeError("An existing fixture descriptor is preserved")
    baseline_streams, baseline_sinks = await asyncio.to_thread(pulse_state)
    baseline_info = await command("/usr/bin/pactl", "-f", "json", "info")
    sink_name = f"deckbridge_test_{os.getpid()}_{secrets.token_hex(4)}"
    module = await command(
        "/usr/bin/pactl",
        "load-module",
        "module-null-sink",
        "sink_name=" + sink_name,
        'sink_properties="device.description=DeckBridgeTestSink '
        'priority.session=0 node.hidden=true"',
    )
    if type(module) is not int:
        raise RuntimeError("Invalid null-sink module response")
    process = producer = None
    content = None
    try:
        info = await command("/usr/bin/pactl", "-f", "json", "info")
        if any(
            info.get(k) != baseline_info.get(k)
            for k in ("default_sink_name", "default_source_name")
        ):
            raise RuntimeError("Default audio device changed; stopping owned fixture")
        process = await start_fixture(sink_name)
        producer = asyncio.create_task(feed_zeroes(process))
        deadline = time.monotonic() + 10
        while True:
            data = await call(
                socket_path(),
                "actions.execute",
                {"capability": "audio.sessions.list", "arguments": {}},
            )
            app = next((a for a in data["applications"] if a["id"] == APPLICATION), None)
            if app:
                break
            if process.returncode is not None or time.monotonic() >= deadline:
                raise RuntimeError("Silent fixture did not appear within 10 seconds")
            await asyncio.sleep(0.1)  # Observe graph creation; never retry a mutation.
        await verify_isolation(app, sink_name)
        content = (
            json.dumps(
                {
                    "owner_pid": os.getpid(),
                    "fixture_pid": process.pid,
                    "application": APPLICATION,
                    "hardware_isolated": True,
                    "virtual_sink": sink_name,
                    "module": module,
                    "baseline_defaults": {
                        k: baseline_info[k] for k in ("default_sink_name", "default_source_name")
                    },
                    "baseline_streams": baseline_streams,
                    "baseline_sinks": baseline_sinks,
                },
                indent=2,
            )
            + "\n"
        )
        fd = os.open(descriptor, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        print(
            json.dumps(
                {
                    "fixture": "ready",
                    "application": APPLICATION,
                    "hardware_isolated": True,
                    "volume_changes_performed": False,
                    "duration_seconds": duration,
                }
            ),
            flush=True,
        )
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        stopped = asyncio.create_task(stop.wait())
        exited = asyncio.create_task(process.wait())
        try:
            done, _ = await asyncio.wait(
                {stopped, exited}, timeout=duration, return_when=asyncio.FIRST_COMPLETED
            )
            if exited in done:
                diagnostic = (await process.stderr.read(2048)).decode(errors="replace").strip()
                raise RuntimeError(
                    f"Audio fixture exited ({process.returncode}): {diagnostic or 'no stderr'}"
                )
        finally:
            stopped.cancel()
            exited.cancel()
            await asyncio.gather(stopped, exited, return_exceptions=True)
    finally:
        if producer:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
        if process and process.returncode is None:
            process.terminate()
            try:
                async with asyncio.timeout(5):
                    await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()
        if content and descriptor.exists() and descriptor.read_text() == content:
            descriptor.unlink()
        await unload_owned_module(module, sink_name, baseline_info["cookie"])
        print('{"fixture":"stopped"}', flush=True)


async def exercise(approved: bool) -> None:
    if not approved:
        raise RuntimeError("Volume tests require explicit authorization and --approved")
    descriptor = state_directory() / "audio-fixture.json"
    record = json.loads(descriptor.read_text())
    if record.get("application") != APPLICATION or not record.get("hardware_isolated"):
        raise RuntimeError("Expected owned hardware-isolated fixture")

    async def action(capability, **kwargs):
        return await call(
            socket_path(),
            "actions.execute",
            {"capability": capability, "arguments": {"target": APPLICATION, **kwargs}},
        )

    async def current():
        data = await call(
            socket_path(), "actions.execute", {"capability": "audio.sessions.list", "arguments": {}}
        )
        result = next((a for a in data["applications"] if a["id"] == APPLICATION), None)
        if not result:
            raise RuntimeError("Owned fixture disappeared")
        return result

    original = await current()
    await verify_isolation(original, record["virtual_sink"])
    if not 0 <= original["volume"] <= 1:
        raise RuntimeError("Fixture volume is outside the supported restoration range")
    baseline_streams, baseline_sinks = await asyncio.to_thread(pulse_state)
    baseline_info = await command("/usr/bin/pactl", "-f", "json", "info")
    report = {}
    try:
        await action("audio.session.volume", volume=0.25)
        volume = await current()
        report["volume_25_percent_observed"] = abs(volume["volume"] - 0.25) < 1 / 65536
        await action("audio.session.mute", mute=True)
        report["mute_observed"] = (await current())["mute"] is True
    finally:
        await action("audio.session.volume", volume=original["volume"])
        await action("audio.session.mute", mute=original["mute"])
    restored = await current()
    report["fixture_restored"] = (restored["volume"], restored["mute"]) == (
        original["volume"],
        original["mute"],
    )
    streams, sinks = await asyncio.to_thread(pulse_state)
    report["system_sinks_unchanged"] = sinks == baseline_sinks
    report["surviving_other_streams_unchanged"] = all(
        streams[k] == v for k, v in baseline_streams.items() if k in streams
    )
    info = await command("/usr/bin/pactl", "-f", "json", "info")
    report["default_devices_unchanged"] = all(
        info.get(k) == baseline_info.get(k) for k in ("default_sink_name", "default_source_name")
    )
    (state_directory() / "audio-write-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not all(report.values()):
        raise RuntimeError("An audio observation failed; no success claimed")


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    hold = sub.add_parser("hold-fixture")
    hold.add_argument("--duration", type=float, default=900)
    check = sub.add_parser("exercise")
    check.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(
            fixture(args.duration) if args.command == "hold-fixture" else exercise(args.approved)
        )
    except (RuntimeError, BridgeError, OSError, subprocess.SubprocessError) as error:
        print(f"Audio smoke stopped: {error}", file=sys.stderr)
        sys.exit(1)
