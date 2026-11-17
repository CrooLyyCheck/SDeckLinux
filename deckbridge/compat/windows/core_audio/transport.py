"""Bounded Core Audio RPC, separate from plugin contracts and host audio models."""

from __future__ import annotations

import asyncio
import math
import os
import re
import secrets
import stat
import struct
import threading
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic

from ....backends.audio.devices import DeviceBackend
from ....protocol import BridgeError

REQUEST = struct.Struct("<4sHHIf16s")
RESPONSE = struct.Struct("<4sIfII64f16s")
MAGIC = b"DBA2"
NULL_CONTEXT = bytes(16)
READ_MAX_AGE = 0.25  # Native events invalidate earlier; setters always verify fresh state.
E_FAIL, E_INVALIDARG, E_ACCESSDENIED = 0x80004005, 0x80070057, 0x80070005
E_NOTIMPL, E_NOTFOUND = 0x80004001, 0x80070490
NAME_LENGTH = struct.Struct("<I")


class PeerHints:
    """Bounded candidate ordering, never a cache of authorization decisions."""

    def __init__(self):
        self._pids = deque(maxlen=16)
        self._lock = threading.Lock()

    def candidates(self, proc_root: Path):
        with self._lock:
            known = tuple(self._pids)
        for pid in known:
            yield proc_root / pid
        for proc in proc_root.glob("[0-9]*"):
            if proc.name not in known:
                yield proc

    def remember(self, pid: str):
        with self._lock:
            if pid in self._pids:
                self._pids.remove(pid)
            self._pids.appendleft(pid)


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
    prefix: Path,
    library: Path,
    address: tuple,
    port: int,
    proc_root: Path = Path("/proc"),
    *,
    hints: PeerHints | None = None,
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
    candidates = hints.candidates(proc_root) if hints is not None else proc_root.glob("[0-9]*")
    for proc in candidates:
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
                    if hints is not None:
                        hints.remember(proc.name)
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


def default_response(status: int, device=None, *, description=False) -> bytes:
    if status:
        return response(status)
    name = (device.description if description else device.name).encode("utf-8")
    if not 0 < len(name) <= 4096 or b"\x00" in name:
        return response(E_FAIL)
    return response(0, device) + NAME_LENGTH.pack(len(name)) + name


async def dispatch(
    backend: DeviceBackend,
    header: bytes,
    name_bytes: bytes,
    on_change=None,
    snapshot=None,
    defaults=None,
) -> bytes:
    try:
        magic, operation, flow, length, value, context = REQUEST.unpack(header)
        if (
            magic != MAGIC
            or operation not in (0, 1, 2, 3, 4, 5, 6, 7)
            or flow not in (0, 1)
            or length != len(name_bytes)
            or length > 4096
            or not math.isfinite(value)
        ):
            return response(E_INVALIDARG)
        name = name_bytes.decode("utf-8")
        if operation in (4, 5, 6):
            if defaults is None or flow != 0 or (operation == 4 and value == 2):
                return response(E_NOTIMPL)
            if (operation == 4 and (not name or value not in (0, 1))) or (
                operation in (5, 6) and (name or value != 0)
            ):
                return response(E_INVALIDARG)
        if (
            "\x00" in name
            or (operation == 7 and (not name or value != 0))
            or (operation == 1 and not 0 <= value <= 1)
            or (operation == 2 and value not in (0, 1))
        ):
            return response(E_INVALIDARG)
        direction = "output" if flow == 0 else "input"
        devices = (
            await snapshot(force=operation in (1, 2, 4))
            if snapshot is not None
            else await backend.inventory()
        )
        device = next(
            (
                d
                for d in devices
                if d.direction == direction and (d.name == name if name else d.default)
            ),
            None,
        )
        if device is None:
            if operation in (5, 6):
                return response(E_NOTFOUND)
            return response(E_FAIL)
        if operation in (1, 2, 4):
            if operation == 4:
                await defaults.set_target(device.id)
            else:
                await backend.set_target(
                    device.id,
                    **({"volume": value} if operation == 1 else {"mute": bool(value)}),
                    **({"require_default": True} if not name else {}),
                )
            devices = (
                await snapshot(force=True) if snapshot is not None else await backend.inventory()
            )
            device = next((d for d in devices if d.id == device.id), None)
            if device is None:
                return response(E_FAIL)
            if on_change is not None:
                await on_change(device, context, devices)
        if operation in (5, 6):
            return default_response(0, device)
        if operation == 7:
            return default_response(0, device, description=True)
        return response(0, device, context if operation in (1, 2) else NULL_CONTEXT)
    except BridgeError as error:
        return response(
            E_ACCESSDENIED
            if error.code in {"audio_device_write_disabled", "audio_default_write_disabled"}
            else E_FAIL
        )
    except (UnicodeError, struct.error):
        return response(E_INVALIDARG)


@asynccontextmanager
async def endpoint_server(
    prefix: Path,
    library: Path,
    backend: DeviceBackend,
    *,
    port=1845,
    on_failure=None,
    defaults=None,
):
    clients = set()
    handlers = set()
    subscriptions = {}
    transaction = asyncio.Lock()
    peer_hints = PeerHints()
    revision = 0
    cached_revision, cached_at, cached_devices = -1, 0.0, None
    refresh_needed = asyncio.Event()
    stats = {"reads": 0, "writes": 0, "rejected": 0, "subscribers": 0, "monitor_failed": False}
    library = await asyncio.to_thread(library.resolve, strict=True)
    token = await asyncio.to_thread(private_token, library)

    async def snapshot(*, force=False):
        nonlocal cached_revision, cached_at, cached_devices
        if (
            force
            or cached_devices is None
            or cached_revision != revision
            or monotonic() - cached_at >= READ_MAX_AGE
        ):
            seen = revision
            cached_devices = None  # A failed forced read must not leave usable stale state.
            cached_devices = await backend.inventory()
            cached_at, cached_revision = monotonic(), seen
        return cached_devices

    async def publish(devices, changed=None, context=NULL_CONTEXT):
        for writer, (flow, name, previous, default_names) in tuple(subscriptions.items()):
            device = next(
                (
                    d
                    for d in devices
                    if d.direction == flow and (d.name == name if name else d.default)
                ),
                None,
            )
            baseline = (
                (default_response(0, device) if device else response(E_NOTFOUND))
                if default_names
                else (response(0, device) if device else response(E_FAIL))
            )
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
            writer.write(
                baseline
                if default_names
                else response(0, device, event_context)
                if device
                else baseline
            )
            subscriptions[writer] = (flow, name, baseline, default_names)

    async def changed(device, context, devices):
        await publish(devices, device, context)

    async def read_events(process):
        nonlocal revision
        while line := await process.stdout.readline():
            if re.fullmatch(
                rb"Event '(?:new|change|remove)' on (?:sink|source|server) #\d+\r?\n", line
            ):
                revision += 1
                refresh_needed.set()
        raise BridgeError("audio_backend_disconnected")

    async def refresh_subscriptions():
        while True:
            await refresh_needed.wait()
            refresh_needed.clear()
            if not subscriptions:
                continue
            async with transaction:
                async with backend.lock:
                    devices = await snapshot()
                await publish(devices)

    async def notifications():
        process = None
        tasks = []
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
            tasks = [
                asyncio.create_task(read_events(process)),
                asyncio.create_task(refresh_subscriptions()),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                await task
        except (OSError, ValueError, TimeoutError, BridgeError):
            stats["monitor_failed"] = True
            if on_failure is not None:
                on_failure()
            for writer in tuple(clients):
                writer.close()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
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
                    authorized_peer, prefix, library, address, local_port, hints=peer_hints
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
                    if operation in (3, 6):
                        async with backend.lock:
                            result = await dispatch(
                                backend, header, name, snapshot=snapshot, defaults=defaults
                            )
                            status = RESPONSE.unpack_from(result)[1]
                            if status == 0 or (operation == 6 and status == E_NOTFOUND):
                                if stats["monitor_failed"]:
                                    result = response(E_FAIL)
                                else:
                                    subscriptions[writer] = (
                                        "output" if flow == 0 else "input",
                                        name.decode("utf-8"),
                                        result,
                                        operation == 6,
                                    )
                                    subscribed = True
                                    stats["subscribers"] = len(subscriptions)
                    else:
                        result = await dispatch(backend, header, name, changed, snapshot, defaults)
                stats["writes" if operation in (1, 2, 4) else "reads"] += 1
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
