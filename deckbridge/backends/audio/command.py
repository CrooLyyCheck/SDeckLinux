"""Bounded native audio subprocess observations and explicitly scoped commands."""

from __future__ import annotations

import asyncio
import json
import os

from ...protocol import BridgeError

MAX_GRAPH_BYTES = 8 * 1024 * 1024


async def command(*argv: str, json_output: bool = True):
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=dict(os.environ, LC_ALL="C"),
    )
    try:
        async with asyncio.timeout(5):
            try:
                data = await process.stdout.readexactly(MAX_GRAPH_BYTES + 1)
            except asyncio.IncompleteReadError as error:
                data = error.partial
            else:
                raise BridgeError("audio_snapshot_too_large")
            await process.wait()
    except (BridgeError, TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise BridgeError("audio_backend_failed")
    if not json_output:
        return None
    try:
        return json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise BridgeError("audio_invalid_snapshot") from None
