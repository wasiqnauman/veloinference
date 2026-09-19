# ADIP paper

This directory contains the LaTeX source for the arXiv preprint. The manuscript
tests a deliberately narrow systems hypothesis: an outer gateway batcher helps
continuous LLM serving only when its backend-time savings exceed both its queue
delay and the scheduling freedom it removes from vLLM. Numerical claims are
claim-gated and must come from the final analysis artifact, never from a partial
run or console output.

## Source layout

- `main.tex`: document preamble, title, abstract, and section assembly. Compile
  this file only.
- `macros.tex`: experiment constants and the temporary result macros. The four
  result macros must be replaced with audited findings before release.
- `sections/01_introduction.tex`: motivation, hypothesis, research questions,
  contributions, and scope.
- `sections/02_background.tex`: continuous batching, outer batching, and the
  queueing model that motivates the hypothesis.
- `sections/03_methodology.tex`: causal comparisons, frozen matrix, metrics,
  statistical estimands, and validity gates.
- `sections/04_design.tex`: ADIP architecture, fixed/adaptive closure policies,
  instrumentation, and failure semantics.
- `sections/05_evaluation.tex`: question-structured findings populated by the
  generated figures and tables.
- `sections/06_discussion.tex`: interpretation, design implications, threats to
  validity, and reproducibility boundary.
- `sections/07_conclusion.tex`: claim-bounded conclusion.
- `references.bib`: primary systems and model references.
- `figures/`: generated publication figures from `bench.analyze_final`.
- `tables/`: generated LaTeX tables from `bench.analyze_final`.

## Generate final evidence

Run this only after all 48 declared primary conditions are terminal:

```text
uv run --group research python -m bench.analyze_final \
  --input results/raw/exp003-primary-final \
  --summary results/summaries/generated/exp003-analysis.json \
  --figure-dir paper/figures \
  --table-dir paper/tables
```

The command rejects an incomplete matrix, reports harness-invalid exclusions,
aggregates at the run level with two-sided 95% Student-t intervals, computes
paired effects by repetition seed, and generates the paper's evidence files.

## Build

From `paper/`, run the bibliography-aware LuaLaTeX sequence:

```text
lualatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
lualatex -interaction=nonstopmode -halt-on-error main.tex
lualatex -interaction=nonstopmode -halt-on-error main.tex
```

## Release gate

Before calling the manuscript submission-ready:

1. Replace every temporary result macro in `macros.tex` from the audited JSON.
2. Confirm `rg -n "TODO|placeholder|pending" paper` finds no unresolved claim.
3. Confirm the LaTeX log has no undefined references or layout warnings.
4. Render every PDF page to an image and inspect figures, tables, equations,
   citations, clipping, and font size.
5. Record every included run, excluded run, figure, table, and claim in
   `docs/RESULT_CLAIMS.md`.
