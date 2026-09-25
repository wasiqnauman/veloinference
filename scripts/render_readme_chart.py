"""Render the README's paired p95 chart from the committed analysis JSON."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/summaries/generated/exp003-analysis.json"
OUTPUT = ROOT / "docs/figures/readme/paired-p95.svg"

analysis = json.loads(SOURCE.read_text(encoding="utf-8"))
effects = [
    effect
    for effect in analysis["paired_effects"]
    if effect["treatment"] == "fixed" and effect["baseline"] == "pass_through"
]
assert len(effects) == 4

left, right = 350, 1080
minimum, maximum = -1000, 2500


def x(value: float) -> float:
    return left + (value - minimum) * (right - left) / (maximum - minimum)


parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 510" role="img" aria-labelledby="title desc">',
    '<title id="title">Paired p95 latency effect of fixed gateway batching</title>',
    '<desc id="desc">Fixed batching minus gateway pass-through at four offered loads. The 95 percent intervals cross zero at 0.5 requests per second and are above zero at 1.0, 1.5, and 1.8 requests per second. Means are approximately minus 123, plus 1510, plus 1047, and plus 1370 milliseconds.</desc>',
    '<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#101a31"/><stop offset="1" stop-color="#172746"/></linearGradient></defs>',
    '<rect width="1200" height="510" rx="22" fill="url(#bg)"/>',
    '<text x="40" y="47" style="font:700 12px Arial,sans-serif;letter-spacing:2px;fill:#93aaca">PAIRED EXPERIMENT RESULT</text>',
    '<text x="40" y="81" style="font:700 25px Arial,sans-serif;fill:#f5f8ff">Fixed batching raised p95 at 1.0–1.8 req/s</text>',
    '<text x="40" y="110" style="font:15px Arial,sans-serif;fill:#bdcbe0">p95 latency difference vs gateway pass-through · positive means slower</text>',
    f'<rect x="{x(0):.1f}" y="150" width="{right-x(0):.1f}" height="280" fill="#523c3e" opacity=".40"/>',
    f'<line x1="{x(0):.1f}" y1="150" x2="{x(0):.1f}" y2="430" stroke="#9aabc1" stroke-width="2"/>',
    '<text x="40" y="157" style="font:700 13px Arial,sans-serif;fill:#93aaca">OFFERED LOAD</text>',
    '<text x="815" y="157" style="font:700 13px Arial,sans-serif;fill:#f1b18f">FIXED IS SLOWER →</text>',
]

for i, effect in enumerate(effects):
    y = 200 + i * 65
    rate = effect["rate_rps"]
    result = effect["p95_latency_ms_absolute"]
    mean, lower, upper = (result[key] for key in ("mean", "lower", "upper"))
    significant = lower > 0
    color = "#ffad81" if significant else "#8fc2f1"
    parts.extend(
        [
            f'<line x1="40" y1="{y+34}" x2="1158" y2="{y+34}" stroke="#39506d" stroke-width="1"/>',
            f'<text x="45" y="{y+6}" style="font:700 20px Arial,sans-serif;fill:#f5f8ff">{rate:.1f} req/s</text>',
            f'<line x1="{x(lower):.1f}" y1="{y}" x2="{x(upper):.1f}" y2="{y}" stroke="{color}" stroke-width="5" stroke-linecap="round"/>',
            f'<line x1="{x(lower):.1f}" y1="{y-9}" x2="{x(lower):.1f}" y2="{y+9}" stroke="{color}" stroke-width="3"/>',
            f'<line x1="{x(upper):.1f}" y1="{y-9}" x2="{x(upper):.1f}" y2="{y+9}" stroke="{color}" stroke-width="3"/>',
            f'<circle cx="{x(mean):.1f}" cy="{y}" r="9" fill="{color}" stroke="#172746" stroke-width="3"/>',
            f'<text x="1100" y="{y+6}" style="font:700 19px Arial,sans-serif;fill:{color}">{mean/1000:+.2f} s</text>',
        ]
    )

for tick in (-1000, 0, 1000, 2000):
    parts.append(
        f'<text x="{x(tick):.1f}" y="458" text-anchor="middle" style="font:13px Arial,sans-serif;fill:#a8bad2">{tick/1000:+.0f} s</text>'
    )
parts.extend(
    [
        '<text x="40" y="488" style="font:14px Arial,sans-serif;fill:#bdcbe0">● mean of 3 paired runs     ━  two-sided 95% Student-t interval</text>',
        '</svg>',
    ]
)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
print(OUTPUT.relative_to(ROOT))
