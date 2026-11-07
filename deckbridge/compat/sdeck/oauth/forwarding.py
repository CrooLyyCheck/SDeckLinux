"""Forward Stream Deck callbacks through the existing exact-prefix Wine instance."""

import asyncio
import os

from ....config import Config
from ....protocol import BridgeError
from ....wine import run_bounded, running_instances
from .uri import validate_deep_link


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
