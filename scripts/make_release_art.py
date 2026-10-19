#!/usr/bin/env python3
"""Render the release graphic from the package's own suite metadata.

The point of generating the picture instead of drawing it by hand is that the
task and assertion counts cannot drift away from the code they describe. Run:

    python scripts/make_release_art.py --png

writes ``assets/release-<version>.svg`` and, with ``--png``, a 1600×900 PNG.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from modelbench import __version__  # noqa: E402
from modelbench.tasks import available_suites  # noqa: E402

W, H = 1600, 900
BG = "#070b10"
PANEL = "#0c131b"
EDGE = "#1b2833"
FG = "#e6edf4"
MUTED = "#8b9aab"
DIM = "#51606f"
CYAN = "#22d3ee"
INDIGO = "#6366f1"
GREEN = "#34d399"

SANS = "ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace"

TILES = [
    ("± 95%", "Confidence on every score", "bootstrapped over tasks, seeded, reproducible"),
    ("p < 0.05", "A winner needs both tests", "interval excludes zero and the sign test agrees"),
    ("$ / solved", "The bill, not just the score", "retries and feedback turns included"),
    ("1200×675", "A scorecard that travels", "one SVG: interval, categories, every task"),
    ("1=", "Ties stay ties", "overlapping runs share a rank, by design"),
    ("work-v1", "Desk work, not just code", "4 tasks: layout, export, SQL, memo"),
]


def tile(x: int, y: int, figure: str, label: str, desc: str) -> str:
    return f'''<g>
  <rect x="{x}" y="{y}" width="460" height="146" rx="14" fill="{PANEL}" stroke="{EDGE}"/>
  <rect x="{x}" y="{y}" width="3" height="146" rx="1.5" fill="{INDIGO}" opacity=".7"/>
  <text x="{x + 28}" y="{y + 64}" font-family="{MONO}" font-size="38" font-weight="600" fill="{CYAN}">{escape(figure)}</text>
  <text x="{x + 28}" y="{y + 98}" font-family="{SANS}" font-size="18" font-weight="600" fill="{FG}">{escape(label)}</text>
  <text x="{x + 28}" y="{y + 122}" font-family="{SANS}" font-size="14.5" fill="{MUTED}">{escape(desc)}</text>
</g>'''


def render(tasks: int, assertions: int, suites: int) -> str:
    grid = []
    for index, (figure, label, desc) in enumerate(TILES):
        col, row = index % 3, index // 3
        grid.append(tile(78 + col * 482, 392 + row * 178, figure, label, desc))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="modelbench {__version__} release">
<defs>
  <radialGradient id="g1" cx="12%" cy="-10%" r="80%">
    <stop offset="0%" stop-color="#123244" stop-opacity=".95"/>
    <stop offset="70%" stop-color="{BG}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="g2" cx="100%" cy="110%" r="70%">
    <stop offset="0%" stop-color="#221a4d" stop-opacity=".8"/>
    <stop offset="100%" stop-color="{BG}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="text" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#7dd3fc"/>
    <stop offset="55%" stop-color="{CYAN}"/>
    <stop offset="100%" stop-color="{INDIGO}"/>
  </linearGradient>
  <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="{CYAN}" stop-opacity=".85"/>
    <stop offset="60%" stop-color="{INDIGO}" stop-opacity=".35"/>
    <stop offset="100%" stop-color="{INDIGO}" stop-opacity="0"/>
  </linearGradient>
</defs>
<rect width="{W}" height="{H}" fill="{BG}"/>
<rect width="{W}" height="{H}" fill="url(#g1)"/>
<rect width="{W}" height="{H}" fill="url(#g2)"/>

<text x="80" y="82" font-family="{MONO}" font-size="17" letter-spacing="3.2" fill="{MUTED}">MODELBENCH</text>
<text x="1520" y="82" text-anchor="end" font-family="{MONO}" font-size="15" fill="{DIM}">v{__version__} · {suites} suites · {tasks} tasks · {assertions} assertions</text>

<text x="76" y="236" font-family="{SANS}" font-size="92" font-weight="700" letter-spacing="-3.5" fill="url(#text)">A score you can defend.</text>
<text x="80" y="300" font-family="{SANS}" font-size="26" fill="{MUTED}">Most benchmarks print a number. modelbench prints the doubt, the bill and the receipts.</text>
<rect x="80" y="336" width="1440" height="1.5" fill="url(#rule)"/>

{''.join(grid)}

<text x="80" y="812" font-family="{MONO}" font-size="15" fill="{DIM}">{tasks} tasks · {assertions} assertions · {suites} suites · zero runtime dependencies · every answer kept</text>
<text x="1520" y="812" text-anchor="end" font-family="{MONO}" font-size="15" fill="{MUTED}">github.com/1313hati/modelbench</text>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help="SVG path (default assets/release-<version>.svg)")
    parser.add_argument("--png", action="store_true", help="also write a PNG next to the SVG")
    args = parser.parse_args()

    suites = available_suites()
    tasks = sum(len(suite.tasks) for suite in suites)
    assertions = sum(task.checks for suite in suites for task in suite.tasks)
    out = Path(args.out) if args.out else ROOT / "assets" / f"release-{__version__}.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(tasks, assertions, len(suites)), encoding="utf-8")
    print(f"{out}  ({tasks} tasks, {assertions} assertions, {len(suites)} suites)")

    if args.png:
        binary = shutil.which("rsvg-convert")
        if not binary:
            print("rsvg-convert not found; SVG written, PNG skipped", file=sys.stderr)
            return 1
        png = out.with_suffix(".png")
        subprocess.run([binary, "--width", "1600", "--format", "png", "--output", str(png), str(out)], check=True)
        print(png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
