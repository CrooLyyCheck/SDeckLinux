PYTHON ?= python3
DEV_PYTHON = .venv/bin/python
NATIVE_CC ?= .local/toolchains/llvm-mingw-20261104-ucrt-ubuntu-22.04-x86_64/bin/x86_64-w64-mingw32-gcc

.PHONY: install setup check format native-probe
install:
	$(PYTHON) tools/setup.py

setup:
	$(PYTHON) -m venv .venv
	$(DEV_PYTHON) -m pip install --require-hashes --only-binary=:all: -r requirements-dev.txt
	$(DEV_PYTHON) tools/prepare_runtime.py

check:
	$(DEV_PYTHON) -m ruff format --check deckbridge tests tools
	$(DEV_PYTHON) -m ruff check deckbridge tests tools
	$(PYTHON) -m compileall -q deckbridge tests tools
	$(DEV_PYTHON) -m unittest discover -s tests -v

format:
	$(DEV_PYTHON) -m ruff format deckbridge tests tools

native-probe:
	@test -x "$(NATIVE_CC)" || { echo 'Prepare the isolated compiler described in tools/native/README.md'; exit 1; }
	mkdir -p .local/native
	"$(NATIVE_CC)" -std=c11 -O2 -Wall -Wextra -Werror -municode tools/native/core_audio_probe.c -o .local/native/core_audio_probe.exe -lole32 -luuid
