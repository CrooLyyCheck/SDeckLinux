"""Host audio identities and grouping, independent of Windows/plugin wire models."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from ...protocol import BridgeError


@dataclass(frozen=True)
class Session:
    id: str
    node_id: int
    serial: int
    application_key: str
    name: str
    executable: str
    reported_pid: int | None
    flatpak_id: str | None
    channels: tuple[int, ...]  # PulseAudio scalar units, 65536 = 100%.
    mute: bool
    pulse_index: int | None

    @property
    def volume(self) -> float:
        return max(self.channels, default=0) / 65536


def application_key(props: dict) -> str:
    flatpak = props.get("pipewire.access.portal.app_id")
    app_id = props.get("application.id")
    binary = str(
        props.get("application.process.binary") or props.get("application.name") or "unknown"
    )
    if flatpak:
        return "flatpak:" + str(flatpak)
    if app_id:
        return "app:" + str(app_id)
    return "binary:" + binary


def balanced_channels(old: tuple[int, ...], volume: object) -> list[str]:
    if type(volume) not in (int, float) or not math.isfinite(volume) or not 0 <= volume <= 1:
        raise BridgeError("invalid_audio_volume")
    peak = max(old, default=0)
    return [str(round(volume * 65536 * (value / peak if peak else 1))) for value in old]


def group_sessions(sessions: list[Session]) -> list[dict]:
    groups: dict[str, list[Session]] = {}
    for session in sessions:
        groups.setdefault(session.application_key, []).append(session)
    return [
        {
            "id": key,
            "name": members[0].name,
            "executable": members[0].executable,
            "volume": max(s.volume for s in members),
            "mute": all(s.mute for s in members),
            "mixed_mute": len({s.mute for s in members}) > 1,
            "controllable": all(s.pulse_index is not None for s in members),
            "sessions": [asdict(s) for s in members],
        }
        for key, members in sorted(groups.items())
    ]
