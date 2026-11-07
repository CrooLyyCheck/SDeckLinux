"""Private, opt-in implementation of the observed vendor Audio Router service."""

from __future__ import annotations

import asyncio
import json
import logging
from http import HTTPStatus

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from ....backends.audio.pipewire import AudioBackend
from ....config import Config
from ....protocol import BridgeError
from .peer import authenticate, verify_plugin
from .protocol import Router


class SafeLog(logging.Handler):
    def emit(self, record):
        # Library debug records can contain complete frames/HTTP headers.
        if record.levelno >= logging.WARNING:
            from ....server import log

            log("volume_controller_transport_error", code="transport_internal_error")


async def run_adapter(config: Config, backend: AudioBackend, *, port: int = 1844) -> None:
    from ....server import log

    status = backend.adapter_status
    status["display"] = config.volume_controller_display
    status["hide_event_streams"] = config.volume_controller_hide_events
    status["icon_images_served"] = 0
    logger = logging.getLogger("deckbridge.volume_controller.websocket")
    logger.handlers = [SafeLog()]
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    clients = set()

    async def authorize(connection, request):
        if request.path != "/" or "Origin" in request.headers or len(clients) >= 2:
            return connection.respond(HTTPStatus.FORBIDDEN, "peer_not_allowed\n")
        pid = await asyncio.to_thread(
            authenticate, config, root, connection.remote_address, connection.local_address[1]
        )
        if pid is None:
            log("volume_controller_peer_rejected", code="peer_not_allowed")
            return connection.respond(HTTPStatus.FORBIDDEN, "peer_not_allowed\n")
        return None

    async def handler(connection):
        clients.add(connection)
        status["connected_clients"] = len(clients)
        log("volume_controller_connected")
        router = Router(
            backend,
            display=config.volume_controller_display,
            hide_events=config.volume_controller_hide_events,
        )

        async def notifications():
            try:
                _, previous = router.notifications({})
                revision = backend.revision
                while True:
                    async with backend.changed:
                        await backend.changed.wait_for(
                            lambda revision=revision: backend.revision != revision
                        )
                    await backend.snapshot()
                    revision = backend.revision
                    events, previous = router.notifications(previous)
                    for event in events:
                        await connection.send(json.dumps(event))
            except ConnectionClosed:
                return
            except (BridgeError, OSError, TimeoutError):
                log("volume_controller_notifications_failed", code="audio_backend_unavailable")
                await connection.close(code=1011, reason="audio_backend_unavailable")

        task = asyncio.create_task(notifications())
        try:
            async for message in connection:
                result = await router.request(message)
                await connection.send(json.dumps(result))
                for event in router.followup_events():
                    await connection.send(json.dumps(event))
                status["requests_completed"] += 1
                status["enumerated_applications"] = len(router.enumerated)
                if "error" in result:
                    log("volume_controller_request_failed", code=result["error"]["message"])
        except (ConnectionClosed, BridgeError):
            log("volume_controller_disconnected")
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            clients.discard(connection)
            status["connected_clients"] = len(clients)

    try:
        root = await asyncio.to_thread(verify_plugin, config)
        await backend.ready.wait()
        await backend.snapshot()
        async with serve(
            handler,
            "127.0.0.1",
            port,
            origins=[None],
            process_request=authorize,
            compression=None,
            logger=logger,
            max_size=16384,
            max_queue=8,
            open_timeout=5,
            close_timeout=2,
        ) as server:
            status["state"] = "listening"
            status["port"] = server.sockets[0].getsockname()[1]
            log("volume_controller_listening")
            await asyncio.Future()
    except (BridgeError, OSError) as error:
        status["state"] = "failed"
        status["error"] = (
            error.code if isinstance(error, BridgeError) else "adapter_port_unavailable"
        )
        log("volume_controller_failed", code=status["error"])
