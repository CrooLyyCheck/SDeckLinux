"""Concrete providers only: Wine URI forwarding and explicit native mappings."""

from __future__ import annotations

import uuid

from .config import Config
from .protocol import BridgeError, exact_keys
from .wine import forward, run_bounded


def capabilities(config: Config) -> dict:
    return {
        "capabilities": [
            {
                "name": "oauth.deepLink",
                "version": 1,
                "enabled": config.deep_links,
                "acknowledgement": "launcher-only",
            },
            {"name": "desktop.launch", "version": 1, "enabled": bool(config.applications)},
            {"name": "desktop.openUrl", "version": 1, "enabled": bool(config.urls)},
        ],
        "events": {"supported": False},
        "automatic_retry": False,
    }


async def execute(config: Config, params: dict) -> dict:
    exact_keys(params, {"capability", "arguments"})
    capability, arguments = params["capability"], params["arguments"]
    if not isinstance(capability, str) or not isinstance(arguments, dict):
        raise BridgeError("invalid_params")
    if capability == "oauth.deepLink":
        exact_keys(arguments, {"uri"})
        return await forward(config, arguments["uri"])
    if capability not in {"desktop.launch", "desktop.openUrl"}:
        raise BridgeError("unsupported_capability")
    exact_keys(arguments, {"target"})
    target = arguments["target"]
    if not isinstance(target, str):
        raise BridgeError("invalid_params")
    if capability == "desktop.launch":
        if target not in config.applications:
            raise BridgeError("target_not_allowed")
        argv = list(config.applications[target])
    else:
        if target not in config.urls:
            raise BridgeError("target_not_allowed")
        argv = ["/usr/bin/xdg-open", config.urls[target]]
    # A separate transient user service keeps native apps alive when the bridge stops.
    # Type=exec confirms execve, not readiness or visible UI.
    unit = "deckbridge-action-" + uuid.uuid4().hex
    await run_bounded(
        [
            "/usr/bin/systemd-run",
            "--user",
            "--collect",
            "--quiet",
            "--expand-environment=no",
            "--service-type=exec",
            "--description=DeckBridge native action",
            "--property=StandardOutput=null",
            "--property=StandardError=null",
            "--unit=" + unit,
            "--",
            *argv,
        ]
    )
    return {"status": "started-unconfirmed", "unit": unit, "application_ack": False}
