PYTHON ?= python3
DEV_PYTHON = .venv/bin/python

.PHONY: setup check format
setup:
	$(PYTHON) -m venv .venv
	$(DEV_PYTHON) -m pip install --require-hashes --only-binary=:all: -r requirements-dev.txt

check:
	$(DEV_PYTHON) -m ruff format --check deckbridge tests tools
	$(DEV_PYTHON) -m ruff check deckbridge tests tools
	$(PYTHON) -m compileall -q deckbridge tests tools
	$(PYTHON) -m unittest discover -s tests -v

format:
	$(DEV_PYTHON) -m ruff format deckbridge tests tools
