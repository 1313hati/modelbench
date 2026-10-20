#!/usr/bin/env python3
"""Blueprint release plate: 1600x900, Prussian ground, ivory hairlines.

    python scripts/make_release_plate.py            # assets/release-<version>.png
    python scripts/make_release_plate.py --out /tmp/x.png

Words come from ``scripts/release-themes/<version>.json``; the sheet, the grid
and the title block come from the digital-leonardo blueprint toolkit. Counts are
read from the packaged suites so the plate cannot drift from the code.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

from PIL import ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from blueprint import (  # noqa: E402
    AMBER, CYAN, INK, MUTED, MONO, MONO_B, SERIF, SERIF_B,
    arrow, fitted, sheet_frame, title_block, tracked,
)

from modelbench import __version__  # noqa: E402
from modelbench.tasks import available_suites  # noqa: E402

W, H = 1600, 900


def load_theme(version: str) -> dict:
    path = ROOT / "scripts" / "release-themes" / f"{version}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def card(d: ImageDraw.ImageDraw, box, value: str, title: str, sub: str, fonts) -> None:
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=(11, 31, 53, 210), outline=INK + (60,), width=1)
    tracked(d, (x0 + 16, y0 + 14), value, fonts["value"], CYAN, 1.4)
    d.text((x0 + 16, y0 + 52), title, font=fonts["title"], fill=INK)
    lines = textwrap.wrap(sub, width=52)[:2]
    for i, line in enumerate(lines):
        tracked(d, (x0 + 16, y0 + 90 + i * 18), line, fonts["sub"], MUTED, 0.8)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    out = Path(args.out) if args.out else ROOT / "assets" / f"release-{args.version}.png"

    theme = load_theme(args.version)
    suites = available_suites()
    core = next((s for s in suites if s.id == "core-v2"), suites[0] if suites else None)
    tasks = len(core.tasks) if core else 0
    checks = core.total_checks if core else 0

    img, d = sheet_frame(W, H)
    fonts = {
        "value": ImageFont.truetype(MONO_B, 24),
        "title": ImageFont.truetype(SERIF_B, 27),
        "sub": ImageFont.truetype(MONO, 13),
        "eyebrow": ImageFont.truetype(MONO, 15),
        "subhead": ImageFont.truetype(SERIF, 22),
        "readout": ImageFont.truetype(MONO, 16),
        "note": ImageFont.truetype(MONO, 13),
    }

    tracked(d, (80, 74), theme["eyebrow"], fonts["eyebrow"], MUTED, 2.2)
    head = fitted(d, theme["headline"], SERIF_B, 54, 1200, tracking=1.4)
    d.text((80, 104), theme["headline"], font=head, fill=INK)
    d.text((80, 186), theme["subhead"], font=fonts["subhead"], fill=MUTED)

    # dimension line under the headline: the suite's declared size
    y = 244
    d.line([(80, y), (1520, y)], fill=INK + (90,), width=1)
    d.line([(80, y - 6), (80, y + 6)], fill=INK + (140,), width=1)
    d.line([(1520, y - 6), (1520, y + 6)], fill=INK + (140,), width=1)
    arrow(d, (88, y), 180, size=10)
    arrow(d, (1512, y), 0, size=10)
    label = f"{tasks} TASKS  ·  {checks} DECLARED ASSERTIONS  ·  ONE SUITE, ANY MODEL SIZE"
    tracked(d, (80, y + 10), label, fonts["readout"], MUTED, 1.6)

    # 3 x 2 card grid inside the drawing band
    cols, rows = 3, 2
    gap = 24
    x0, x1 = 80, 1520
    top, bottom = 300, 664
    cw = (x1 - x0 - gap * (cols - 1)) / cols
    ch = (bottom - top - gap) / rows
    for index, (value, title, sub) in enumerate(theme["tiles"][: cols * rows]):
        r, c = divmod(index, cols)
        bx = x0 + c * (cw + gap)
        by = top + r * (ch + gap)
        card(d, (bx, by, bx + cw, by + ch), value, title, sub, fonts)

    # the one amber callout: the release date
    d.line([(80, 712), (1080, 712)], fill=INK + (70,), width=1)
    tracked(d, (80, 728), "MEASURED, NOT QUOTED  ·  EVERY DIVISOR DECLARED", fonts["readout"], CYAN, 1.8)
    tracked(d, (80, 760), "github.com/1313hati/modelbench", fonts["note"], AMBER, 1.2)

    title_block(d, W, H, f"MB-{args.version}", date="20 OCT 2026", handle="@1101hati")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
