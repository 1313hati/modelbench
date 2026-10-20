#!/usr/bin/env python3
"""Blueprint plates: engineering drawing language, digital light.

Deep Prussian ground, ivory line work, a drafting grid and dimension lines with
arrowheads. One accent for the datum that matters. Title block in the corner.
The "digital" part is in the glow on the accent and the bracket-style readouts,
not in the geometry: the drawing is still a drawing.

All geometry is in pixels on the sheet; nothing is scaled from the Leonardo kit.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SERIF = "/usr/share/fonts/gsfonts/C059-Roman.otf"
SERIF_B = "/usr/share/fonts/gsfonts/C059-Bold.otf"
MONO = "/usr/share/fonts/liberation/LiberationMono-Regular.ttf"
MONO_B = "/usr/share/fonts/liberation/LiberationMono-Bold.ttf"

GROUND = (11, 31, 53)
GROUND_DEEP = (7, 21, 38)
INK = (232, 239, 245)
MUTED = (150, 178, 198)
CYAN = (126, 214, 233)
AMBER = (238, 150, 84)

GRID_MINOR = 24
GRID_MAJOR = 120


# --------------------------------------------------------------------------
# sheet
# --------------------------------------------------------------------------
def sheet(w: int, h: int, seed: int = 7) -> Image.Image:
    """Blue ground with a vignette and a little paper tooth."""
    img = Image.new("RGB", (w, h), GROUND)
    px = img.load()
    rnd = random.Random(seed)
    cx, cy = w / 2, h / 2
    maxd = math.hypot(cx, cy)
    for y in range(h):
        for x in range(w):
            t = math.hypot(x - cx, y - cy) / maxd
            t = min(1.0, t * 1.12)
            r, g, b = GROUND
            dr, dg, db = GROUND_DEEP
            f = t ** 1.6
            n = rnd.randint(-3, 3)
            px[x, y] = (
                max(0, min(255, int(r + (dr - r) * f) + n)),
                max(0, min(255, int(g + (dg - g) * f) + n)),
                max(0, min(255, int(b + (db - b) * f) + n)),
            )
    return img


def _overlay_line(d: ImageDraw.ImageDraw, xy, colour, width=1, alpha=255):
    r, g, b = colour
    d.line(xy, fill=(r, g, b, alpha), width=width)


def grid(d: ImageDraw.ImageDraw, w: int, h: int, margin: int = 40) -> None:
    """Drafting grid, clipped to the drawing area."""
    for x in range(margin, w - margin + 1, GRID_MINOR):
        major = (x - margin) % GRID_MAJOR == 0
        _overlay_line(d, [(x, margin), (x, h - margin)], INK, 1, 26 if major else 12)
    for y in range(margin, h - margin + 1, GRID_MINOR):
        major = (y - margin) % GRID_MAJOR == 0
        _overlay_line(d, [(margin, y), (w - margin, y)], INK, 1, 26 if major else 12)


def border(d: ImageDraw.ImageDraw, w: int, h: int, inset: int = 40) -> None:
    _overlay_line(d, [(inset, inset), (w - inset, inset)], INK, 2, 210)
    _overlay_line(d, [(inset, h - inset), (w - inset, h - inset)], INK, 2, 210)
    _overlay_line(d, [(inset, inset), (inset, h - inset)], INK, 2, 210)
    _overlay_line(d, [(w - inset, inset), (w - inset, h - inset)], INK, 2, 210)
    # inner hairline, the way a drawing sheet is double-ruled
    _overlay_line(d, [(inset + 10, inset + 10), (w - inset - 10, inset + 10)], INK, 1, 90)
    _overlay_line(d, [(inset + 10, h - inset - 10), (w - inset - 10, h - inset - 10)], INK, 1, 90)
    _overlay_line(d, [(inset + 10, inset + 10), (inset + 10, h - inset - 10)], INK, 1, 90)
    _overlay_line(d, [(w - inset - 10, inset + 10), (w - inset - 10, h - inset - 10)], INK, 1, 90)


def ruler(d: ImageDraw.ImageDraw, w: int, h: int, inset: int = 40) -> None:
    """Tick marks along the top and left edges."""
    for x in range(inset, w - inset + 1, GRID_MINOR):
        major = (x - inset) % GRID_MAJOR == 0
        ln = 12 if major else 6
        _overlay_line(d, [(x, inset), (x, inset + ln)], INK, 1, 170 if major else 90)
    for y in range(inset, h - inset + 1, GRID_MINOR):
        major = (y - inset) % GRID_MAJOR == 0
        ln = 12 if major else 6
        _overlay_line(d, [(inset, y), (inset + ln, y)], INK, 1, 170 if major else 90)


# --------------------------------------------------------------------------
# type
# --------------------------------------------------------------------------
def tracked(d: ImageDraw.ImageDraw, xy, text: str, font, colour, tracking: float = 0.0, anchor_left=True):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=colour + (255,) if len(colour) == 3 else colour)
        x += d.textlength(ch, font=font) + tracking
    return x


def tracked_width(d: ImageDraw.ImageDraw, text: str, font, tracking: float = 0.0) -> float:
    return sum(d.textlength(c, font=font) for c in text) + tracking * max(0, len(text) - 1)


def fitted(d: ImageDraw.ImageDraw, text: str, path: str, size: int, width: float, floor: int = 18, tracking: float = 0.0):
    while size > floor:
        f = ImageFont.truetype(path, size)
        if tracked_width(d, text, f, tracking) <= width:
            return f
        size -= 2
    return ImageFont.truetype(path, floor)


# --------------------------------------------------------------------------
# drafting devices
# --------------------------------------------------------------------------
def hatch(d: ImageDraw.ImageDraw, box, colour, step: int = 9, width: int = 1, alpha: int = 220) -> None:
    """45-degree section hatching inside a box.

    Lines run along x - y = c; each one is clipped by testing the four edges and
    keeping the two that land on the box.
    """
    x0, y0, x1, y1 = [int(v) for v in box]
    for c in range(x0 - y1, x1 - y0 + 1, step):
        pts = []
        for x in (x0, x1):
            y = x - c
            if y0 <= y <= y1:
                pts.append((x, y))
        for y in (y0, y1):
            x = c + y
            if x0 <= x <= x1:
                pts.append((x, y))
        pts = sorted(set(pts))
        if len(pts) >= 2:
            _overlay_line(d, [pts[0], pts[-1]], colour, width, alpha)


def glow_line(d: ImageDraw.ImageDraw, xy, colour, width: int = 2, alpha: int = 255, bloom: int = 10) -> None:
    r, g, b = colour
    for i in range(bloom, 0, -1):
        a = int(alpha * 0.05 * (1 - i / bloom))
        _overlay_line(d, xy, (r, g, b), max(1, width + i), a)
    _overlay_line(d, xy, (r, g, b), width, alpha)


def arrow(d: ImageDraw.ImageDraw, tip, angle: float, size: int = 12, colour=INK, alpha: int = 230) -> None:
    x, y = tip
    for s in (+1, -1):
        a = angle + s * math.radians(17)
        _overlay_line(d, [(x, y), (x - size * math.cos(a), y - size * math.sin(a))], colour, 2, alpha)


def dimension(d: ImageDraw.ImageDraw, x0: float, x1: float, y: float, label: str, font, colour=CYAN,
              above: bool = True, rise: int = 18, alpha: int = 255) -> None:
    """Dimension line with arrowheads, extension ticks and a label."""
    glow_line(d, [(x0, y), (x1, y)], colour, 2, alpha, bloom=9)
    _overlay_line(d, [(x0, y - rise), (x0, y + rise)], colour, 1, 150)
    _overlay_line(d, [(x1, y - rise), (x1, y + rise)], colour, 1, 150)
    arrow(d, (x0, y), math.pi, colour=colour, alpha=alpha)
    arrow(d, (x1, y), 0.0, colour=colour, alpha=alpha)
    tw = tracked_width(d, label, font, 1.6)
    lx = (x0 + x1) / 2 - tw / 2
    ly = y - 34 if above else y + 14
    # clear a little of the grid behind the label, the way lettering sits in a gap
    d.rectangle((lx - 6, ly - 2, lx + tw + 6, ly + font.size + 4), fill=GROUND + (255,))
    tracked(d, (lx, ly), label, font, colour, 1.6)


def leader(d: ImageDraw.ImageDraw, start, end, label: str, font, colour=INK, alpha: int = 210) -> None:
    """Callout: elbow line from the feature to a label."""
    x0, y0 = start
    x1, y1 = end
    knee = (x1, y0)
    _overlay_line(d, [(x0, y0), knee], colour, 1, alpha)
    _overlay_line(d, [knee, (x1, y1)], colour, 1, alpha)
    _overlay_line(d, [(x1, y1), (x1 + 26, y1)], colour, 1, alpha)
    d.ellipse((x0 - 3, y0 - 3, x0 + 3, y0 + 3), outline=colour + (alpha,), width=1)
    tracked(d, (x1 + 34, y1 - font.size / 2), label, font, colour, 1.2)


def title_block(d: ImageDraw.ImageDraw, w: int, h: int, dwg: str, sheet_no: str = "1 / 1",
                scale: str = "1:1", date: str = "19 OCT 2026", handle: str = "@1313hati") -> None:
    bw, bh = 520, 118
    x1, y1 = w - 40, h - 40
    x0, y0 = x1 - bw, y1 - bh
    d.rectangle((x0, y0, x1, y1), fill=GROUND + (235,))
    _overlay_line(d, [(x0, y0), (x1, y0)], INK, 2, 220)
    _overlay_line(d, [(x0, y0), (x0, y1)], INK, 2, 220)
    _overlay_line(d, [(x0, y0 + 58), (x1, y0 + 58)], INK, 1, 150)
    _overlay_line(d, [(x0, y0 + 88), (x1, y0 + 88)], INK, 1, 120)
    _overlay_line(d, [(x0 + 300, y0 + 58), (x0 + 300, y1)], INK, 1, 120)

    f_big = ImageFont.truetype(MONO_B, 21)
    f_sm = ImageFont.truetype(MONO, 14)
    tracked(d, (x0 + 16, y0 + 14), dwg.upper(), f_big, INK, 1.8)
    tracked(d, (x0 + 16, y0 + 36), "MODELBENCH FIELD NOTES", f_sm, MUTED, 1.6)
    tracked(d, (x0 + 16, y0 + 68), f"SCALE {scale}", f_sm, MUTED, 1.4)
    tracked(d, (x0 + 16, y0 + 96), f"SHEET {sheet_no}", f_sm, MUTED, 1.4)
    tracked(d, (x0 + 316, y0 + 68), date, f_sm, MUTED, 1.4)
    tracked(d, (x0 + 316, y0 + 96), handle, f_sm, AMBER, 1.4)


def sheet_frame(w: int, h: int, seed: int = 7):
    img = sheet(w, h, seed=seed)
    d = ImageDraw.Draw(img, "RGBA")
    grid(d, w, h)
    border(d, w, h)
    ruler(d, w, h)
    return img, d
