# --- Minimal Makefile ---

PY      ?= python3
VENV    ?= .venv
ACT     = . $(VENV)/bin/activate;

# create venv + install deps (app + dev linters/formatters)
setup:
	$(PY) -m venv $(VENV)
	$(ACT) pip install -U pip
	$(ACT) pip install -r requirements.txt
	$(ACT) pip install ruff black isort

# run the app
run:
	$(ACT) $(PY) -m promotion_tycoon.main

# lint only (report issues)
lint:
	$(ACT) ruff check .

# auto-fix + format
format:
	$(ACT) ruff check --fix .
	$(ACT) isort .
	$(ACT) black .

# remove caches & build junk
clean:
	rm -rf __pycache__ */__pycache__ .pytest_cache .ruff_cache .mypy_cache .coverage .gradio outputs
