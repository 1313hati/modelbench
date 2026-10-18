#!/usr/bin/env python3
"""Build the modelbench ASCII banner (and optionally a rendered JPG of it).

    python scripts/make_banner.py --text assets/banner.txt
    python scripts/make_banner.py --jpg ~/modelbench-ascii.jpg   # needs pillow

The art is plain text on purpose: it renders identically in a README, a
terminal, a CI log and a plain text file.  The JPG is a faithful render of the
same characters, so the two never drift apart.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# 5x7 block font, one string per row.  Only the letters the wordmark needs.
FONT = {
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
}

GLYPH_W = 5
GLYPH_H = 7
GAP = 2


def wordmark(word: str = "MODELBENCH") -> list[str]:
    width = len(word) * (GLYPH_W + GAP) - GAP
    grid = [[" "] * width for _ in range(GLYPH_H)]
    x = 0
    for char in word:
        glyph = FONT[char]
        for row in range(GLYPH_H):
            for col in range(GLYPH_W):
                if glyph[row][col] == "1":
                    grid[row][x + col] = "█"
        x += GLYPH_W + GAP
    return ["".join(row).rstrip() for row in grid]


TAGLINE = "a local AI benchmark for coding and more"
SUB = "llama.cpp · vLLM · Ollama · any OpenAI-compatible endpoint"


def card(lines: list[str], title: str = "modelbench", inner: int = 60) -> list[str]:
    label = f"─ {title} "
    out = ["  ┌" + label + "─" * (inner - len(label)) + "┐"]
    for line in lines:
        out.append("  │" + (" " + line).ljust(inner)[:inner] + "│")
    out.append("  └" + "─" * inner + "┘")
    return out


def build() -> str:
    lines = [""]
    lines += ["  " + row for row in wordmark()]
    lines.append("")
    lines.append("  " + TAGLINE)
    lines.append("  " + SUB)
    lines.append("")
    lines += card(
        [
            "$ modelbench run --target local --samples 2",
            "",
            "suite   core-v2 · 12 tasks · 296 hidden assertions",
            "target  local-27b @ 127.0.0.1:8080/v1",
            "",
            "[ 09/24] t07_thread_queue   s1  23/23 100.0%   41.2s",
            "[ 10/24] t08_code_review    s1  14/14 100.0%   22.7s",
            "[ 11/24] t09_csv_rfc4180    s1  33/33 100.0%   35.0s",
            "",
            "run complete · 24 records · 18m04s · REPORT.md written",
        ]
    )
    lines.append("")
    lines.append("  install  pipx install modelbench")
    lines.append("  source   github.com/1313hati/modelbench")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# rendering (optional, needs pillow)
# --------------------------------------------------------------------------- #
BLOCKS = set("█▓▀▄▁▂▃▅▆▇")


def render_jpg(text: str, path: Path, cell: int = 30) -> Path:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    font_path = next(
        (
            p
            for p in (
                "/usr/share/fonts/TTF/JetBrainsMono-Regular.ttf",
                "/usr/share/fonts/noto/NotoSansMono-Regular.ttf",
                "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",
            )
            if Path(p).is_file()
        ),
        None,
    )
    if font_path is None:
        raise SystemExit("no monospace font found")

    cell_w = cell * 0.62
    cell_h = cell * 1.18
    font = ImageFont.truetype(font_path, int(cell * 0.99))
    rows = text.split("\n")
    cols = max(len(r) for r in rows)

    pad_x, pad_y = int(cell_w * 3), int(cell_h * 2)
    width = int(cols * cell_w + pad_x * 2)
    height = int(len(rows) * cell_h + pad_y * 2)

    img = Image.new("RGB", (width, height), "#070a12")
    draw = ImageDraw.Draw(img)
    top_color, bottom_color = (12, 18, 34), (5, 7, 13)
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line([(0, y), (width, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top_color, bottom_color)))

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    start, end = (64, 231, 214), (154, 131, 255)
    bar_frac = {"▁": 0.125, "▂": 0.25, "▃": 0.375, "▄": 0.5, "▅": 0.625, "▆": 0.75, "▇": 0.875, "█": 1.0}

    def color_at(x: float, y: float) -> tuple[int, int, int]:
        t = max(0.0, min(1.0, x / width * 0.62 + y / height * 0.38))
        return tuple(int(a + (b - a) * t) for a, b in zip(start, end))

    for row_index, row in enumerate(rows):
        for col_index, char in enumerate(row):
            if char == " ":
                continue
            x = pad_x + col_index * cell_w
            y = pad_y + row_index * cell_h
            colour = color_at(x, y)
            if char in BLOCKS:
                # Full-bleed cells so stacked rows of blocks tile without seams.
                box = [x, y, x + cell_w + 0.7, y + cell_h + 1.0]
                if char == "▓":
                    ld.rectangle(box, fill=colour + (120,))
                elif char == "▀":
                    ld.rectangle([x, y, x + cell_w + 0.7, y + cell_h / 2], fill=colour + (255,))
                elif char == "█":
                    ld.rectangle(box, fill=colour + (255,))
                else:
                    frac = bar_frac[char]
                    ld.rectangle([x, y + cell_h * (1 - frac), x + cell_w + 0.7, y + cell_h + 1.0], fill=colour + (255,))
            else:
                ld.text((x, y + cell_h * 0.10), char, font=font, fill=colour + (255,))

    glow = layer.filter(ImageFilter.GaussianBlur(cell * 0.5)).point(lambda v: int(v * 0.5))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    img = Image.alpha_composite(img, layer)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(0, height, 3):
        od.line([(0, y), (width, y)], fill=(0, 0, 0, 24))
    img = Image.alpha_composite(img, overlay)

    vignette = Image.new("L", (width, height), 0)
    ImageDraw.Draw(vignette).ellipse([-width * 0.25, -height * 0.5, width * 1.25, height * 1.5], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(width * 0.08))
    black = Image.new("RGBA", (width, height), (0, 0, 0, 235))
    img = Image.composite(img, black, vignette)

    if path.suffix.lower() in {".jpg", ".jpeg"}:
        img.convert("RGB").save(path, quality=93, subsampling=0, optimize=True)
    else:
        img.save(path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="assets/banner.txt", help="where to write the ASCII art")
    parser.add_argument("--jpg", default=None, help="also render a JPG of the same art")
    parser.add_argument("--cell", type=int, default=30, help="pixel size of one character cell")
    args = parser.parse_args()

    art = build()
    if args.text:
        path = Path(args.text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(art, encoding="utf-8")
        print(f"wrote {path} ({max(len(line) for line in art.splitlines())} cols)")
    if args.jpg:
        out = render_jpg(art, Path(args.jpg).expanduser(), cell=args.cell)
        print(f"wrote {out}")
    if not args.text and not args.jpg:
        print(art)


if __name__ == "__main__":
    main()
