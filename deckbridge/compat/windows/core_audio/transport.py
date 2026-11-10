"""Bounded Core Audio RPC, separate from plugin contracts and host audio models."""

from __future__ import annotations

import asyncio
import math
import os
import re
import secrets
import stat
import struct
from contextlib import asynccontextmanager
from pathlib import Path

from ....backends.audio.devices import DeviceBackend
from ....protocol import BridgeError

REQUEST = struct.Struct("<4sHHIf16s")
RESPONSE = struct.Struct("<4sIfII64f16s")
MAGIC = b"DBA2"
NULL_CONTEXT = bytes(16)
E_FAIL, E_INVALIDARG, E_ACCESSDENIED = 0x80004005, 0x80070057, 0x80070005


def private_token(library: Path) -> bytes:
    path = library.with_suffix(".token")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        fd = None
    if fd is not None:
        with os.fdopen(fd, "wb") as stream:
            stream.write(secrets.token_bytes(32))
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_size != 32
    ):
        raise RuntimeError("Unsafe native endpoint token")
    with path.open("rb") as stream:
        token = stream.read(33)
    if len(token) != 32:
        raise RuntimeError("Native endpoint token changed")
    return token


def authorized_peer(
    prefix: Path, library: Path, address: tuple, port: int, proc_root: Path = Path("/proc")
) -> bool:
    if address[0] != "127.0.0.1" or library.is_symlink():
        return False
    info = library.stat()
    if info.st_uid != os.getuid():
        return False
    inodes = set()
    for line in (proc_root / "net/tcp").read_text().splitlines()[1:]:
        fields = line.split()
        if (
            len(fields) >= 10
            and fields[1] == f"0100007F:{address[1]:04X}"
            and fields[2] == f"0100007F:{port:04X}"
            and fields[3] == "01"
            and fields[7] == str(os.getuid())
        ):
            inodes.add(f"socket:[{fields[9]}]")
    if not inodes:
        return False
    for proc in proc_root.glob("[0-9]*"):
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            if not any(str(fd.readlink()) in inodes for fd in (proc / "fd").iterdir()):
                continue
            env = dict(
                v.split(b"=", 1) for v in (proc / "environ").read_bytes().split(b"\0") if b"=" in v
            )
            if env.get(b"WINEPREFIX") != os.fsencode(prefix):
                continue
            for line in (proc / "maps").read_text().splitlines():
                fields = line.split(maxsplit=5)
                if len(fields) != 6 or not fields[4].isdigit() or int(fields[4]) != info.st_ino:
                    continue
                path = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[5])
                if path == str(library):
                    return True
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return False


def response(status: int, device=None, context=NULL_CONTEXT) -> bytes:
    channels = [min(1.0, value / 65536) for value in device.channels] if device else []
    return RESPONSE.pack(
        MAGIC,
        status,
        min(1.0, device.volume) if device else 0,
        int(device.mute) if device else 0,
        len(channels),
        *(channels + [0.0] * (64 - len(channels))),
        context,
    )


async def dispatch(
    backend: DeviceBackend, header: bytes, name_bytes: bytes, on_change=None
) -> bytes:
    try:
        magic, operation, flow, length, value, context = REQUEST.unpack(header)
        if (
            magic != MAGIC
            or operation not in (0, 1, 2, 3)
            or flow not in (0, 1)
            or length != len(name_bytes)
            or length > 4096
            or not math.isfinite(value)
        ):
            return response(E_INVALIDARG)
        name = name_bytes.decode("utf-8")
        if (
            "\x00" in name
            or (operation == 1 and not 0 <= value <= 1)
            or (operation == 2 and value not in (0, 1))
        ):
            return response(E_INVALIDARG)
        direction = "output" if flow == 0 else "input"
        devices = await backend.inventory()
        device = next(
            (
                d
                for d in devices
                if d.direction == direction and (d.name == name if name else d.default)
            ),
            None,
        )
        if device is None:
            return response(E_FAIL)
        if operation in (1, 2):
            await backend.set_target(
                device.id, **({"volume": value} if operation == 1 else {"mute": bool(value)})
            )
            device = next((d for d in await backend.inventory() if d.id == device.id), None)
            if device is None:
                return response(E_FAIL)
            if on_change is not None:
                await on_change(device, context)
        return response(0, device, context if operation in (1, 2) else NULL_CONTEXT)
    except BridgeError as error:
        return response(E_ACCESSDENIED if error.code == "audio_device_write_disabled" else E_FAIL)
    except (UnicodeError, struct.error):
        return response(E_INVALIDARG)


@asynccontextmanager
async def endpoint_server(prefix: Path, library: Path, backend: DeviceBackend, *, port=1845):
    clients = set()
    handlers = set()
    subscriptions = {}
    transaction = asyncio.Lock()
    stats = {"reads": 0, "writes": 0, "rejected": 0, "subscribers": 0, "monitor_failed": False}
    library = await asyncio.to_thread(library.resolve, strict=True)
    token = await asyncio.to_thread(private_token, library)

    async def publish(devices, changed=None, context=NULL_CONTEXT):
        for writer, (flow, name, previous) in tuple(subscriptions.items()):
            device = next(
                (
                    d
                    for d in devices
                    if d.direction == flow and (d.name == name if name else d.default)
                ),
                None,
            )
            baseline = response(0, device) if device else response(E_FAIL)
            if baseline == previous:
                continue
            if writer.transport.get_write_buffer_size() > 4096:
                writer.close()
                continue
            # Only the exact endpoint changed by this setter receives its GUID.
            event_context = (
                context
                if device
                and changed
                and (device.id, device.channels, device.mute)
                == (changed.id, changed.channels, changed.mute)
                else NULL_CONTEXT
            )
            writer.write(response(0, device, event_context) if device else baseline)
            subscriptions[writer] = (flow, name, baseline)

    async def changed(device, context):
        async with backend.lock:
            devices = await backend.inventory()
        await publish(devices, device, context)

    async def notifications():
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                "/usr/bin/pactl",
                "subscribe",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                stdin=asyncio.subprocess.DEVNULL,
                env=dict(os.environ, LC_ALL="C"),
                limit=1024,
            )
            while line := await process.stdout.readline():
                if not re.fullmatch(
                    rb"Event '(?:new|change|remove)' on (?:sink|source|server) #\d+\r?\n", line
                ):
                    continue
                if not subscriptions:
                    continue
                async with transaction:
                    async with backend.lock:
                        devices = await backend.inventory()
                    await publish(devices)
            raise BridgeError("audio_backend_disconnected")
        except (OSError, ValueError, TimeoutError, BridgeError):
            stats["monitor_failed"] = True
            for writer in tuple(clients):
                writer.close()
        finally:
            if process is not None:
                if process.returncode is None:
                    process.kill()
                await process.wait()

    async def handle(reader, writer):
        clients.add(writer)
        task = asyncio.current_task()
        handlers.add(task)
        try:
            async with asyncio.timeout(8):
                address = writer.get_extra_info("peername")
                local_port = writer.get_extra_info("sockname")[1]
                if len(clients) > 32 or not await asyncio.to_thread(
                    authorized_peer, prefix, library, address, local_port
                ):
                    stats["rejected"] += 1
                    return
                writer.write(MAGIC + token)
                await writer.drain()
                header = await reader.readexactly(REQUEST.size)
                length = REQUEST.unpack(header)[3]
                if length > 4096:
                    return
                name = await reader.readexactly(length)
                operation, flow = REQUEST.unpack(header)[1:3]
                subscribed = False
                async with transaction:
                    if operation == 3:
                        async with backend.lock:
                            result = await dispatch(backend, header, name)
                            if RESPONSE.unpack(result)[1] == 0:
                                if stats["monitor_failed"]:
                                    result = response(E_FAIL)
                                else:
                                    subscriptions[writer] = (
                                        "output" if flow == 0 else "input",
                                        name.decode("utf-8"),
                                        result,
                                    )
                                    subscribed = True
                                    stats["subscribers"] = len(subscriptions)
                    else:
                        result = await dispatch(backend, header, name, changed)
                stats["writes" if operation in (1, 2) else "reads"] += 1
                writer.write(result)
                await writer.drain()
            if subscribed:
                await reader.read(1)  # A subscription is read-only; no second command on it.
        except (asyncio.IncompleteReadError, OSError, TimeoutError, BridgeError):
            pass  # Fixed failure/connection close; never echo a request or retry an action.
        finally:
            clients.discard(writer)
            subscriptions.pop(writer, None)
            stats["subscribers"] = len(subscriptions)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            handlers.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", port, limit=8192)
    monitor = asyncio.create_task(notifications())
    try:
        async with server:
            yield server.sockets[0].getsockname()[1], stats
    finally:
        for writer in tuple(clients):
            writer.close()
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
        if handlers:
            await asyncio.gather(*tuple(handlers), return_exceptions=True)
