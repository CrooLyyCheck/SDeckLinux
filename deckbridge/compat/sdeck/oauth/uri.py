"""Stream Deck deep-link validation and KDE URL ingress."""

from urllib.parse import quote

from ....protocol import BridgeError
from ....uri import validate


def validate_deep_link(value: object) -> str:
    return validate(value, {"streamdeck"})


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
