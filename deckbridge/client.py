"""No transparent retries: side effects may have happened on disconnect."""

import asyncio
import json
import uuid
from pathlib import Path

from .protocol import ACTION_TIMEOUT, IO_TIMEOUT, MAX_FRAME, WIRE_ERRORS, BridgeError, encode


async def call(path: Path, method: str, params: dict) -> dict:
    request_id = uuid.uuid4().hex
    async with asyncio.timeout(IO_TIMEOUT):
        reader, writer = await asyncio.open_unix_connection(str(path), limit=MAX_FRAME)
    try:
        writer.write(encode({"v": 1, "id": request_id, "method": method, "params": params}))
        async with asyncio.timeout(ACTION_TIMEOUT + IO_TIMEOUT):
            await writer.drain()
            data = await reader.readuntil(b"\n")
        try:
            reply = json.loads(data)
        except (ValueError, UnicodeError, RecursionError):
            raise BridgeError("invalid_response") from None
        if (
            not isinstance(reply, dict)
            or type(reply.get("v")) is not int
            or reply["v"] != 1
            or reply.get("id") != request_id
            or set(reply) not in ({"v", "id", "result"}, {"v", "id", "error"})
        ):
            raise BridgeError("invalid_response")
        if "error" in reply:
            code = reply["error"].get("code") if isinstance(reply["error"], dict) else None
            # Do not print arbitrary text supplied by the other endpoint.
            if (
                not isinstance(code, str)
                or code not in WIRE_ERRORS
                or set(reply["error"]) != {"code"}
            ):
                raise BridgeError("invalid_response")
            raise BridgeError(code)
        if "result" not in reply or not isinstance(reply["result"], dict):
            raise BridgeError("invalid_response")
        return reply["result"]
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        raise BridgeError("connection_lost_outcome_unknown") from None
    finally:
        writer.close()
        await writer.wait_closed()
