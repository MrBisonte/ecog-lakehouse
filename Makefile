.PHONY: all fetch synth bronze silver gold checks publish bench test lint lineage sbom
PY ?= python3
SYNTH ?= 0
ARCH_STANDARDS ?= ../arch-standards
export DATA_DIR ?= $(HOME)/data/ecog-lakehouse

all: bronze silver gold checks publish

fetch:
	$(PY) -m pipeline.fetch

synth:
	$(PY) -m pipeline.synth

bronze:
	$(PY) -m pipeline.run bronze $(if $(filter 1,$(SYNTH)),--synth,)

silver:
	$(PY) -m pipeline.run silver

gold:
	$(PY) -m pipeline.run gold

checks:
	$(PY) -m pipeline.checks

publish:
	$(PY) -m pipeline.publish

bench:
	$(PY) pipeline/bench_doc.py
	for f in $(wildcard faults/*/bench.sh); do bash $$f; done

test:
	$(PY) -m pytest -q

lineage:
	cp $(ARCH_STANDARDS)/data/ids/generated/lid/duckdb.sql sql/lineage/lid_generated.sql

lint:
	ruff check . && $(PY) scripts/lint_doc.py README.md CLAUDE.md CONTRIBUTING.md doc/*.md adr/*.md docs/*.md

# CycloneDX 1.6 bill of materials of the installed environment, the project as root component.
sbom:
	cyclonedx-py environment --pyproject pyproject.toml --mc-type application --sv 1.6 --of JSON --output-reproducible -o sbom.cdx.json
