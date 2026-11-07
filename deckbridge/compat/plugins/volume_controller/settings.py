"""Local CLI preference editing; no writes to vendor files or Wine profiles."""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from pathlib import Path

from ....config import load
from ....protocol import BridgeError


def set_display(path: Path, mode: str) -> bool:
    if mode not in {"icons", "text"}:
        raise BridgeError("invalid_params")
    config = load(path)
    if config.volume_controller_display == mode:
        return False
    original = path.read_bytes()
    if len(original) > 65536:
        raise BridgeError("config_layout_unsupported")
    lines = original.decode().splitlines(keepends=True)
    starts = [
        i
        for i, line in enumerate(lines)
        if re.fullmatch(r"\s*\[compat\.volume_controller\]\s*(?:#.*)?\n?", line)
    ]
    if len(starts) != 1:
        raise BridgeError("config_layout_unsupported")
    start = starts[0] + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].lstrip().startswith("[")), len(lines)
    )
    existing = [i for i in range(start, end) if re.match(r"\s*display\s*=", lines[i])]
    value = f'display = "{mode}"\n'
    if existing:
        if len(existing) != 1:
            raise BridgeError("config_layout_unsupported")
        lines[existing[0]] = value
    else:
        if start and not lines[start - 1].endswith("\n"):
            lines[start - 1] += "\n"
        lines.insert(start, value)
    fd, name = tempfile.mkstemp(prefix=".deckbridge-display-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write("".join(lines))
        load(temporary)
        if path.is_symlink() or path.read_bytes() != original:
            raise BridgeError("config_changed")
        backup = (
            Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
            / "deckbridge/backups"
        )
        backup.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            backup / ("before-icon-display-" + uuid.uuid4().hex + ".toml"),
            os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(original)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True
