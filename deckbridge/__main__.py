"""Small CLI; no interactive UI or shell command endpoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from .client import call
from .compat.sdeck.oauth.uri import from_desktop
from .config import default_config, load, socket_path
from .protocol import BridgeError
from .server import serve


async def main(args: argparse.Namespace) -> dict | None:
    path = socket_path()
    if args.command == "serve":
        await serve(load(args.config), path)
        return None
    if args.command == "diagnose":
        return await call(path, "diagnostics.get", {})
    if args.command == "capabilities":
        return await call(path, "capabilities.list", {})
    if args.command == "audio":
        capability = {
            "list": "audio.sessions.list",
            "set-volume": "audio.session.volume",
            "set-mute": "audio.session.mute",
        }[args.audio_command]
        arguments = {}
        if args.audio_command == "set-volume":
            arguments = {"target": args.target, "volume": args.volume / 100}
        elif args.audio_command == "set-mute":
            arguments = {"target": args.target, "mute": args.mute == "true"}
        return await call(
            path, "actions.execute", {"capability": capability, "arguments": arguments}
        )
    capability = {
        "deep-link": "oauth.deepLink",
        "handle-uri": "oauth.deepLink",
        "launch": "desktop.launch",
        "open-url": "desktop.openUrl",
    }[args.command]
    if args.command == "handle-uri":
        arguments = {"uri": from_desktop(args.value)}
    else:
        arguments = {"uri": args.value} if args.command == "deep-link" else {"target": args.value}
    return await call(path, "actions.execute", {"capability": capability, "arguments": arguments})


def entrypoint() -> int:
    os.umask(0o077)
    if os.getuid() == 0:
        print('{"error":"desktop_user_required"}', file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(prog="deckbridge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve").add_argument("--config", type=Path, default=default_config())
    for command in ("diagnose", "capabilities"):
        sub.add_parser(command)
    for command in ("deep-link", "handle-uri", "launch", "open-url"):
        sub.add_parser(command).add_argument("value")
    audio = sub.add_parser("audio").add_subparsers(dest="audio_command", required=True)
    audio.add_parser("list")
    volume = audio.add_parser("set-volume")
    volume.add_argument("target", help="session ID or application key from audio list")
    volume.add_argument("volume", type=float, help="0..100 percent; never controls system volume")
    mute = audio.add_parser("set-mute")
    mute.add_argument("target")
    mute.add_argument("mute", choices=("true", "false"))
    args = parser.parse_args()
    try:
        result = asyncio.run(main(args))
    except BridgeError as exc:
        print(json.dumps({"error": exc.code}), file=sys.stderr)
        return 1
    except (OSError, TimeoutError):
        print('{"error":"unavailable_or_timeout_outcome_unknown"}', file=sys.stderr)
        return 1
    if result is not None:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(entrypoint())
