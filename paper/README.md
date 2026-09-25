# Paper source

This directory contains the LaTeX source for *When Batching Backfires: The
Hidden Cost of Adding a Gateway to Continuous LLM Serving*.

The manuscript reports a controlled single-GPU study of an outer API-gateway
batcher in front of vLLM. Its numerical results are generated from the audited
analysis artifact rather than copied from console output or partial runs.

## Layout

- `main.tex`: preamble, title, abstract, and section assembly
- `macros.tex`: frozen experiment constants and reported results
- `sections/`: manuscript body
- `references.bib`: bibliography
- `figures/`: generated PDF figures and PNG previews
- `tables/`: generated LaTeX tables

## Regenerate evidence

After producing a complete 48-condition raw result tree:

```bash
uv run --group research python -m bench.analyze_final \
  --input results/raw/exp003-primary-final \
  --summary results/summaries/generated/exp003-analysis.json \
  --figure-dir paper/figures \
  --table-dir paper/tables
```

The analysis rejects incomplete matrices and harness-invalid runs, aggregates
at the run level with two-sided 95% Student-t intervals, computes paired effects
by repetition seed, and writes the tables and figures used by the manuscript.

## Build

From this directory, run:

```bash
lualatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
lualatex -interaction=nonstopmode -halt-on-error main.tex
lualatex -interaction=nonstopmode -halt-on-error main.tex
```

The generated PDF and LaTeX auxiliary files are intentionally ignored.
