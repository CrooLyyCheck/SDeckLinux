"""Observed Audio Router contract for Volume Controller 2.0.5.201 only."""

from __future__ import annotations

import json

from ....backends.audio.pipewire import AudioBackend
from ....backends.desktop.icons import IconProvider
from ....protocol import BridgeError, reject_constant, unique_object


class Router:
    def __init__(self, backend: AudioBackend, *, display: str = "icons", hide_events: bool = True):
        self.backend = backend
        self.ids: dict[str, int] = {}
        self.next_id = 1
        self.requests = 0
        self.enumerated: set[str] = set()
        self.previous_system: dict | None = None
        self.display, self.hide_events = display, hide_events
        self.icons = IconProvider()
        self.sync_system = False

    def apps(self) -> list[dict]:
        apps = [
            a for a in self.backend.applications if not (self.hide_events and a.get("event_only"))
        ]
        for app in apps:
            if app["id"] not in self.ids:
                self.ids[app["id"]] = self.next_id
                self.next_id += 1
        return apps

    def describe(self, app: dict) -> dict:
        return {
            "processID": self.ids[app["id"]],
            "displayName": app["name"][:256],
            "executableFile": "deckbridge-audio:" + app["id"],
            "volume": app["volume"],
            "mute": app["mute"],
            "activity": 2 if app["controllable"] else 4,
        }

    def by_id(self, process_id: object) -> dict | None:
        if type(process_id) is not int or process_id <= 0:
            raise BridgeError("audio_application_gone")
        return next((app for app in self.apps() if self.ids[app["id"]] == process_id), None)

    async def request(self, raw: str) -> dict:
        request_id = None
        try:
            if not isinstance(raw, str) or len(raw) > 16384:
                raise BridgeError("invalid_request")
            try:
                obj = json.loads(
                    raw, object_pairs_hook=unique_object, parse_constant=reject_constant
                )
            except (ValueError, UnicodeError, RecursionError):
                raise BridgeError("invalid_request") from None
            if (
                not isinstance(obj, dict)
                or set(obj) - {"id", "jsonrpc", "method", "params"}
                or obj.get("jsonrpc") != "2.0"
                or type(obj.get("id")) is not int
                or not 0 <= obj["id"] < 2**53
                or not isinstance(obj.get("method"), str)
            ):
                raise BridgeError("invalid_request")
            request_id = obj["id"]
            method, params = obj["method"], obj.get("params", {})
            if not isinstance(params, dict):
                raise BridgeError("invalid_params")
            await self.backend.snapshot()
            apps = self.apps()
            if method == "getApplicationInstanceCount" and not params:
                result = {"count": len(apps)}
            elif method == "getSystemDefaultDevice" and not params:
                result = {
                    "volume": self.backend.system["volume"],
                    "mute": self.backend.system["mute"],
                }
            elif method == "getApplicationInstanceAtIndex" and set(params) == {"index"}:
                index = params["index"]
                if type(index) is not int or not 0 <= index < len(apps):
                    raise BridgeError("audio_application_gone")
                app = apps[index]
                self.enumerated.add(app["id"])
                result = self.describe(app)
            elif method == "getApplicationInstance" and set(params) == {"processID"}:
                app = self.by_id(params["processID"])
                if not app:
                    raise BridgeError("audio_application_gone")
                self.enumerated.add(app["id"])
                result = self.describe(app)
            elif method == "getApplicationInstanceImage" and set(params) == {
                "processID",
                "imageSize",
            }:
                app = self.by_id(params["processID"])
                if not app:
                    raise BridgeError("audio_application_gone")
                image = await self.icons.image(app) if self.display == "icons" else None
                self.backend.adapter_status["icon_cache_entries"] = len(self.icons.cache)
                self.backend.adapter_status["icon_error"] = self.icons.failure
                if image:
                    status = self.backend.adapter_status
                    status["icon_images_served"] = status.get("icon_images_served", 0) + 1
                self.sync_system = True
                result = {
                    "processID": self.ids[app["id"]],
                    "image": image,
                    "imageSize": len(image) * 3 // 4 - image[-2:].count("=") if image else 0,
                    "imageFormat": "png",
                }
            elif method == "setApplicationInstanceVolume" and set(params) == {
                "processID",
                "volume",
            }:
                app = self.by_id(params["processID"])
                if not app or type(params["volume"]) not in (int, float):
                    raise BridgeError("invalid_params")
                result = await self.backend.set_target(app["id"], volume=params["volume"])
            elif method == "setApplicationInstanceMute" and set(params) == {"processID", "mute"}:
                app = self.by_id(params["processID"])
                if not app:
                    raise BridgeError("audio_application_gone")
                result = await self.backend.set_target(app["id"], mute=params["mute"])
            elif method in {"setSystemDefaultDeviceVolume", "setSystemDefaultDeviceMute"}:
                field = "volume" if method == "setSystemDefaultDeviceVolume" else "mute"
                if (
                    set(params) != {"processID", field}
                    or type(params["processID"]) is not int
                    or params["processID"] != 0
                ):
                    raise BridgeError("invalid_params")
                result = await self.backend.set_system(**{field: params[field]})
            else:
                raise BridgeError("unsupported_router_method")
            self.requests += 1
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (BridgeError, OSError, TimeoutError) as error:
            code = (
                error.code
                if isinstance(error, BridgeError)
                else "timeout_outcome_unknown"
                if isinstance(error, TimeoutError)
                else "audio_backend_failed"
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": code},
            }

    def followup_events(self) -> list[dict]:
        if not self.sync_system:
            return []
        self.sync_system = False
        # The original client rekeys System from a string to numeric zero when
        # the first application is inserted. Its image request proves that step
        # completed; resynchronize the default state after that observed boundary.
        return [
            {
                "jsonrpc": "2.0",
                "method": "systemDefaultDeviceChanged",
                "params": {"processID": 0, **self.backend.system},
            }
        ]

    def notifications(self, previous: dict[str, dict]) -> tuple[list[dict], dict[str, dict]]:
        current = {a["id"]: self.describe(a) for a in self.apps()}
        events = []
        if self.previous_system is not None:
            for field, method in (
                ("volume", "currentSystemDefaultDeviceVolumeChanged"),
                ("mute", "currentSystemDefaultDeviceMuteChanged"),
            ):
                if self.backend.system[field] != self.previous_system[field]:
                    events.append((method, {"processID": 0, field: self.backend.system[field]}))
        self.previous_system = dict(self.backend.system)
        for key in previous.keys() - current.keys():
            events.append(
                ("appInstanceAddRemove", {"processID": self.ids[key], "appAddedRemoved": "Removed"})
            )
        for key in current.keys() - previous.keys():
            events.append(
                ("appInstanceAddRemove", {"processID": self.ids[key], "appAddedRemoved": "Added"})
            )
        for key in current.keys() & previous.keys():
            for field, method in (
                ("volume", "preferredSessionInstanceVolumeChanged"),
                ("mute", "preferredSessionInstanceMuteChanged"),
                ("activity", "appInstanceActivityChanged"),
            ):
                if current[key][field] != previous[key][field]:
                    events.append(
                        (method, {"processID": self.ids[key], field: current[key][field]})
                    )
        return (
            [{"jsonrpc": "2.0", "method": method, "params": params} for method, params in events],
            current,
        )
