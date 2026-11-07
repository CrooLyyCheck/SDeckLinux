"""Bounded native icon lookup; no vendor paths or executable desktop actions."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

MAX_PNG_BYTES = 32768


class IconProvider:
    def __init__(self):
        self.cache: dict[tuple, str | None] = {}
        self.failure: str | None = None

    async def image(self, app: dict) -> str | None:
        key = (app.get("icon_name"), app["id"], app["executable"])
        if key in self.cache:
            return self.cache[key]
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                "/usr/bin/python3",
                str(Path(__file__).with_name("icon_worker.py")),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            async with asyncio.timeout(4):
                process.stdin.write(
                    json.dumps(
                        {
                            "icon_name": app.get("icon_name"),
                            "id": app["id"],
                            "executable": app["executable"],
                        }
                    ).encode()
                )
                await process.stdin.drain()
                process.stdin.close()
                try:
                    data = await process.stdout.readexactly(MAX_PNG_BYTES + 1)
                except asyncio.IncompleteReadError as error:
                    data = error.partial
                else:
                    self.failure = "icon_too_large"
                    return None
                await process.wait()
            if process.returncode == 3:
                self.failure = "native_icon_backend_unavailable"
            encoded = (
                base64.b64encode(data).decode("ascii")
                if process.returncode == 0 and data.startswith(b"\x89PNG\r\n\x1a\n")
                else None
            )
            if len(self.cache) >= 128:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = encoded
            return encoded
        except (OSError, TimeoutError):
            self.failure = "native_icon_backend_unavailable"
            return None
        finally:
            if process:
                if process.returncode is None:
                    process.kill()
                await process.wait()
