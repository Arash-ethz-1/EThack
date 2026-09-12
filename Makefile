PY := python
PYTEST := pytest -q -m "not network"

.PHONY: help mocks fetch link score portfolio eval app test fmt all clean

help:
	@echo "mocks     generate schema-valid fake data (start here)"
	@echo "fetch     L1 pull + cache all real sources        [Jean]"
	@echo "link      L2 facility -> ticker resolution        [Arash]"
	@echo "score     L3+L4 indicators and scores             [Lauren]"
	@echo "portfolio L5 build the \$$1B book                  [Florian]"
	@echo "eval      L6 validation + METRICS.md              [Harprit]"
	@echo "app       launch the dashboard"
	@echo "test      pytest (network tests skipped)"
	@echo "all       full pipeline"

mocks:
	$(PY) scripts/make_mocks.py

fetch:
	$(PY) -m ethack.sources.epa
	$(PY) -m ethack.sources.sec
	$(PY) -m ethack.sources.ex21
	$(PY) -m ethack.sources.echo
	$(PY) -m ethack.sources.satellite

link:
	$(PY) -m ethack.link

score:
	$(PY) -m ethack.score

portfolio:
	$(PY) -m ethack.portfolio.construct

eval:
	$(PY) -m ethack.eval.validate

app:
	streamlit run app/main.py

test:
	$(PYTEST)

fmt:
	ruff format src app tests scripts
	ruff check --fix src app tests scripts

all: mocks link score portfolio eval
	@echo "pipeline complete"

clean:
	rm -rf data/processed/* data/mock/* .pytest_cache
