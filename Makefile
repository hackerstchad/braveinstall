.PHONY: install test lint format clean run dry-run info

PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

$(VENV):
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt

install: $(VENV)
	$(PIP) install -r requirements.txt

test:
	$(PY) -m pytest tests/ -v --cov=braveinstall --cov-report=term-missing

lint:
	$(PY) -m flake8 braveinstall.py
	$(PY) -m mypy braveinstall.py

format:
	$(PY) -m black braveinstall.py

run:
	$(PY) braveinstall.py

dry-run:
	$(PY) braveinstall.py --dry-run --no-launch

info:
	$(PY) braveinstall.py --info

clean:
	rm -rf $(VENV) __pycache__ .pytest_cache *.egg-info
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
