# arXiv Submission Handoff

## Purpose

This file records the exact, independently verified source package for the
EXP-003 preprint. It separates what is technically ready from the author and
account decisions that must be supplied before an arXiv submission.

## Submission-ready artifacts

- Paper PDF: `paper/main.pdf`
- LaTeX entry point: `paper/main.tex`
- Source archive: `dist/veloinference-arxiv-source-2026-09-19.zip`
- Archive size: 77,020 bytes
- Archive SHA-256:
  `3fa38209036b96d1bd3b8a9bddc76c1facd2f946d732fee37dcfb57473e1e086`

The PDF and archive are intentionally ignored by Git because they are build
outputs. The committed LaTeX sources, generated paper tables, generated paper
figures, bibliography, analysis code, tests, claim ledger, and machine-readable
summary are the reproducible source of truth.

## Exact archive contents

The archive contains exactly these 15 files and no auxiliary build files:

```text
figures/mechanism_effects.pdf
figures/primary_overview.pdf
macros.tex
main.bbl
main.tex
references.bib
sections/01_introduction.tex
sections/02_background.tex
sections/03_methodology.tex
sections/04_design.tex
sections/05_evaluation.tex
sections/06_discussion.tex
sections/07_conclusion.tex
tables/paired_effects.tex
tables/primary_results.tex
```

`main.bbl` is included so arXiv can build the bibliography even if BibTeX is
not rerun. PNG figure previews, the generated PDF, logs, auxiliary files, and
local experiment traces are excluded from the source archive.

## Independent build verification

The archive inputs were copied to the isolated directory
`tmp/arxiv-source-20260919-final` and built there with:

```powershell
lualatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
lualatex -interaction=nonstopmode -halt-on-error main.tex
lualatex -interaction=nonstopmode -halt-on-error main.tex
```

Verified result on 2026-09-19:

- 12 letter-size pages
- 320,778-byte PDF
- no matched LaTeX or package warnings
- no overfull or underfull box warnings
- no undefined citations or references
- audited text present for 6,912 measured requests, the 1,510 ms primary
  paired effect, the 0.9985 descriptive fit, and the raw-trace availability
  boundary

## Required human decisions before upload

Do not submit until the user provides or confirms all of the following:

1. Public author name. The current manuscript says `Wasiq` only because a
   surname was not supplied; do not invent one.
2. Public contact email and whether it should appear in the PDF.
3. Affiliation wording. The current manuscript says `Independent Researcher`.
4. Primary and optional cross-list category. Plausible categories include
   `cs.DC` for distributed/serving systems and `cs.PF` for performance, but the
   author must choose; do not silently assign a category.
5. arXiv license selection.
6. Final title, abstract, comments, and journal-reference metadata entered in
   the arXiv form.
7. Submission through the author's arXiv account, including any endorsement
   requirement and the final preview check.

## Data-release boundary

The paper truthfully states that raw traces remain local. The source archive is
therefore suitable for manuscript submission but is not a complete public
artifact package. Before claiming public reproducibility, separately create an
archival release containing the allowable raw records, frozen manifests,
analysis instructions, environment details, and checksums, then replace the
paper's availability statement with the permanent DOI or URL.

## Final upload checklist

1. Replace author/contact placeholders only with user-confirmed information.
2. Rebuild `paper/main.pdf` and repeat the log, text, and visual checks.
3. Recreate the source archive and record its new SHA-256 if any source changes.
4. Upload the source ZIP, not the local PDF alone, to arXiv.
5. Inspect arXiv's generated PDF page by page before submission.
6. Confirm title, author order, abstract, categories, license, and comments.
7. Submit, record the arXiv identifier and version, and tag the exact Git commit.
