PY ?= python

.PHONY: install test reproduce smoke check-dashes screenshots

install:
	$(PY) -m pip install -e ".[test]"

test:
	$(PY) -m pytest

reproduce:
	$(PY) -m vicinia.cli reproduce --out results

smoke:
	$(PY) -m vicinia.cli reproduce --quick --out results/_smoke

check-dashes:
	$(PY) scripts/check_no_em_dash.py

screenshots:
	$(PY) scripts/screenshot_report.py results/report.html docs/img
