"""Narrow access to the portal's remembered Stream Deck application choices."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from ....protocol import BridgeError

SERVICE = "org.freedesktop.impl.portal.PermissionStore"
OBJECT = "/org/freedesktop/impl/portal/PermissionStore"
TABLE = "desktop-used-apps"
MIME = "x-scheme-handler/streamdeck"
HANDLER = "io.deckbridge.UrlHandler"
LEGACY = "streamdeck-wine"


def call(method: str, signature: str, *arguments: str) -> dict[str, Any] | None:
    try:
        result = subprocess.run(  # noqa: S603 - fixed service/methods, argv only
            [
                "/usr/bin/busctl",
                "--user",
                "--json=short",
                "call",
                SERVICE,
                OBJECT,
                SERVICE,
                method,
                signature,
                *arguments,
            ],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        raise BridgeError("portal_unavailable") from None
    if len(result.stdout) > 65536:
        raise BridgeError("portal_invalid_response")
    if not result.stdout.strip():
        return None
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise BridgeError("portal_invalid_response") from None
    if not isinstance(value, dict):
        raise BridgeError("portal_invalid_response")
    return value


def read_permissions() -> dict[str, list[str]]:
    listing = call("List", "s", TABLE)
    if (
        not listing
        or listing.get("type") != "as"
        or not isinstance(listing.get("data"), list)
        or len(listing["data"]) != 1
        or not isinstance(listing["data"][0], list)
    ):
        raise BridgeError("portal_invalid_response")
    if MIME not in listing["data"][0]:
        return {}
    reply = call("Lookup", "ss", TABLE, MIME)
    if (
        not reply
        or reply.get("type") != "a{sas}v"
        or not isinstance(reply.get("data"), list)
        or len(reply["data"]) != 2
        or not isinstance(reply["data"][0], dict)
    ):
        raise BridgeError("portal_invalid_response")
    permissions = reply["data"][0]
    for app, values in permissions.items():
        if (
            not isinstance(app, str)
            or not isinstance(values, list)
            or any(not isinstance(value, str) for value in values)
        ):
            raise BridgeError("portal_invalid_response")
    return permissions


def legacy_choices(permissions: dict[str, list[str]]) -> dict[str, list[str]]:
    changes = {}
    for app, values in permissions.items():
        if not values or values[0] != LEGACY:
            continue
        if len(values) not in (2, 3) or any(value and not value.isdigit() for value in values[1:]):
            raise BridgeError("portal_choice_unrecognized")
        changes[app] = [HANDLER, *values[1:]]
    return changes


def set_permission(app: str, values: list[str]) -> None:
    # SetPermission preserves other callers' entries and the opaque data variant,
    # including always-ask. It never changes browser external-protocol consent.
    call("SetPermission", "sbssas", TABLE, "false", MIME, app, str(len(values)), *values)
    if read_permissions().get(app) != values:
        raise BridgeError("portal_write_unconfirmed")


def summary(permissions: dict[str, list[str]]) -> dict:
    values = permissions.get("", [])  # Unsandboxed callers share the empty application ID.
    first = values[0] if values else None
    return {
        "unsandboxed_handler": "deckbridge"
        if first == HANDLER
        else "legacy-wine-launcher"
        if first == LEGACY
        else "other"
        if first
        else "unset",
        "legacy_choice_count": sum(bool(v) and v[0] == LEGACY for v in permissions.values()),
    }
