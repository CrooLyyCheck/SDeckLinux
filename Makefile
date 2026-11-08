PYTHON ?= python3
DEV_PYTHON = .venv/bin/python

.PHONY: install setup check format
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
