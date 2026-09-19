"""Auditable run-level analysis for the EXP-003 primary matrix."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, stdev

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

MODES = ("direct", "pass_through", "fixed", "adaptive")
RATES = (0.5, 1.0, 1.5, 1.8)
REPETITIONS = (1, 2, 3)
RUN_PATTERN = re.compile(
    r"^(direct|pass_through|fixed|adaptive)-rate-(\d+)p(\d+)-rep-(\d+)$"
)
T_CRITICAL_95 = {1: 12.7062047364, 2: 4.3026527299}
COLORS = {
    "direct": "#0072B2",
    "pass_through": "#009E73",
    "fixed": "#D55E00",
    "adaptive": "#CC79A7",
}
LABELS = {
    "direct": "Direct vLLM",
    "pass_through": "Gateway pass-through",
    "fixed": "Fixed 1 ms",
    "adaptive": "Adaptive (20 ms cap)",
}
METRICS = (
    "achieved_request_throughput",
    "p50_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
    "mean_queue_ms",
    "mean_backend_ms",
    "mean_batch_size",
    "mean_gpu_utilization_percent",
    "max_vram_used_mb",
    "mean_power_draw_w",
    "p95_arrival_drift_ms",
)


@dataclass(frozen=True, slots=True)
class RunResult:
    """One completed run and its publication-facing summary."""

    run_id: str
    mode: str
    rate: float
    repetition: int
    summary: dict[str, object]


def parse_run_id(run_id: str) -> tuple[str, float, int]:
    """Parse one stable EXP-003 run identifier."""
    match = RUN_PATTERN.fullmatch(run_id)
    if match is None:
        raise ValueError(f"Unrecognized final run ID: {run_id}")
    mode, whole, fraction, repetition = match.groups()
    return mode, float(f"{whole}.{fraction}"), int(repetition)


def mean_ci95(values: list[float]) -> dict[str, float | int | None]:
    """Return a two-sided 95% Student-t interval over run-level values."""
    if not values:
        return {"n": 0, "mean": None, "lower": None, "upper": None, "half_width": None}
    mean = fmean(values)
    if len(values) == 1:
        return {
            "n": 1,
            "mean": mean,
            "lower": None,
            "upper": None,
            "half_width": None,
        }
    critical = T_CRITICAL_95.get(len(values) - 1, 1.96)
    half_width = critical * stdev(values) / math.sqrt(len(values))
    return {
        "n": len(values),
        "mean": mean,
        "lower": mean - half_width,
        "upper": mean + half_width,
        "half_width": half_width,
    }


def load_terminal_matrix(root: Path) -> tuple[list[RunResult], list[dict[str, object]]]:
    """Load the complete terminal matrix without modifying raw artifacts."""
    expected = {
        (mode, rate, repetition)
        for mode in MODES
        for repetition in REPETITIONS
        for rate in RATES
    }
    observed: set[tuple[str, float, int]] = set()
    completed: list[RunResult] = []
    excluded: list[dict[str, object]] = []

    for manifest_path in sorted(root.glob("**/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run_id = str(manifest["run_id"])
        mode, rate, repetition = parse_run_id(run_id)
        key = (mode, rate, repetition)
        if key in observed:
            raise ValueError(f"Duplicate final condition: {run_id}")
        observed.add(key)
        status = manifest.get("status")
        if status == "complete":
            summary_path = manifest_path.parent / "summary.json"
            if not summary_path.is_file():
                raise ValueError(f"Complete run has no summary: {run_id}")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if summary.get("run_id") != run_id:
                raise ValueError(f"Summary run ID mismatch: {run_id}")
            completed.append(RunResult(run_id, mode, rate, repetition, summary))
        elif status == "invalid_harness":
            excluded.append(
                {
                    "run_id": run_id,
                    "mode": mode,
                    "rate": rate,
                    "repetition": repetition,
                    "status": status,
                    "reason": manifest.get("invalid_reason") or manifest.get("reason"),
                }
            )
        else:
            raise ValueError(f"Nonterminal final condition {run_id}: {status}")

    missing = expected - observed
    extra = observed - expected
    if missing or extra:
        raise ValueError(
            f"Final matrix mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return completed, excluded


def aggregate_runs(runs: list[RunResult]) -> list[dict[str, object]]:
    """Aggregate metrics across run-level repetitions for each condition."""
    grouped: dict[tuple[str, float], list[RunResult]] = defaultdict(list)
    for run in runs:
        grouped[(run.mode, run.rate)].append(run)

    aggregates: list[dict[str, object]] = []
    for mode in MODES:
        for rate in RATES:
            group = sorted(grouped[(mode, rate)], key=lambda item: item.repetition)
            row: dict[str, object] = {
                "mode": mode,
                "rate_rps": rate,
                "run_ids": [run.run_id for run in group],
                "repetitions": [run.repetition for run in group],
            }
            for metric in METRICS:
                values = [
                    float(run.summary[metric])
                    for run in group
                    if run.summary.get(metric) is not None
                ]
                row[metric] = mean_ci95(values)
            aggregates.append(row)
    return aggregates


def paired_effects(runs: list[RunResult]) -> list[dict[str, object]]:
    """Compute paired run-level policy effects using the shared repetition seed."""
    by_key = {(run.mode, run.rate, run.repetition): run for run in runs}
    comparisons = (
        ("pass_through", "direct", "Proxy minus direct"),
        ("fixed", "pass_through", "Fixed minus pass-through"),
        ("adaptive", "fixed", "Adaptive minus fixed"),
    )
    effects: list[dict[str, object]] = []
    for treatment, baseline, label in comparisons:
        for rate in RATES:
            row: dict[str, object] = {
                "comparison": label,
                "treatment": treatment,
                "baseline": baseline,
                "rate_rps": rate,
            }
            for metric in (
                "p95_latency_ms",
                "achieved_request_throughput",
                "mean_gpu_utilization_percent",
                "mean_batch_size",
            ):
                absolute: list[float] = []
                relative: list[float] = []
                for repetition in REPETITIONS:
                    treatment_run = by_key.get((treatment, rate, repetition))
                    baseline_run = by_key.get((baseline, rate, repetition))
                    if treatment_run is None or baseline_run is None:
                        continue
                    treatment_value = treatment_run.summary.get(metric)
                    baseline_value = baseline_run.summary.get(metric)
                    if treatment_value is None or baseline_value is None:
                        continue
                    treatment_number = float(treatment_value)
                    baseline_number = float(baseline_value)
                    absolute.append(treatment_number - baseline_number)
                    if baseline_number != 0:
                        relative.append(100.0 * (treatment_number - baseline_number) / baseline_number)
                row[f"{metric}_absolute"] = mean_ci95(absolute)
                row[f"{metric}_relative_percent"] = mean_ci95(relative)
            effects.append(row)
    return effects


def write_analysis_json(
    output_path: Path,
    runs: list[RunResult],
    excluded: list[dict[str, object]],
    aggregates: list[dict[str, object]],
    effects: list[dict[str, object]],
) -> None:
    """Write the machine-readable analysis artifact."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "analysis_unit": "run",
        "confidence_interval": "two-sided 95% Student-t over run-level values",
        "completed_run_count": len(runs),
        "excluded_run_count": len(excluded),
        "excluded": excluded,
        "aggregates": aggregates,
        "paired_effects": effects,
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def plot_overview(
    runs: list[RunResult],
    aggregates: list[dict[str, object]],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Plot throughput, latency, batching, and GPU utilization."""
    output_dir.mkdir(parents=True, exist_ok=True)
    by_condition = {(row["mode"], row["rate_rps"]): row for row in aggregates}
    figure, axes = plt.subplots(2, 2, figsize=(9.2, 6.4), constrained_layout=True)
    panels = (
        (axes[0, 0], "achieved_request_throughput", "Achieved throughput", "requests/s"),
        (axes[0, 1], "p95_latency_ms", "Tail latency", "p95 latency (ms)"),
        (
            axes[1, 0],
            "mean_batch_size",
            "Outer request grouping",
            "prompts per backend HTTP call",
        ),
        (axes[1, 1], "mean_gpu_utilization_percent", "GPU utilization", "mean utilization (%)"),
    )
    offsets = {mode: offset for mode, offset in zip(MODES, (-0.035, -0.012, 0.012, 0.035), strict=True)}
    for axis, metric, title, ylabel in panels:
        for mode in MODES:
            means: list[float] = []
            errors: list[float] = []
            for rate in RATES:
                stats = by_condition[(mode, rate)][metric]
                mean = stats["mean"]
                means.append(float("nan") if mean is None else float(mean))
                half_width = stats["half_width"]
                errors.append(0.0 if half_width is None else float(half_width))
                points = [
                    float(run.summary[metric])
                    for run in runs
                    if run.mode == mode
                    and run.rate == rate
                    and run.summary.get(metric) is not None
                ]
                axis.scatter(
                    [rate + offsets[mode]] * len(points),
                    points,
                    color=COLORS[mode],
                    alpha=0.35,
                    s=18,
                    zorder=2,
                )
            axis.errorbar(
                RATES,
                means,
                yerr=errors,
                color=COLORS[mode],
                marker="o",
                linewidth=1.7,
                capsize=3,
                label=LABELS[mode],
                zorder=3,
            )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_xlabel("Offered load (requests/s)")
        axis.set_ylabel(ylabel)
        axis.set_xticks(RATES)
        axis.grid(alpha=0.22, linewidth=0.6)
    axes[0, 0].plot(RATES, RATES, linestyle="--", color="#666666", linewidth=1, label="ideal")
    handles, labels = axes[0, 1].get_legend_handles_labels()
    figure.legend(handles, labels, loc="outside lower center", ncol=4, frameon=False)
    return _save_figure(figure, output_dir, "primary_overview")


def plot_mechanism(
    aggregates: list[dict[str, object]],
    effects: list[dict[str, object]],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Plot queue/backend decomposition and paired p95 effects."""
    output_dir.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(9.2, 3.7), constrained_layout=True)
    gateway_modes = ("pass_through", "fixed", "adaptive")
    width = 0.085
    for mode_index, mode in enumerate(gateway_modes):
        rows = [row for row in aggregates if row["mode"] == mode]
        x = [rate + (mode_index - 1) * width for rate in RATES]
        queue = [float(row["mean_queue_ms"]["mean"] or 0.0) for row in rows]
        backend = [float(row["mean_backend_ms"]["mean"] or 0.0) for row in rows]
        axes[0].bar(x, backend, width=width, color=COLORS[mode], alpha=0.82, label=LABELS[mode])
        axes[0].bar(x, queue, width=width, bottom=backend, color=COLORS[mode], alpha=0.35, hatch="//")
    axes[0].set_title("A  Queue and backend time", loc="left", fontweight="bold")
    axes[0].set_xlabel("Offered load (requests/s)")
    axes[0].set_ylabel("Mean time per request (ms)")
    axes[0].set_xticks(RATES)
    axes[0].grid(axis="y", alpha=0.22, linewidth=0.6)
    axes[0].legend(frameon=False, fontsize=8)

    comparison_styles = {
        "Proxy minus direct": ("#009E73", "o"),
        "Fixed minus pass-through": ("#D55E00", "s"),
        "Adaptive minus fixed": ("#CC79A7", "^"),
    }
    for comparison, (color, marker) in comparison_styles.items():
        rows = [row for row in effects if row["comparison"] == comparison]
        means = [float(row["p95_latency_ms_absolute"]["mean"] or 0.0) for row in rows]
        errors = [float(row["p95_latency_ms_absolute"]["half_width"] or 0.0) for row in rows]
        axes[1].errorbar(
            RATES,
            means,
            yerr=errors,
            color=color,
            marker=marker,
            linewidth=1.7,
            capsize=3,
            label=comparison,
        )
    axes[1].axhline(0.0, color="#333333", linewidth=0.8)
    axes[1].set_title("B  Paired tail-latency effect", loc="left", fontweight="bold")
    axes[1].set_xlabel("Offered load (requests/s)")
    axes[1].set_ylabel("Mean paired p95 delta (ms)")
    axes[1].set_xticks(RATES)
    axes[1].grid(alpha=0.22, linewidth=0.6)
    axes[1].legend(frameon=False, fontsize=8)
    return _save_figure(figure, output_dir, "mechanism_effects")


def write_primary_table(aggregates: list[dict[str, object]], output_path: Path) -> None:
    """Write a compact LaTeX table with all primary conditions."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "% Generated by python -m bench.analyze_final; do not edit by hand.",
        "\\begin{tabular}{llrrrr}",
        "\\toprule",
        "Mode & Rate & Throughput & p95 latency & Outer group & GPU util. \\\\",
        " & (req/s) & (req/s) & (ms) & (requests) & (\\%) \\\\",
        "\\midrule",
    ]
    for row in aggregates:
        lines.append(
            "{} & {:.1f} & {} & {} & {} & {} \\\\".format(
                LABELS[str(row["mode"])],
                float(row["rate_rps"]),
                _latex_stat(row["achieved_request_throughput"], 2),
                _latex_stat(row["p95_latency_ms"], 0),
                _latex_stat(row["mean_batch_size"], 2),
                _latex_stat(row["mean_gpu_utilization_percent"], 1),
            )
        )
        if float(row["rate_rps"]) == RATES[-1] and row["mode"] != MODES[-1]:
            lines.append("\\addlinespace")
    lines.extend(["\\bottomrule", "\\end{tabular}"])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_effect_table(effects: list[dict[str, object]], output_path: Path) -> None:
    """Write paired p95 latency effects and relative changes as LaTeX."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "% Generated by python -m bench.analyze_final; do not edit by hand.",
        "\\begin{tabular}{lrrr}",
        "\\toprule",
        "Comparison & Rate & p95 delta (ms) & Relative delta (\\%) \\\\",
        "\\midrule",
    ]
    for row in effects:
        lines.append(
            "{} & {:.1f} & {} & {} \\\\".format(
                str(row["comparison"]),
                float(row["rate_rps"]),
                _latex_stat(row["p95_latency_ms_absolute"], 0),
                _latex_stat(row["p95_latency_ms_relative_percent"], 1),
            )
        )
    lines.extend(["\\bottomrule", "\\end{tabular}"])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _latex_stat(stats: object, decimals: int) -> str:
    mapping = dict(stats)  # type: ignore[arg-type]
    mean = mapping["mean"]
    half_width = mapping["half_width"]
    if mean is None:
        return "--"
    if half_width is None:
        return f"{float(mean):.{decimals}f}"
    return f"{float(mean):.{decimals}f} $\\pm$ {float(half_width):.{decimals}f}"


def _save_figure(figure: plt.Figure, output_dir: Path, stem: str) -> tuple[Path, Path]:
    metadata = {"Creator": "ADIP analysis", "Title": stem, "CreationDate": None, "ModDate": None}
    pdf_path = output_dir / f"{stem}.pdf"
    png_path = output_dir / f"{stem}.png"
    figure.savefig(pdf_path, metadata=metadata, bbox_inches="tight")
    figure.savefig(png_path, dpi=220, metadata={"Software": "ADIP analysis"}, bbox_inches="tight")
    plt.close(figure)
    return pdf_path, png_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="EXP-003 raw result root")
    parser.add_argument("--summary", type=Path, required=True, help="analysis JSON output")
    parser.add_argument("--figure-dir", type=Path, required=True, help="publication figure directory")
    parser.add_argument("--table-dir", type=Path, required=True, help="publication table directory")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    runs, excluded = load_terminal_matrix(args.input)
    aggregates = aggregate_runs(runs)
    effects = paired_effects(runs)
    write_analysis_json(args.summary, runs, excluded, aggregates, effects)
    plot_overview(runs, aggregates, args.figure_dir)
    plot_mechanism(aggregates, effects, args.figure_dir)
    write_primary_table(aggregates, args.table_dir / "primary_results.tex")
    write_effect_table(effects, args.table_dir / "paired_effects.tex")
    print(
        json.dumps(
            {
                "completed": len(runs),
                "excluded": len(excluded),
                "summary": str(args.summary),
                "figure_dir": str(args.figure_dir),
                "table_dir": str(args.table_dir),
            }
        )
    )


if __name__ == "__main__":
    main()
