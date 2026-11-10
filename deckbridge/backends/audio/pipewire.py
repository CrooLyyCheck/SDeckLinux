"""PipeWire graph observations, with explicit per-stream pipewire-pulse control.

Direct PipeWire streams remain visible but read-only in this initial backend.
Default-output control is separately opt-in and never changes default routing.
"""

from __future__ import annotations

import asyncio
import codecs
import json

from ...protocol import BridgeError
from .command import MAX_GRAPH_BYTES, command
from .devices import DeviceBackend
from .model import Session, application_key, balanced_channels, group_sessions


def sessions_from_graph(objects: list[dict], pulse: list[dict], cookie: int) -> list[Session]:
    if not isinstance(objects, list) or not isinstance(pulse, list) or type(cookie) is not int:
        raise BridgeError("audio_invalid_snapshot")
    controls = {}
    for item in pulse:
        if not isinstance(item, dict) or not isinstance(item.get("properties", {}), dict):
            raise BridgeError("audio_invalid_snapshot")
        props = item.get("properties", {})
        try:
            controls[int(props["object.serial"])] = item
        except (KeyError, TypeError, ValueError):
            continue  # Not a native PipeWire-backed Pulse stream; never guess an ID.
    sessions = []
    for obj in objects:
        if not isinstance(obj, dict) or not isinstance(obj.get("info") or {}, dict):
            raise BridgeError("audio_invalid_snapshot")
        info = obj.get("info") or {}
        props = info.get("props", {})
        if (
            obj.get("type") != "PipeWire:Interface:Node"
            or props.get("media.class") != "Stream/Output/Audio"
        ):
            continue
        serial = props.get("object.serial")
        if type(serial) is not int:
            raise BridgeError("audio_invalid_snapshot")
        control = controls.get(serial)
        params = (info.get("params", {}).get("Props") or [{}])[0]
        channels = (
            tuple(v["value"] for v in control["volume"].values())
            if control
            else tuple(
                round(max(0, v) ** (1 / 3) * 65536) for v in params.get("channelVolumes", [])
            )
        )
        pid = props.get("application.process.id")
        if (
            len(channels) > 64
            or any(type(v) is not int or not 0 <= v < 2**31 for v in channels)
            or (control and (type(control.get("index")) is not int or control["index"] < 0))
        ):
            raise BridgeError("audio_invalid_snapshot")
        sessions.append(
            Session(
                id=f"pw:{cookie}:{serial}",
                node_id=obj["id"],
                serial=serial,
                application_key=application_key(props),
                name=str(
                    props.get("application.name") or props.get("node.name") or "Audio application"
                ),
                executable=str(props.get("application.process.binary") or "unknown"),
                reported_pid=int(pid) if str(pid).isdigit() else None,
                flatpak_id=props.get("pipewire.access.portal.app_id"),
                channels=channels,
                mute=bool(control["mute"] if control else params.get("mute", False)),
                pulse_index=control["index"] if control else None,
                icon_name=props.get("application.icon-name") or props.get("application.icon_name"),
                event_stream=(
                    props.get("media.role") in {"event", "notification"}
                    or bool(props.get("event.id"))
                    or str(props.get("application.name", "")).casefold() == "libcanberra"
                    or props.get("application.process.binary") == "canberra-gtk-play"
                ),
            )
        )
    return sorted(sessions, key=lambda s: s.serial)


class AudioBackend:
    def __init__(
        self,
        allow_write: bool = False,
        allowed_apps: tuple[str, ...] = (),
        *,
        allow_system_write: bool = False,
        allow_output_write: bool = False,
        allow_input_write: bool = False,
        allowed_devices: tuple[str, ...] = (),
    ):
        self.allow_write = allow_write
        self.allowed_apps = allowed_apps
        self.allow_system_write = allow_system_write
        self.devices = DeviceBackend(
            allow_output=allow_output_write,
            allow_input=allow_input_write,
            allowed_devices=allowed_devices,
        )
        self.sessions: list[Session] = []
        self.applications: list[dict] = []
        self.system = {"volume": 0.0, "mute": False}
        self.cookie: int | None = None
        self.revision = 0
        self.changed = asyncio.Condition()
        self.ready = asyncio.Event()
        self.failure: str | None = None
        self._action_lock = asyncio.Lock()
        self.adapter_status = {
            "state": "disabled",
            "connected_clients": 0,
            "requests_completed": 0,
            "enumerated_applications": 0,
        }

    async def refresh(self, objects: list[dict]) -> None:
        core = next((o for o in objects if o.get("type") == "PipeWire:Interface:Core"), None)
        if not core or type(core.get("info", {}).get("cookie")) is not int:
            raise BridgeError("audio_invalid_snapshot")
        cookie = core["info"]["cookie"]
        pulse = await command("/usr/bin/pactl", "-f", "json", "list", "sink-inputs")
        info = await command("/usr/bin/pactl", "-f", "json", "info")
        if not str(info.get("server_name", "")).startswith("PulseAudio (on PipeWire "):
            raise BridgeError("pipewire_pulse_required")
        sinks = await command("/usr/bin/pactl", "-f", "json", "list", "sinks")
        default = next((s for s in sinks if s["name"] == info.get("default_sink_name")), None)
        system = (
            {
                "volume": max(v["value"] for v in default["volume"].values()) / 65536,
                "mute": default["mute"],
            }
            if default
            else {"volume": 0.0, "mute": False}
        )
        sessions = sessions_from_graph(objects, pulse, cookie)
        apps = group_sessions(sessions)
        if (sessions, system, cookie) != (self.sessions, self.system, self.cookie):
            self.sessions, self.applications, self.system, self.cookie = (
                sessions,
                apps,
                system,
                cookie,
            )
            async with self.changed:
                self.revision += 1
                self.changed.notify_all()
        self.ready.set()

    async def snapshot(self) -> dict:
        if self.failure:
            raise BridgeError(self.failure)
        if not self.ready.is_set():
            raise BridgeError("audio_not_ready")
        return {
            "version": 1,
            "backend": "pipewire+pipewire-pulse",
            "revision": self.revision,
            "applications": self.applications,
            "system": self.system,
            "write_enabled": self.allow_write,
            "system_write_enabled": self.allow_system_write,
        }

    async def set_system(self, *, volume=None, mute=None) -> dict:
        if not self.allow_system_write:
            raise BridgeError("global_audio_control_disabled")
        if (volume is None) == (mute is None) or (mute is not None and type(mute) is not bool):
            raise BridgeError("invalid_params")
        async with self._action_lock:
            await self.snapshot()
            info = await command("/usr/bin/pactl", "-f", "json", "info")
            sinks = await command("/usr/bin/pactl", "-f", "json", "list", "sinks")
            sink = next((s for s in sinks if s["name"] == info.get("default_sink_name")), None)
            if not sink:
                raise BridgeError("audio_default_output_missing")
            index = sink.get("index")
            serial = sink.get("properties", {}).get("object.serial")
            if type(index) is not int or not str(serial).isdigit():
                raise BridgeError("audio_invalid_snapshot")
            channels = tuple(v["value"] for v in sink["volume"].values())
            values = balanced_channels(channels, volume) if volume is not None else []
            # Select the named default once, then validate identity immediately before use.
            fresh = await command("/usr/bin/pactl", "-f", "json", "list", "sinks")
            current_info = await command("/usr/bin/pactl", "-f", "json", "info")
            if (
                info.get("cookie") != current_info.get("cookie")
                or not any(
                    s.get("index") == index
                    and s.get("name") == sink["name"]
                    and s.get("properties", {}).get("object.serial") == serial
                    for s in fresh
                )
                or current_info.get("default_sink_name") != sink["name"]
            ):
                raise BridgeError("audio_default_output_changed")
            await command(
                "/usr/bin/pactl",
                "set-sink-volume" if volume is not None else "set-sink-mute",
                str(index),
                *(values if volume is not None else ["1" if mute else "0"]),
                json_output=False,
            )
            await self.refresh(await command("/usr/bin/pw-dump", "--no-colors"))
            return {"status": "applied", "output_count": 1}

    async def run(self) -> None:
        monitor = None
        graph: dict[int, dict] = {}
        decoder, buffer = json.JSONDecoder(), ""
        utf8 = codecs.getincrementaldecoder("utf-8")()
        try:
            monitor = await asyncio.create_subprocess_exec(
                "/usr/bin/pw-dump",
                "--monitor",
                "--no-colors",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            while chunk := await monitor.stdout.read(65536):
                buffer += utf8.decode(chunk)
                if len(buffer) > MAX_GRAPH_BYTES:
                    raise BridgeError("audio_snapshot_too_large")
                while buffer.strip():
                    buffer = buffer.lstrip()
                    try:
                        update, offset = decoder.raw_decode(buffer)
                    except ValueError:
                        break  # Bounded incremental JSON, not a retry or action replay.
                    buffer = buffer[offset:]
                    relevant = not self.ready.is_set()
                    if not isinstance(update, list):
                        raise BridgeError("audio_invalid_snapshot")
                    for obj in update:
                        old = graph.get(obj["id"], {})
                        kind = obj.get("type", old.get("type"))
                        if kind in {
                            "PipeWire:Interface:Core",
                            "PipeWire:Interface:Node",
                            "PipeWire:Interface:Metadata",
                        }:
                            relevant = True
                        if obj.get("info", "present") is None:
                            graph.pop(obj["id"], None)
                        elif "info" in obj:
                            merged = {**old, **obj}
                            merged["info"] = {**old.get("info", {}), **obj["info"]}
                            graph[obj["id"]] = merged
                    if relevant:
                        await self.refresh(list(graph.values()))
            raise BridgeError("audio_backend_disconnected")
        except (BridgeError, OSError, UnicodeError, TimeoutError) as error:
            self.failure = error.code if isinstance(error, BridgeError) else "audio_backend_failed"
            self.ready.set()
            async with self.changed:
                self.revision += 1
                self.changed.notify_all()
        finally:
            if monitor:
                if monitor.returncode is None:
                    monitor.kill()
                await monitor.wait()

    async def set_target(self, key: str, *, volume=None, mute=None) -> dict:
        if not self.allow_write:
            raise BridgeError("audio_write_disabled")
        if (volume is None) == (mute is None) or (mute is not None and type(mute) is not bool):
            raise BridgeError("invalid_params")
        async with self._action_lock:
            await self.snapshot()
            members = [s for s in self.sessions if s.application_key == key or s.id == key]
            if not members:
                raise BridgeError("audio_application_gone")
            if self.allowed_apps and any(
                s.application_key not in self.allowed_apps for s in members
            ):
                raise BridgeError("audio_write_disabled")
            if any(s.pulse_index is None for s in members):
                raise BridgeError("audio_stream_read_only")
            updates = {
                s.id: balanced_channels(s.channels, volume) if volume is not None else []
                for s in members
            }
            fresh_graph = await command("/usr/bin/pw-dump", "--no-colors")
            fresh_cookie = next(
                (
                    o["info"]["cookie"]
                    for o in fresh_graph
                    if o.get("type") == "PipeWire:Interface:Core"
                ),
                None,
            )
            pulse = await command("/usr/bin/pactl", "-f", "json", "list", "sink-inputs")
            fresh = sessions_from_graph(fresh_graph, pulse, fresh_cookie)
            current = {s.id: s for s in fresh}
            if any(
                s.id not in current or current[s.id].pulse_index != s.pulse_index for s in members
            ):
                raise BridgeError("audio_stream_gone")
            completed = 0
            try:
                for session in members:
                    if volume is not None:
                        await command(
                            "/usr/bin/pactl",
                            "set-sink-input-volume",
                            str(session.pulse_index),
                            *updates[session.id],
                            json_output=False,
                        )
                    else:
                        await command(
                            "/usr/bin/pactl",
                            "set-sink-input-mute",
                            str(session.pulse_index),
                            "1" if mute else "0",
                            json_output=False,
                        )
                    completed += 1
            except BridgeError:
                raise BridgeError(
                    "audio_partial_action" if completed else "audio_action_failed"
                ) from None
            await self.refresh(await command("/usr/bin/pw-dump", "--no-colors"))
            return {"status": "applied", "stream_count": completed}
