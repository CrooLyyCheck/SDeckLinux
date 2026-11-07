#!/usr/bin/env python3
"""Explicit opt-in tests against real Wine or HID. Never reads button reports."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deckbridge.config import default_config, load  # noqa: E402
from deckbridge.diagnostics import hardware  # noqa: E402
from deckbridge.wine import running_instances  # noqa: E402

CALLBACK_DEADLINE_SECONDS = 10.0
LOG_POLL_INTERVAL_SECONDS = 0.1


def inspect_hardware() -> dict:
    devices = hardware()
    if len(devices) != 1:
        raise RuntimeError("Expected exactly one MK.2; refusing ambiguous selection")
    node = devices[0]["node"]
    fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = bytearray(8)
        # Linux asm-generic ioctl ABI: _IOR('H', 0x03, struct hidraw_devinfo).
        # Verified against /usr/include/linux/hidraw.h; no feature/input/output reports.
        fcntl.ioctl(fd, 0x80084803, info, True)
        bus, vendor, product = struct.unpack("IHH", info)
        if (bus, vendor, product) != (3, 0x0FD9, 0x0080):
            raise RuntimeError("Unexpected HID identity")
    finally:
        os.close(fd)
    return {
        "hardware_identity_verified": True,
        "read_write_access": devices[0]["read_write"],
        "input_reports_read": 0,
        "output_reports_written": 0,
        "display_and_physical_buttons": "requires_user_test",
    }


def deep_link(app_log: Path, deadline_seconds: float, poll_interval: float) -> dict:
    cfg = load(default_config())
    if not app_log.resolve(strict=True).is_relative_to(cfg.prefix):
        raise RuntimeError("App log must be inside the configured prefix")
    before = running_instances(cfg)
    if len(before) != 1:
        raise RuntimeError("Expected exactly one running Stream Deck in the configured prefix")
    marker = "deckbridge-smoke-" + uuid.uuid4().hex
    uri = (
        "streamdeck://plugins/message/io.deckbridge.probe/"
        + marker
        + "?streamdeck=hidden&probe=a%26b%2Fc%25%2B%20x#za%C5%BC%C3%B3%C5%82%C4%87"
    )
    if not 0 < poll_interval <= deadline_seconds <= 60:
        raise RuntimeError("Require 0 < poll interval <= deadline <= 60 seconds")
    with app_log.open("r", errors="replace") as stream:
        stream.seek(0, os.SEEK_END)
        subprocess.run(  # noqa: S603 - fixed launcher and synthetic URI, no shell
            ["/usr/bin/xdg-open", uri],
            check=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        identity = app_log.stat().st_ino
        deadline = time.monotonic() + deadline_seconds
        observed = ""
        while True:
            observed += stream.read()
            if marker in observed:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("No application receipt observed before deadline")
            if app_log.stat().st_ino != identity:
                raise RuntimeError("App log rotated during test; result not inferred")
            if len(observed) > 1024 * 1024:
                raise RuntimeError("Unexpected application log volume")
            # Sample receipts only; never resend a callback. The audited
            # workstation has exhausted its per-user inotify instance limit.
            time.sleep(min(poll_interval, remaining))
        receipt = next(line for line in observed.splitlines() if marker in line)
        same = running_instances(cfg) == before
        reserved = "a%26b%2Fc%25%2B x" in receipt
        unicode = "zażółć" in receipt
        if not same or not reserved or not unicode or "openFile" not in receipt:
            raise RuntimeError("Application receipt did not satisfy the test contract")
        return {
            "application_received": True,
            "same_instance": same,
            "reserved_escapes_preserved": reserved,
            "unicode_observed": unicode,
            "plugin_receipt": "untested",
            "oauth_completed": "untested",
            "log_poll_interval_seconds": poll_interval,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "inspect-hardware", help="Read kernel identity only, no button/display access"
    )
    callback = commands.add_parser(
        "deep-link", help="Synthetic passive callback to original application"
    )
    callback.add_argument("--app-log", type=Path, required=True)
    callback.add_argument("--deadline", type=float, default=CALLBACK_DEADLINE_SECONDS)
    callback.add_argument("--poll-interval", type=float, default=LOG_POLL_INTERVAL_SECONDS)
    args = parser.parse_args()
    try:
        result = (
            inspect_hardware()
            if args.command == "inspect-hardware"
            else deep_link(args.app_log, args.deadline, args.poll_interval)
        )
        print(json.dumps(result, indent=2))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Smoke test failed: {error}", file=sys.stderr)
        sys.exit(1)
