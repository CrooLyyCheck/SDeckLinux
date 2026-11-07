"""Authenticate an unchanged Windows client's TCP connection by kernel ownership.

The vendor client sends no credential. Only the matching same-user Wine Node
process running the hash/version-pinned plugin may access this adapter.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ....config import Config
from ....protocol import BridgeError

CONTRACT = json.loads(Path(__file__).with_name("contract.json").read_text())


def plugin_directory(config: Config) -> Path:
    paths = list(
        (config.prefix / "drive_c/users").glob(
            "*/AppData/Roaming/Elgato/StreamDeck/Plugins/com.elgato.volume-controller.sdPlugin"
        )
    )
    if len(paths) != 1:
        raise BridgeError("volume_controller_not_found")
    return paths[0]


def verify_plugin(config: Config) -> Path:
    root = plugin_directory(config)
    for relative, expected in CONTRACT["files"].items():
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise BridgeError("volume_controller_contract_mismatch")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise BridgeError("volume_controller_contract_mismatch")
    return root


def plugin_pids(config: Config, root: Path, proc_root: Path = Path("/proc")) -> list[int]:
    script = root / "bin/plugin.js"
    windows = "c:/" + str(script.relative_to(config.prefix / "drive_c")).replace("\\", "/")
    valid_scripts = {str(script).lower(), windows.lower(), ("z:" + str(script)).lower()}
    expected_node = root.parents[1] / "NodeJS/20.20.2/node.exe"
    node_windows = "c:/" + str(expected_node.relative_to(config.prefix / "drive_c")).replace(
        "\\", "/"
    )
    valid_nodes = {str(expected_node).lower(), node_windows.lower()}
    result = []
    for proc in proc_root.glob("[0-9]*"):
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            args = [os.fsdecode(a) for a in (proc / "cmdline").read_bytes().split(b"\0") if a]
            if len(args) < 2 or args[0].replace("\\", "/").lower() not in valid_nodes:
                continue
            position = 1
            while position < len(args) and args[position] == "--no-global-search-paths":
                position += 1
            if (
                position >= len(args)
                or args[position].replace("\\", "/").lower() not in valid_scripts
            ):
                continue
            env = dict(
                x.split(b"=", 1) for x in (proc / "environ").read_bytes().split(b"\0") if b"=" in x
            )
            if env.get(b"WINEPREFIX") != os.fsencode(config.prefix) or "-info" not in args:
                continue
            info = json.loads(args[args.index("-info") + 1])
            public = info.get("plugin", {})
            if (public.get("uuid"), public.get("version")) == (
                CONTRACT["plugin_uuid"],
                CONTRACT["plugin_version"],
            ):
                result.append(int(proc.name))
        except (OSError, ValueError, IndexError):
            continue  # Exited/inaccessible/non-matching processes are never authenticated.
    return result


def matching_inodes(tcp: str, peer_port: int, server_port: int, uid: int) -> set[str]:
    result = set()
    for line in tcp.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 10:
            continue
        if (
            fields[1] == f"0100007F:{peer_port:04X}"
            and fields[2] == f"0100007F:{server_port:04X}"
            and fields[3] == "01"
            and fields[7] == str(uid)
        ):
            result.add(fields[9])
    return result


def authenticate(
    config: Config, root: Path, address: tuple, port: int = 1844, proc_root: Path = Path("/proc")
) -> int | None:
    if address[0] != "127.0.0.1":
        return None
    inodes = matching_inodes((proc_root / "net/tcp").read_text(), address[1], port, os.getuid())
    if not inodes:
        return None
    for pid in plugin_pids(config, root, proc_root):
        try:
            for fd in (proc_root / str(pid) / "fd").iterdir():
                try:
                    if os.readlink(fd) in {f"socket:[{i}]" for i in inodes}:
                        return pid
                except FileNotFoundError:
                    continue
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return None
