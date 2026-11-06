"""Polygon regions: winding numbers, miter offsets, convex clipping and boolean difference."""

from __future__ import annotations

import math

from .geometry import (
    Point,
    Subpath,
    flatten,
    point_in_polygon,
    same_point,
    signed_area,
    with_orientation,
)


def _side(a: Point, b: Point, p: Point) -> float:
    """Positive when ``p`` is left of the directed edge a -> b (y up, counter-clockwise interior)."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _crossing(p: Point, q: Point, sp: float, sq: float) -> Point:
    t = sp / (sp - sq)
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def counter_clockwise(window: list[Point]) -> list[Point]:
    return list(window) if signed_area(window) > 0 else list(reversed(window))


def inside_convex(point: Point, window: list[Point], eps: float = 1e-9) -> bool:
    edges = counter_clockwise(window)
    return all(_side(edges[i], edges[(i + 1) % len(edges)], point) >= -eps for i in range(len(edges)))


def clip_convex(points: list[Point], window: list[Point]) -> list[Point]:
    """Clip a closed polygon to a convex window (Sutherland-Hodgman)."""
    edges = counter_clockwise(window)
    out = list(points)
    for i, a in enumerate(edges):
        b = edges[(i + 1) % len(edges)]
        src, out = out, []
        if not src:
            break
        prev = src[-1]
        prev_side = _side(a, b, prev)
        for cur in src:
            cur_side = _side(a, b, cur)
            if cur_side >= 0.0:
                if prev_side < 0.0:
                    out.append(_crossing(prev, cur, prev_side, cur_side))
                out.append(cur)
            elif prev_side >= 0.0:
                out.append(_crossing(prev, cur, prev_side, cur_side))
            prev, prev_side = cur, cur_side
    return out


def _edge_normal(x1: float, y1: float, x2: float, y2: float, outward: float) -> Point:
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    return (outward * dy / length, -outward * dx / length)


def offset_closed(points: list[Point], distance: float) -> list[Point]:
    """Grow (positive distance) or shrink a closed polygon, moving each vertex along its miter normal."""
    count = len(points)
    outward = 1.0 if signed_area(points) > 0 else -1.0
    result: list[Point] = []
    for i in range(count):
        px, py = points[i]
        ax, ay = points[i - 1]
        bx, by = points[(i + 1) % count]
        n1 = _edge_normal(ax, ay, px, py, outward)
        n2 = _edge_normal(px, py, bx, by, outward)
        mx, my = n1[0] + n2[0], n1[1] + n2[1]
        length = math.hypot(mx, my)
        if length < 1e-12:
            result.append((px + n1[0] * distance, py + n1[1] * distance))
            continue
        mx, my = mx / length, my / length
        scale = distance / max(0.5, mx * n1[0] + my * n1[1])
        result.append((px + mx * scale, py + my * scale))
    return result


def winding_number(point: Point, polygon: list[Point]) -> int:
    """Signed crossing count of a closed polygon around a point: +1 inside a counter-clockwise loop."""
    x, y = point
    total = 0
    count = len(polygon)
    for i in range(count):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % count]
        cross = (x2 - x1) * (y - y1) - (x - x1) * (y2 - y1)
        if y1 <= y < y2 and cross > 0:
            total += 1
        elif y2 <= y < y1 and cross < 0:
            total -= 1
    return total


def _proper_crossing(p: Point, q: Point, r: Point, s: Point) -> Point | None:
    """The point where segment p-q properly crosses segment r-s, or None."""
    d1, d2 = _side(r, s, p), _side(r, s, q)
    d3, d4 = _side(p, q, r), _side(p, q, s)
    if d1 * d2 < 0.0 and d3 * d4 < 0.0:
        return _crossing(p, q, d1, d2)
    return None


def _parameter(p: Point, q: Point, hit: Point) -> float:
    dx, dy = q[0] - p[0], q[1] - p[1]
    return ((hit[0] - p[0]) * dx + (hit[1] - p[1]) * dy) / (dx * dx + dy * dy)


def without_repeats(points: list[Point]) -> list[Point]:
    """``points`` with consecutive duplicates removed, including a last point equal to the first."""
    out: list[Point] = []
    for p in points:
        if not out or not same_point(p, out[-1]):
            out.append(p)
    while len(out) > 1 and same_point(out[0], out[-1]):
        out.pop()
    return out


def _with_hits(poly: list[Point], hits: dict[int, list[tuple[float, Point]]]) -> list[Point]:
    """``poly`` with its crossing points inserted along each edge, in order."""
    out: list[Point] = []
    for i, p in enumerate(poly):
        out.append(p)
        out.extend(point for _, point in sorted(hits.get(i, []), key=lambda hit: hit[0]))
    return out


def subtract_polygon(subject: list[Point], clip: list[Point]) -> list[list[Point]]:
    """Loops that outline ``subject`` minus the closed polygon ``clip``.

    The boundaries must cross in general position (no shared vertices, no collinear edges), and
    the polygons must be simple. Each returned loop keeps the kept area on its left: outer loops
    are counter-clockwise, holes clockwise. Raises ValueError when the boundaries do not close.
    """
    subject = counter_clockwise(without_repeats(subject))
    clip = counter_clockwise(without_repeats(clip))
    subject_hits: dict[int, list[tuple[float, Point]]] = {}
    clip_hits: dict[int, list[tuple[float, Point]]] = {}
    for i in range(len(subject)):
        p, q = subject[i], subject[(i + 1) % len(subject)]
        for j in range(len(clip)):
            r, s = clip[j], clip[(j + 1) % len(clip)]
            hit = _proper_crossing(p, q, r, s)
            if hit is None:
                continue
            subject_hits.setdefault(i, []).append((_parameter(p, q, hit), hit))
            clip_hits.setdefault(j, []).append((_parameter(r, s, hit), hit))

    edges: dict[Point, Point] = {}

    def keep(start: Point, end: Point) -> None:
        if start in edges:
            raise ValueError("boundaries meet at a shared point; the difference is not traceable")
        edges[start] = end

    outline = _with_hits(subject, subject_hits)
    for k, start in enumerate(outline):
        end = outline[(k + 1) % len(outline)]
        if not point_in_polygon(_midpoint(start, end), clip):
            keep(start, end)
    cutter = _with_hits(clip, clip_hits)
    for k, start in enumerate(cutter):
        end = cutter[(k + 1) % len(cutter)]
        if point_in_polygon(_midpoint(start, end), subject):
            keep(end, start)

    loops: list[list[Point]] = []
    while edges:
        first = next(iter(edges))
        loop = [first]
        current = edges.pop(first)
        while current != first:
            if current not in edges:
                raise ValueError("boundary pieces do not close into loops")
            loop.append(current)
            current = edges.pop(current)
        if len(loop) < 3:
            raise ValueError("a boundary loop is degenerate")
        loops.append(loop)
    return loops


def _midpoint(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def parity_oriented(subpaths: list[Subpath]) -> list[Subpath]:
    """Orient contours so nonzero filling gives the same region as even-odd filling of them."""
    polygons = [flatten(sub) for sub in subpaths]
    result: list[Subpath] = []
    for i, sub in enumerate(subpaths):
        probe = polygons[i][0]
        depth = sum(1 for j, poly in enumerate(polygons) if j != i and point_in_polygon(probe, poly))
        result.append(with_orientation(sub, positive=depth % 2 == 0))
    return result
