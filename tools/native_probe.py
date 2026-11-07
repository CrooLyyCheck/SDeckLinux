#!/usr/bin/env python3
"""Harmless native application fixture: an exclusive private execution receipt."""

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    exe = Path("/proc/self/exe").resolve()
    with exe.open("rb") as binary:
        elf = binary.read(4) == b"\x7fELF"
    result = {"native_executable": str(exe), "uid": os.getuid(), "linux_elf": elf}
    fd = os.open(args.receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
