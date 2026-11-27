# Offshore-wind real-options model, common tasks.
# Uses the project venv; create it with `make install` if it does not exist.

# interpreter used to create the venv
PYTHON ?= python3
PY := ./venv/bin/python
PIP := ./venv/bin/pip
# path count; override e.g. `make charts N=10000`
N ?= 50000

.PHONY: help install data test charts charts-final price generation npv lcoe sensitivity defer expand abandon clean

help:
	@echo "Targets:"
	@echo "  install       create ./venv if missing and install the pinned deps (PYTHON=... picks Python 3.12-3.14)"
	@echo "  data          download the Elexon price history and rebuild data/processed/gb_price_daily.csv"
	@echo "  test          run the pytest suite"
	@echo "  charts        regenerate all charts (N=$(N) paths; override with N=...)"
	@echo "  charts-final  regenerate all charts at production quality (N_PATHS_FINAL)"
	@echo "  price generation npv lcoe sensitivity defer expand abandon   single modules"
	@echo "  clean         remove __pycache__"

install: $(PIP)
	$(PIP) install -r requirements.txt

# the pinned packages publish installers for Python 3.12 to 3.14 only
$(PIP):
	@$(PYTHON) -c 'import sys; v = sys.version_info[:2]; sys.exit("Python 3.12 to 3.14 is needed, found %s. Try: make install PYTHON=python3.13" % sys.version.split()[0]) if not (3, 12) <= v <= (3, 14) else None'
	$(PYTHON) -m venv venv

data:
	$(PY) -m src.download_prices
	$(PY) -m src.data_prep

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

lcoe:
	$(PY) -m src.lcoe

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
