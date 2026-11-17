"""Optional installed Core Audio service with exact owned-library validation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
from pathlib import Path

from ....config import Config
from .activation import library_path
from .transport import endpoint_server


def installed_library(data: Path, state: Path) -> Path:
    library = library_path(data)
    manifest_path = state / "install.json"
    contents = {}
    for path, limit in ((library, 4 * 1024 * 1024), (manifest_path, 1024 * 1024)):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or not 0 < info.st_size <= limit
            ):
                raise RuntimeError("Unsafe Core Audio runtime ownership")
            contents[path] = stream.read(limit + 1)
        if len(contents[path]) > limit:
            raise RuntimeError("Unsafe Core Audio runtime ownership")
    manifest = json.loads(contents[manifest_path])
    if (
        not isinstance(manifest, dict)
        or manifest.get("version") != 1
        or not isinstance(manifest.get("files"), dict)
        or hashlib.sha256(contents[library]).hexdigest()
        != manifest.get("files", {}).get(str(library))
    ):
        raise RuntimeError("Core Audio runtime hash mismatch")
    return library


async def run(config: Config, backend, status: dict) -> None:
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "deckbridge"
    try:
        library = await asyncio.to_thread(installed_library, data, state)
        failed = asyncio.Event()
        async with endpoint_server(config.prefix, library, backend, on_failure=failed.set) as (
            _,
            stats,
        ):
            status.update(listening=True, error="", transport=stats)
            await failed.wait()
            status["error"] = "core_audio_monitor_failed"
    except (OSError, RuntimeError, ValueError):
        status.update(listening=False, error="core_audio_unavailable")
    finally:
        status["listening"] = False
