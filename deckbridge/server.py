"""Same-user Unix socket, bounded frames/concurrency, payload-free logs."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import signal
import socket
import stat
import struct
import sys
import uuid
from pathlib import Path

from .config import Config
from .diagnostics import diagnose
from .protocol import IO_TIMEOUT, MAX_FRAME, BridgeError, decode_request, encode, exact_keys
from .providers import capabilities, execute

MAX_CLIENTS = 16


def log(event: str, correlation: str = "", code: str = "") -> None:
    print(
        json.dumps(
            {
                "level": "error" if code else "info",
                "event": event,
                "correlation": correlation,
                "code": code,
            }
        ),
        file=sys.stderr,
        flush=True,
    )


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise BridgeError("socket_directory_unsafe")


class Server:
    def __init__(self, config: Config):
        self.config = config
        self.clients: set[asyncio.Task] = set()

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if len(self.clients) >= MAX_CLIENTS:
            writer.close()
            await writer.wait_closed()
            return
        self.clients.add(task)
        correlation, request_id = uuid.uuid4().hex, None
        try:
            peer = writer.get_extra_info("socket").getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, 12
            )
            _, uid, _ = struct.unpack("3i", peer)
            if uid != os.getuid():
                raise BridgeError("peer_not_allowed")
            try:
                async with asyncio.timeout(IO_TIMEOUT):
                    raw = await reader.readuntil(b"\n")
            except (asyncio.LimitOverrunError, asyncio.IncompleteReadError):
                raise BridgeError("invalid_frame") from None
            request = decode_request(raw)
            request_id = request.id
            if request.method in {"capabilities.list", "diagnostics.get"}:
                exact_keys(request.params, set())
            if request.method == "capabilities.list":
                result = capabilities(self.config)
            elif request.method == "diagnostics.get":
                result = await diagnose(self.config)
            else:
                result = await execute(self.config, request.params)
            reply = {"v": 1, "id": request_id, "result": result}
            log("request_completed", correlation)
        except BridgeError as exc:
            reply = {"v": 1, "id": request_id, "error": {"code": exc.code}}
            log("request_failed", correlation, exc.code)
        except TimeoutError:
            reply = {"v": 1, "id": request_id, "error": {"code": "timeout_outcome_unknown"}}
            log("request_failed", correlation, "timeout_outcome_unknown")
        except OSError:
            reply = {"v": 1, "id": request_id, "error": {"code": "backend_unavailable"}}
            log("request_failed", correlation, "backend_unavailable")
        finally:
            # Cancellation during shutdown must close accepted sockets too.
            if sys.exc_info()[0] is not None:
                writer.close()
                self.clients.discard(task)
        try:
            writer.write(encode(reply))
            async with asyncio.timeout(IO_TIMEOUT):
                await writer.drain()
        except (ConnectionError, TimeoutError):
            log("client_disconnected", correlation, "outcome_unknown")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass  # Peer has already disconnected; no retry of side effects.
            self.clients.discard(task)


def lock_socket(path: Path) -> int:
    private_directory(path.parent)
    fd = os.open(path.parent / "daemon.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise BridgeError("lock_file_unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BridgeError("daemon_already_running") from None
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise BridgeError("socket_path_unsafe")
            path.unlink()
        return fd
    except (BridgeError, OSError):
        os.close(fd)
        raise


async def serve(config: Config, path: Path) -> None:
    fd = lock_socket(path)
    server = None
    handler = Server(config)
    try:
        server = await asyncio.start_unix_server(handler.handle, path=str(path), limit=MAX_FRAME)
        os.chmod(path, 0o600)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        log("ready")
        async with server:
            await stop.wait()
    finally:
        if server:
            server.close()
            await server.wait_closed()
            for task in tuple(handler.clients):
                task.cancel()
            if handler.clients:
                await asyncio.gather(*tuple(handler.clients), return_exceptions=True)
            await asyncio.to_thread(path.unlink, missing_ok=True)
        os.close(fd)
