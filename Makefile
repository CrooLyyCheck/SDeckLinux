PYTHON ?= python3
DEV_PYTHON = .venv/bin/python
NATIVE_CC ?= .local/toolchains/llvm-mingw-20261104-ucrt-ubuntu-22.04-x86_64/bin/x86_64-w64-mingw32-gcc

.PHONY: install setup check format native-probe native-core-audio
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
	"$(NATIVE_CC)" -std=c11 -O2 -Wall -Wextra -Werror -municode -Ideckbridge/compat/windows/core_audio tools/native/core_audio_probe.c deckbridge/compat/windows/core_audio/identity.c -o .local/native/core_audio_probe.exe -lole32 -luuid -ladvapi32

native-core-audio:
	@test -x "$(NATIVE_CC)" || { echo 'Prepare the isolated compiler described in tools/native/README.md'; exit 1; }
	mkdir -p .local/native
	"$(NATIVE_CC)" -std=c11 -O2 -Wall -Wextra -Werror -shared deckbridge/compat/windows/core_audio/identity.c deckbridge/compat/windows/core_audio/client.c deckbridge/compat/windows/core_audio/volume.c deckbridge/compat/windows/core_audio/factory.c deckbridge/compat/windows/core_audio/exports.def -o .local/native/deckbridge-core-audio.dll -lole32 -luuid -ladvapi32 -lws2_32
	"$(NATIVE_CC)" -std=c11 -O2 -Wall -Wextra -Werror -shared tools/native/core_audio_bootstrap.c -o .local/native/core-audio-bootstrap.node
	cp tools/native/core_audio_bootstrap.manifest .local/native/core-audio-bootstrap.manifest
