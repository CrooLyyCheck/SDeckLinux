"""Protocol v1: one bounded JSON request/response per connection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

VERSION = 1
MAX_FRAME = 16384
IO_TIMEOUT = 5.0
ACTION_TIMEOUT = 10.0
METHODS = {"capabilities.list", "diagnostics.get", "actions.execute"}
WIRE_ERRORS = frozenset(
    {
        "invalid_frame",
        "invalid_json",
        "duplicate_json_key",
        "invalid_json_constant",
        "invalid_request",
        "unsupported_version",
        "invalid_id",
        "unsupported_method",
        "invalid_params",
        "invalid_uri",
        "invalid_percent_encoding",
        "uri_not_allowed",
        "capability_disabled",
        "instance_missing",
        "instance_ambiguous",
        "instance_lost",
        "launcher_failed",
        "unsupported_capability",
        "target_not_allowed",
        "peer_not_allowed",
        "backend_unavailable",
        "timeout_outcome_unknown",
        "response_too_large",
    }
)


class BridgeError(Exception):
    """Only fixed, non-sensitive error codes cross the IPC/log boundary."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Request:
    id: str
    method: str
    params: dict[str, Any]


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BridgeError("duplicate_json_key")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise BridgeError("invalid_json_constant")


def decode_request(data: bytes) -> Request:
    if len(data) > MAX_FRAME or not data.endswith(b"\n"):
        raise BridgeError("invalid_frame")
    try:
        obj = json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise BridgeError("invalid_json") from None
    if not isinstance(obj, dict) or set(obj) != {"v", "id", "method", "params"}:
        raise BridgeError("invalid_request")
    if type(obj["v"]) is not int or obj["v"] != VERSION:
        raise BridgeError("unsupported_version")
    if not isinstance(obj["id"], str) or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", obj["id"]):
        raise BridgeError("invalid_id")
    if not isinstance(obj["method"], str) or obj["method"] not in METHODS:
        raise BridgeError("unsupported_method")
    if not isinstance(obj["params"], dict):
        raise BridgeError("invalid_params")
    return Request(obj["id"], obj["method"], obj["params"])


def encode(obj: dict[str, Any]) -> bytes:
    data = json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"
    if len(data) > MAX_FRAME:
        raise BridgeError("response_too_large")
    return data


def exact_keys(obj: dict, keys: set[str]) -> None:
    if set(obj) != keys:
        raise BridgeError("invalid_params")
