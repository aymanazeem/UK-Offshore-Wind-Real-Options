# Offshore-wind real-options model, common tasks.
# Uses the project venv; create it with `make install` if it does not exist.

PY := ./venv/bin/python
PIP := ./venv/bin/pip
# path count; override e.g. `make charts N=10000`
N ?= 50000

.PHONY: help install test charts charts-final price generation npv sensitivity defer expand abandon clean

help:
	@echo "Targets:"
	@echo "  install       install pinned deps into ./venv"
	@echo "  test          run the pytest suite"
	@echo "  charts        regenerate all charts (N=$(N) paths; override with N=...)"
	@echo "  charts-final  regenerate all charts at production quality (N_PATHS_FINAL)"
	@echo "  price generation npv sensitivity defer expand abandon   single modules"
	@echo "  clean         remove __pycache__"

install:
	$(PIP) install -r requirements.txt

test:
	$(PY) -m pytest -q

charts:
	$(PY) -m src.visualisation --n=$(N)

charts-final:
	$(PY) -m src.visualisation --final

price:
	$(PY) -m src.price_simulator --n=$(N)

generation:
	$(PY) -m src.generation_model --n=$(N)

npv:
	$(PY) -m src.financial_model --n=$(N)

sensitivity:
	$(PY) -m src.sensitivity --n=$(N)

defer:
	$(PY) -m src.lsm_engine --option=defer --n=$(N)

expand:
	$(PY) -m src.lsm_engine --option=expand --n=$(N)

abandon:
	$(PY) -m src.lsm_engine --option=abandon --n=$(N)

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
