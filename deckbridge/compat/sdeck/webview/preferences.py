"""Preserve unrelated private TOML while applying an explicitly selected mode."""

from __future__ import annotations

import copy
import re
import tomllib


def with_mode(original: bytes, mode: str) -> bytes:
    if mode not in {"compatible", "sandboxed"} or len(original) > 65536:
        raise RuntimeError("Invalid WebEngine mode or oversized configuration")
    try:
        parsed = tomllib.loads(original.decode())
    except (ValueError, UnicodeError):
        raise RuntimeError("Invalid private configuration; preserving it") from None
    lines = original.decode().splitlines(keepends=True)
    starts = [
        i
        for i, line in enumerate(lines)
        if re.fullmatch(r"\s*\[compat\.sdeck\.webview\]\s*(?:#.*)?\n?", line)
    ]
    values = {"renderer_sandbox": mode == "sandboxed", "software_rendering": mode == "compatible"}
    if not starts:
        if parsed.get("compat", {}).get("sdeck", {}).get("webview") is not None:
            raise RuntimeError("Unsupported WebEngine config layout; preserving it")
        suffix = "\n[compat.sdeck.webview]\n" + "".join(
            f"{key} = {str(value).lower()}\n" for key, value in values.items()
        )
        result = original.rstrip(b"\n") + b"\n" + suffix.encode()
    else:
        if len(starts) != 1:
            raise RuntimeError("Ambiguous WebEngine config layout; preserving it")
        start = starts[0] + 1
        end = next(
            (i for i in range(start, len(lines)) if lines[i].lstrip().startswith("[")), len(lines)
        )
        block = lines[start:end]
        if lines[start - 1] and not lines[start - 1].endswith("\n"):
            lines[start - 1] += "\n"
        for key, value in values.items():
            matches = [i for i, line in enumerate(block) if re.match(rf"\s*{key}\s*=", line)]
            replacement = f"{key} = {str(value).lower()}\n"
            if len(matches) > 1:
                raise RuntimeError("Ambiguous WebEngine config layout; preserving it")
            if matches:
                block[matches[0]] = replacement
            else:
                if block and not block[-1].endswith("\n"):
                    block[-1] += "\n"
                block.append(replacement)
        result = "".join(lines[:start] + block + lines[end:]).encode()
    try:
        updated = tomllib.loads(result.decode())
        expected = copy.deepcopy(parsed)
        expected.setdefault("compat", {}).setdefault("sdeck", {}).setdefault("webview", {}).update(
            values
        )
        if updated != expected:
            raise RuntimeError("Unsupported WebEngine config layout; preserving it")
    except (ValueError, UnicodeError, AttributeError):
        raise RuntimeError("Unsupported WebEngine config layout; preserving it") from None
    return result
