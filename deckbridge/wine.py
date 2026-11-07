"""Locate the exact running instance before asking Elgato to forward a URI."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from .config import Config
from .protocol import ACTION_TIMEOUT, BridgeError
from .uri import validate_deep_link


def running_instances(config: Config, proc_root: Path = Path("/proc")) -> list[int]:
    found = []
    expected_unix = str(config.executable)
    expected_windows = (
        "c:/"
        + str(config.executable.relative_to(config.prefix / "drive_c")).replace("\\", "/").lower()
    )
    for proc in proc_root.glob("[0-9]*"):
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            argv = (proc / "cmdline").read_bytes().split(b"\0")
            first = os.fsdecode(argv[0]).replace("\\", "/")
            if first != expected_unix and first.lower() != expected_windows:
                continue
            env = dict(
                x.split(b"=", 1) for x in (proc / "environ").read_bytes().split(b"\0") if b"=" in x
            )
            if env.get(b"WINEPREFIX") == os.fsencode(config.prefix):
                found.append(int(proc.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue  # Processes can exit during enumeration; never infer their prefix.
    return sorted(found)


async def run_bounded(
    argv: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None
) -> None:
    process = await asyncio.create_subprocess_exec(
        *argv,
        env=env,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(ACTION_TIMEOUT):
            rc = await process.wait()
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if rc:
        raise BridgeError("launcher_failed")


async def forward(config: Config, value: object) -> dict:
    uri = validate_deep_link(value)
    if not config.deep_links:
        raise BridgeError("capability_disabled")
    instances = await asyncio.to_thread(running_instances, config)
    if len(instances) != 1:
        raise BridgeError("instance_missing" if not instances else "instance_ambiguous")
    env = dict(os.environ)
    env.update(
        WINEPREFIX=str(config.prefix),
        WINEARCH="win64",
        WINEDLLOVERRIDES="winemenubuilder.exe=d",
        WINEDEBUG="-all",
    )
    await run_bounded(
        [str(config.wine), str(config.executable), uri], env=env, cwd=config.executable.parent
    )
    if instances[0] not in await asyncio.to_thread(running_instances, config):
        raise BridgeError("instance_lost")
    return {
        "status": "forwarded-unconfirmed",
        "instance_pid": instances[0],
        "application_ack": False,
    }
