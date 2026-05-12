"""Generate a recruiter-friendly benchmark report."""

from __future__ import annotations

import argparse
from pathlib import Path

from bench.plot_results import build_layman_story, load_summary, render_markdown_table


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a benchmark report from JSON results.")
    parser.add_argument("input", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = load_summary(args.input)
    comparisons = data if isinstance(data, list) else [data]

    print("Benchmark Story")
    print()
    print(build_layman_story(comparisons))
    print()
    print("Benchmark Table")
    print()
    print(render_markdown_table(comparisons))


if __name__ == "__main__":
    main()
