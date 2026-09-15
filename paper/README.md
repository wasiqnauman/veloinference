# ADIP paper

This directory contains the LaTeX source for the arXiv preprint. The paper is
deliberately claim-gated: numerical results must be copied from verified
generated summaries after the final and sensitivity experiments finish. Do
not replace `TODO` markers with estimates or values read from an incomplete
run.

## Files

- `main.tex`: the complete paper source and the only file that should be
  compiled for the manuscript.
- `references.bib`: bibliography entries used by `main.tex`.
- `figures/`: committed final figures exported by the analysis step.
- `tables/`: committed LaTeX tables exported by the analysis step.

## Build

From this directory, run the bibliography-aware LuaLaTeX sequence:

```text
lualatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
lualatex -interaction=nonstopmode -halt-on-error main.tex
lualatex -interaction=nonstopmode -halt-on-error main.tex
```

The final release step must inspect the resulting PDF and confirm that no
`TODO`, placeholder number, missing reference, or missing figure remains.
