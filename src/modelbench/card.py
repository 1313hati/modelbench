"""A shareable scorecard: one SVG you can post, print or attach to a PR.

Reports are for reading; a card is for the one image that travels without its
footnotes. It therefore carries the parts that keep a score honest — the
confidence interval, how many samples it rests on, the suite digest — instead
of only the flattering number.

The output is a single 1200×675 SVG with no external assets. ``write_card`` can
also rasterise it with ``rsvg-convert`` when that is installed, because most
social timelines are happier with a PNG than with an SVG.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from . import __version__
from .report import Run, _usd, ci_pct, per_category_metrics, run_metrics, sampling

W, H = 1200, 675
BG = "#070b10"
FG = "#e6edf4"
MUTED = "#8b9aab"
LINE = "#1e2a36"
CYAN = "#22d3ee"
INDIGO = "#6366f1"
GREEN = "#34d399"
AMBER = "#fbbf24"
RED = "#f87171"

SANS = "ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace"


def _esc(value: object) -> str:
    return escape("" if value is None else str(value), {"'": "&apos;", '"': "&quot;"})


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _wall(seconds: float | None) -> str:
    """Seconds for a quick suite, minutes once the number stops being readable."""
    if not seconds:
        return "—"
    return f"{seconds:.0f} s" if seconds < 90 else f"{seconds / 60:.0f} min"


def _color(score: float) -> str:
    if score >= 0.999:
        return GREEN
    if score >= 0.85:
        return "#a3e635"
    if score >= 0.6:
        return AMBER
    if score > 0:
        return "#fb923c"
    return RED


def _bar(x: float, y: float, width: float, height: float, score: float, color: str) -> str:
    """A track plus a filled portion, rounded on both ends."""
    filled = max(2.0, min(1.0, max(0.0, score)) * width)
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
        f'rx="{height / 2:.1f}" fill="#16212c"/>'
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{filled:.1f}" height="{height:.1f}" '
        f'rx="{height / 2:.1f}" fill="{color}"/>'
    )


def render_card(
    run: Run,
    title: str | None = None,
    subtitle: str | None = None,
    footer: str | None = None,
) -> str:
    """Render one run as an SVG scorecard."""
    m = run_metrics(run)
    label = _clip(title or run.label, 34)
    served = ""
    target = run.header.get("target") or {}
    if target.get("model") and target.get("model") != label:
        served = _clip(str(target["model"]), 40)
    sub_bits = [subtitle] if subtitle else []
    if served:
        sub_bits.append(f"served as {served}")
    sub_bits.append(f"{m['tasks']} tasks · {m['samples']} sample{'s' if m['samples'] != 1 else ''} each")
    sub = " · ".join(sub_bits)

    score = m["first_score"]
    ci_text = ci_pct(m["first_ci"]) if m["first_ci"] else "single sample — no interval"
    final_line = (
        f"final {m['final_score'] * 100:.1f}% after one feedback turn · "
        f"{m['solved_final'] * 100:.1f}% fully solved"
    )
    if m["repairs"] == 0:
        final_line = "no feedback was needed · every first answer graded"
    stats: list[tuple[str, str]] = [
        ("SOLVED FIRST", f"{m['solved_first'] * 100:.0f}%"),
        ("DECODE", f"{m['median_tps']:.0f} tok/s" if m["median_tps"] else "—"),
        ("OUTPUT", f"{m['total_tokens'] / 1000:.1f}k tok"),
        ("WALL", _wall(m["wall_s"])),
    ]
    # A locally hosted model is priced at zero; printing "$0" twice reads as a
    # measurement when it is really "not applicable".
    if m["cost_usd"]:
        stats.append(("COST", _usd(m["cost_usd"])))
        if m["cost_per_solved_usd"]:
            stats.append(("PER SOLVED", _usd(m["cost_per_solved_usd"])))

    # Right panel: categories, worst first so the card shows where it breaks.
    cats = per_category_metrics(run)
    ordered = sorted(cats.items(), key=lambda kv: (kv[1]["first"], kv[0]))
    if len(ordered) > 7:
        head = ordered[:6]
        rest = ordered[6:]
        head.append(
            (
                f"+{len(rest)} more",
                {
                    "first": sum(c["first"] for _, c in rest) / len(rest),
                    "final": sum(c["final"] for _, c in rest) / len(rest),
                },
            )
        )
        ordered = head

    bars = []
    top = 196
    step = 42
    for index, (name, entry) in enumerate(ordered):
        y = top + index * step
        value = float(entry["first"])
        bars.append(
            f'<text x="704" y="{y + 4}" font-family="{SANS}" font-size="14" fill="{MUTED}">'
            f"{_esc(_clip(name, 18))}</text>"
            + _bar(704, y + 12, 340, 6, value, _color(value))
            + f'<text x="1114" y="{y + 4}" text-anchor="end" font-family="{MONO}" font-size="14" '
            f'fill="{FG}">{value * 100:.0f}%</text>'
        )

    digest = (run.header.get("suite") or {}).get("digest") or (
        run.records[0].get("suite_digest") if run.records else ""
    )
    seed = sampling(run)["seed"]
    seed_text = f"seed {seed}" if seed is not None else "seed not pinned"
    when = datetime.now().strftime("%d %b %Y")
    footer_text = footer or (
        f"suite {run.suite_id} · digest {str(digest)[:12]} · {seed_text} · "
        f"{m['records']}/{m['expected']} records · {when}"
    )

    # Sparkline of per-task first-attempt scores: the shape a mean hides.
    per_task = sorted(
        (
            (str(r["task"]), float(r["first"]["score"]))
            for r in run.records
            if int(r.get("sample") or 1) == 1
        ),
        key=lambda item: item[1],
    )
    spark = ""
    if len(per_task) > 1:
        x0, y0, width, height = 64, 580, 520, 34
        points = []
        for i, (_, value) in enumerate(per_task):
            x = x0 + width * i / (len(per_task) - 1)
            y = y0 + height * (1 - max(0.0, min(1.0, value)))
            points.append(f"{x:.1f},{y:.1f}")
        spark = (
            f'<text x="{x0}" y="{y0 - 12}" font-family="{SANS}" font-size="11" '
            f'letter-spacing="1.4" fill="{MUTED}">EVERY TASK, WORST TO BEST</text>'
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{CYAN}" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round" opacity=".9"/>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="modelbench scorecard for {_esc(label)}">
<defs>
  <radialGradient id="glow" cx="18%" cy="0%" r="90%">
    <stop offset="0%" stop-color="#123244" stop-opacity=".95"/>
    <stop offset="60%" stop-color="{BG}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="score" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="{CYAN}"/>
    <stop offset="100%" stop-color="{INDIGO}"/>
  </linearGradient>
  <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="{CYAN}" stop-opacity=".8"/>
    <stop offset="55%" stop-color="{INDIGO}" stop-opacity=".35"/>
    <stop offset="100%" stop-color="{INDIGO}" stop-opacity="0"/>
  </linearGradient>
</defs>
<rect width="{W}" height="{H}" fill="{BG}"/>
<rect width="{W}" height="{H}" fill="url(#glow)"/>
<g opacity=".35">
  <path d="M0 560 H1200 M0 560 V675 M1200 560 V675" stroke="{LINE}" stroke-width="1" fill="none"/>
</g>

<text x="64" y="72" font-family="{MONO}" font-size="15" letter-spacing="2.4" fill="{MUTED}">MODELBENCH</text>
<text x="64" y="98" font-family="{SANS}" font-size="12" fill="#51606f">a score you can defend · v{__version__}</text>
<text x="1136" y="72" text-anchor="end" font-family="{MONO}" font-size="13" fill="{MUTED}">{_esc(run.suite_id)}</text>
<text x="1136" y="96" text-anchor="end" font-family="{SANS}" font-size="12" fill="#51606f">single-turn · graded · kept on disk</text>

<text x="64" y="168" font-family="{SANS}" font-size="34" font-weight="600" fill="{FG}" letter-spacing="-.5">{_esc(label)}</text>
<text x="64" y="198" font-family="{SANS}" font-size="14" fill="{MUTED}">{_esc(_clip(sub, 92))}</text>

<text x="60" y="372" font-family="{SANS}" font-size="150" font-weight="700" fill="url(#score)" letter-spacing="-6">{score * 100:.1f}<tspan font-size="58" letter-spacing="0" dx="6">%</tspan></text>
<text x="64" y="410" font-family="{MONO}" font-size="18" fill="{MUTED}">95% CI {_esc(ci_text)}</text>
<text x="64" y="440" font-family="{SANS}" font-size="14" fill="{MUTED}">{_esc(final_line)}</text>

<rect x="64" y="470" width="1072" height="1" fill="url(#rule)"/>

{''.join(f'<text x="{64 + i * 178}" y="500" font-family="{SANS}" font-size="10.5" letter-spacing="1.5" fill="{MUTED}">{name}</text><text x="{64 + i * 178}" y="528" font-family="{MONO}" font-size="22" fill="{FG}">{value}</text>' for i, (name, value) in enumerate(stats))}

{spark}

<text x="704" y="168" font-family="{SANS}" font-size="10.5" letter-spacing="1.5" fill="{MUTED}">BY CATEGORY, WEAKEST FIRST</text>
{''.join(bars)}

<text x="64" y="640" font-family="{MONO}" font-size="10.5" fill="#51606f">{_esc(_clip(footer_text, 118))}</text>
<text x="1136" y="640" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="#51606f">github.com/1313hati/modelbench</text>
</svg>
'''


def write_card(
    run: Run,
    out: str | Path,
    title: str | None = None,
    subtitle: str | None = None,
    footer: str | None = None,
    png: str | Path | None = None,
    width: int = 1600,
) -> dict[str, Path | None]:
    """Write the SVG, and a PNG beside it when ``rsvg-convert`` is available."""
    svg_path = Path(out).expanduser()
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(render_card(run, title=title, subtitle=subtitle, footer=footer), encoding="utf-8")
    png_path: Path | None = None
    if png:
        png_path = Path(png).expanduser()
        png_path.parent.mkdir(parents=True, exist_ok=True)
        binary = shutil.which("rsvg-convert")
        if not binary:
            raise RuntimeError(
                "rsvg-convert not found: install librsvg (or pass an .svg path and convert it yourself)"
            )
        subprocess.run(
            [binary, "--width", str(width), "--format", "png", "--output", str(png_path), str(svg_path)],
            check=True,
            capture_output=True,
        )
    return {"svg": svg_path, "png": png_path}
