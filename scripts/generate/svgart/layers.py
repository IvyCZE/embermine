"""Icon layers read from icon.svg, and the Android path pieces built from them.

Every drawable fits the art with one matrix. The full-bleed background covers the whole canvas.
The foreground and monochrome layers put the ermine and flower inside the 66 dp safe zone of the
108 dp adaptive canvas. Illustrations fit the art into their own viewport.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .geometry import (
    Matrix,
    Point,
    Subpath,
    control_points,
    flatten,
    polygon_subpath,
    rect,
    scale_factor,
    signed_area,
    stroke_polygon,
    transform_subpath,
)
from .regions import counter_clockwise, offset_closed, parity_oriented, subtract_polygon
from .svgdoc import Document, Shape, parse_document

BACKGROUND_ID = "Ellipse 5"
SUNNY_GROUP = "sunny.svg 4"
FLOWER_GROUP = "flower.svg"
BLACK = "#000000"
CANVAS_DP = 108.0
SAFE_ZONE_DP = 66.0
MARGIN = 0.04

Bounds = tuple[float, float, float, float]
Box = tuple[float, float, float, float]


@dataclass
class IconArt:
    """The three artwork layers of icon.svg, in canvas units (the viewBox)."""

    size: float
    background: str
    sunny: Shape
    flower: Shape
    ermine: list[Shape]


@dataclass
class Piece:
    """One Android path: contours plus paint, already in the drawable's own units."""

    subpaths: list[Subpath]
    fill: str | None = None
    evenodd: bool = False
    stroke: str | None = None
    stroke_width: float = 0.0


def load_icon(path: Path) -> IconArt:
    return art_from_document(parse_document(path.read_text(encoding="utf-8")))


def art_from_document(doc: Document) -> IconArt:
    if doc.width != doc.height:
        raise ValueError("icon canvas must be square")
    background = _single(doc.shapes, "background", lambda s: s.name == BACKGROUND_ID)
    sunny = _single(
        doc.shapes,
        "sunny",
        lambda s: SUNNY_GROUP in s.ancestors and FLOWER_GROUP not in s.ancestors,
    )
    flower = _single(doc.shapes, "flower", lambda s: FLOWER_GROUP in s.ancestors)
    layer_shapes = (background, sunny, flower)
    ermine = [s for s in doc.shapes if all(s is not layer for layer in layer_shapes)]
    if background.fill is None or sunny.fill is None or flower.fill is None:
        raise ValueError("background, sunny and flower layers need a fill colour")
    if not ermine:
        raise ValueError("icon.svg has no ermine shapes")
    for shape in ermine:
        if shape.fill is None and shape.stroke is None:
            raise ValueError(f"ermine shape {shape.name!r} paints nothing")
    return IconArt(doc.width, background.fill, sunny, flower, ermine)


def _single(shapes: list[Shape], layer: str, match: Callable[[Shape], bool]) -> Shape:
    found = [shape for shape in shapes if match(shape)]
    if len(found) != 1:
        raise ValueError(f"expected exactly one {layer} shape in icon.svg, found {len(found)}")
    return found[0]


def _shape_bounds(shape: Shape) -> Bounds:
    points = [p for sub in shape.subpaths for p in control_points(sub)]
    pad = shape.stroke_width / 2 if shape.stroke else 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def art_bounds(art: IconArt) -> Bounds:
    """Bounds of the color art (flower and ermine, strokes included), in canvas units."""
    boxes = [_shape_bounds(shape) for shape in [art.flower, *art.ermine]]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def fit_matrix(bounds: Bounds, box: Box, flip: bool = False) -> Matrix:
    """Uniform scale and translation that centres ``bounds`` inside ``box``, keeping the aspect ratio."""
    x0, y0, x1, y1 = bounds
    bx0, by0, bx1, by1 = box
    scale = min((bx1 - bx0) / (x1 - x0), (by1 - by0) / (y1 - y0))
    sign = -1.0 if flip else 1.0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    tx = (bx0 + bx1) / 2 - scale * cx
    ty = (by0 + by1) / 2 - sign * scale * cy
    return (scale, 0.0, 0.0, sign * scale, tx, ty)


def safe_zone_box(width: float, height: float) -> Box:
    """The 66 dp square at the centre of a 108 dp adaptive canvas, in viewport units."""
    half = SAFE_ZONE_DP / 2 * width / CANVAS_DP
    cx, cy = width / 2, height / 2
    return (cx - half, cy - half, cx + half, cy + half)


def margin_box(width: float, height: float) -> Box:
    margin = MARGIN * min(width, height)
    return (margin, margin, width - margin, height - margin)


def _moved(shape: Shape, m: Matrix) -> list[Subpath]:
    return [transform_subpath(sub, m) for sub in shape.subpaths]


def _is_detail(shape: Shape) -> bool:
    """Black eyes, ears, tail tips and stroke-only lines: never a silhouette loop."""
    return shape.fill == BLACK or (shape.fill is None and shape.stroke == BLACK)


def _cut_outs(shape: Shape, m: Matrix) -> list[list[Point]]:
    """Outlines that ``shape`` removes from the silhouette, each wound counter-clockwise.

    Black details are removed whole. An open black stroke is removed as its stroke band, whether
    the shape is stroke-only or a light fill with a black stroke (the leg lines of Path 62 and 63,
    whose fill stays in the silhouette). A closed outline on a light fill stays in the silhouette.
    """
    half = shape.stroke_width * scale_factor(m) / 2 if shape.stroke else 0.0
    outlines: list[list[Point]] = []
    for sub in _moved(shape, m):
        points = flatten(sub)
        if shape.fill == BLACK:
            outline = offset_closed(points, half) if half > 0 else points
        elif shape.stroke == BLACK and not sub.closed:
            outline = stroke_polygon(points, half)
        elif _is_detail(shape):
            raise ValueError(f"stroke-only detail {shape.name!r} must be an open path")
        else:
            continue
        if len(outline) >= 3:
            outlines.append(counter_clockwise(outline))
    return outlines


def color_pieces(art: IconArt, m: Matrix) -> list[Piece]:
    """Flower, then the ermine in document order, with their own fills and strokes."""
    pieces = [Piece(_moved(art.flower, m), fill=art.flower.fill, evenodd=art.flower.evenodd)]
    for shape in art.ermine:
        pieces.append(
            Piece(
                _moved(shape, m),
                fill=shape.fill,
                evenodd=shape.evenodd,
                stroke=shape.stroke,
                stroke_width=shape.stroke_width * scale_factor(m),
            )
        )
    return pieces


def background_pieces(art: IconArt, m: Matrix, width: float, height: float) -> list[Piece]:
    """Full-bleed background colour, then the Sunny shape on top of it."""
    return [
        Piece([rect(0.0, 0.0, width, height)], fill=art.background),
        Piece(_moved(art.sunny, m), fill=art.sunny.fill, evenodd=art.sunny.evenodd),
    ]


def monochrome_pieces(art: IconArt, m: Matrix, fill: str) -> list[Piece]:
    """One opaque silhouette: the flower and the ermine's light parts, minus the cut-outs.

    Each silhouette loop (a light shape or the flower, wound counter-clockwise) has every cut-out
    subtracted from it, so the holes stay exact where loops overlap. The loops are then filled with
    the nonzero rule, which gives their union with the cut-outs removed.
    """
    cut_outs: list[list[Point]] = []
    for shape in art.ermine:
        cut_outs.extend(_cut_outs(shape, m))

    loops: list[list[Point]] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for shape in [art.flower, *(s for s in art.ermine if not _is_detail(s))]:
        for sub in parity_oriented(_moved(shape, m)):
            points = flatten(sub)
            key = tuple((round(x, 4), round(y, 4)) for x, y in points)
            if key in seen:
                continue
            seen.add(key)
            pieces = [counter_clockwise(points)]
            for cut in cut_outs:
                pieces = [part for loop in pieces for part in _cut_loop(loop, cut)]
            loops.extend(pieces)
    return [Piece([polygon_subpath(loop) for loop in loops], fill=fill)]


def _cut_loop(loop: list[Point], cut: list[Point]) -> list[list[Point]]:
    """``loop`` minus ``cut``, keeping the sign of the loop: a clockwise hole stays a hole.

    A loop counts +1 inside and a clockwise loop -1, so subtracting ``cut`` from a hole means
    subtracting it from the hole's region and flipping the result back to clockwise.
    """
    parts = subtract_polygon(counter_clockwise(loop), cut)
    if signed_area(loop) < 0:
        return [list(reversed(part)) for part in parts]
    return parts
