.PHONY: all fetch synth bronze silver gold checks publish bench test lint lineage
PY ?= python3
SYNTH ?= 0
ARCH_STANDARDS ?= ../arch-standards
export DATA_DIR ?= $(HOME)/data/ecog-lakehouse

all: bronze silver gold checks publish

fetch:
	$(PY) pipeline/fetch.py

synth:
	$(PY) pipeline/synth.py

bronze:
	$(PY) pipeline/run.py bronze $(if $(filter 1,$(SYNTH)),--synth,)

silver:
	$(PY) pipeline/run.py silver

gold:
	$(PY) pipeline/run.py gold

checks:
	$(PY) pipeline/checks.py

publish:
	$(PY) pipeline/publish.py

bench:
	for f in faults/*/bench.sh; do bash $$f; done

test:
	$(PY) -m pytest -q

lineage:
	cp $(ARCH_STANDARDS)/ids/generated/lid/duckdb.sql sql/lineage/lid_generated.sql

lint:
	ruff check . && $(PY) scripts/lint_doc.py README.md CLAUDE.md doc/*.md doc/agent/*.md adr/*.md docs/*.md
