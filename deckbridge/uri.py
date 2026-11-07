"""Validate without decoding, re-encoding, truncating or logging the URI."""

import re
from urllib.parse import quote, urlsplit

from .protocol import BridgeError


def validate(value: object, schemes: set[str]) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError("invalid_uri")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise BridgeError("invalid_uri") from None
    if size > 8192:
        raise BridgeError("invalid_uri")
    if any(ord(c) <= 32 or ord(c) == 127 or c in '\\"<>`{}|^' for c in value):
        raise BridgeError("invalid_uri")
    if re.search(r"%(?![a-fA-F0-9]{2})", value):
        raise BridgeError("invalid_percent_encoding")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise BridgeError("invalid_uri") from None
    if (
        parts.scheme.lower() not in schemes
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise BridgeError("uri_not_allowed")
    if parts.scheme.lower() == "streamdeck" and port is not None:
        raise BridgeError("uri_not_allowed")
    return value


def validate_deep_link(value: object) -> str:
    return validate(value, {"streamdeck"})


def validate_url(value: object) -> str:
    return validate(value, {"http", "https"})


def from_desktop(value: str) -> str:
    """KDE %u decodes spaces/Unicode; restore their URI encoding only at ingress.

    Reserved escapes and percent signs remain opaque. Never unquote the URI.
    """
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise BridgeError("invalid_uri")
    try:
        encoded = quote(value, safe=":/?#[]@!$&'()*+,;=%-._~")
    except UnicodeError:
        raise BridgeError("invalid_uri") from None
    return validate_deep_link(encoded)
