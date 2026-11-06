"""The "Embermine" wordmark as a monoline shape built from stroke centrelines.

The letters are drawn in glyph units (cap height 100, x-height 68, stroke 14, baseline at y = 0,
y up). No font file is read, so the output depends only on this module.
"""

from __future__ import annotations

import math

from .geometry import Point, polygon_subpath, stroke_polygon, with_orientation, apply
from .layers import Box, Piece, fit_matrix

WORDMARK_TEXT = "Embermine"
CAP = 100.0
X_HEIGHT = 68.0
STROKE = 14.0
GAP = 12.0
_HALF = STROKE / 2


def _angles(start: float, end: float, steps: int) -> list[float]:
    return [start + (end - start) * i / steps for i in range(steps + 1)]


def _arc(cx: float, cy: float, rx: float, ry: float, start: float, end: float) -> list[Point]:
    return [(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in _angles(start, end, 32)]


def _arch(xa: float, xb: float, yc: float) -> list[Point]:
    """Half ellipse from (xa, yc), over the top, down to (xb, yc)."""
    return _arc((xa + xb) / 2, yc, (xb - xa) / 2, (xb - xa) / 2, math.pi, 0.0)


def _glyph(ch: str) -> tuple[list[list[Point]], float]:
    """Stroke centrelines and advance width for one letter."""
    if ch == "E":
        return (
            [
                [(7, 0), (7, CAP)],
                [(7, CAP), (51, CAP)],
                [(7, CAP / 2), (44, CAP / 2)],
                [(7, 0), (51, 0)],
            ],
            58,
        )
    if ch == "m":
        yc = X_HEIGHT - 19.5
        return (
            [
                [(7, 0), (7, yc)],
                _arch(7, 46, yc),
                [(46, yc), (46, 0)],
                _arch(46, 85, yc),
                [(85, yc), (85, 0)],
            ],
            92,
        )
    if ch == "n":
        yc = X_HEIGHT - 26
        return ([[(7, 0), (7, yc)], _arch(7, 59, yc), [(59, yc), (59, 0)]], 66)
    if ch == "b":
        return ([[(7, 0), (7, CAP)], _arc(33, 34, 26, 34, math.pi, 3 * math.pi - 0.05)], 66)
    if ch == "e":
        return (
            [[(7, 34), (59, 34)], _arc(33, 34, 26, 34, 0.0, 2 * math.pi - 0.7)],
            66,
        )
    if ch == "r":
        return ([[(7, 0), (7, X_HEIGHT)], _arc(27, 48, 20, 20, math.pi, 0.55)], 52)
    if ch == "i":
        return ([[(7, 0), (7, X_HEIGHT)], [(7, 92), (7, 92.01)]], 14)
    raise ValueError(f"the wordmark has no glyph for {ch!r}")


def wordmark_polygons(text: str) -> list[list[Point]]:
    """Closed outlines of every stroke, in glyph units, one per stroke centreline."""
    polygons: list[list[Point]] = []
    x = 0.0
    for ch in text:
        strokes, advance = _glyph(ch)
        for stroke in strokes:
            shifted = [(px + x, py) for px, py in stroke]
            outline = stroke_polygon(shifted, _HALF)
            if outline:
                polygons.append(outline)
        x += advance + GAP
    return polygons


def wordmark_pieces(text: str, box: Box, fill: str) -> list[Piece]:
    """The text fitted and centred in ``box`` (viewport units), filled with ``fill``."""
    polygons = wordmark_polygons(text)
    xs = [p[0] for poly in polygons for p in poly]
    ys = [p[1] for poly in polygons for p in poly]
    m = fit_matrix((min(xs), min(ys), max(xs), max(ys)), box, flip=True)
    subpaths = [
        with_orientation(polygon_subpath([apply(m, x, y) for x, y in poly]), positive=True)
        for poly in polygons
    ]
    return [Piece(subpaths, fill=fill)]
