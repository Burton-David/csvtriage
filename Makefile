VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help venv install fmt lint type test check clean

help:
	@echo "make venv     - create the virtualenv"
	@echo "make install  - install the package with dev extras"
	@echo "make fmt      - format with black"
	@echo "make lint     - lint with ruff"
	@echo "make type     - type-check with mypy"
	@echo "make test     - run the test suite"
	@echo "make check    - run fmt-check, lint, type, and test (the done gate)"
	@echo "make clean    - remove caches and build artifacts"

venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv
	$(PIP) install -e ".[dev]"

fmt:
	$(VENV)/bin/black src tests

lint:
	$(VENV)/bin/ruff check src tests

type:
	$(VENV)/bin/mypy src

test:
	$(PY) -m pytest

check:
	$(VENV)/bin/black --check src tests
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/mypy src
	$(PY) -m pytest

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__ \
		src/*.egg-info build dist .coverage coverage.xml
