"""Geometry for the artwork generators: affine matrices, SVG path data, polylines.

Coordinates are plain floats. Paths are lists of subpaths made of absolute lines and
cubic curves, which is all Android VectorDrawable needs once transforms are baked in.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Union

Point = tuple[float, float]
Matrix = tuple[float, float, float, float, float, float]

IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_NUMBER_RE = re.compile(_NUMBER)
_TRANSFORM_RE = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
_PATH_COMMANDS = frozenset("MmLlHhVvCcSsQqTtAaZz")


@dataclass(frozen=True)
class Line:
    x: float
    y: float


@dataclass(frozen=True)
class Cubic:
    x1: float
    y1: float
    x2: float
    y2: float
    x: float
    y: float


Segment = Union[Line, Cubic]


@dataclass
class Subpath:
    """One contour: a start point, then segments. ``closed`` adds the implicit closing edge."""

    start: Point
    segments: list[Segment] = field(default_factory=list)
    closed: bool = False


# ---------------------------------------------------------------- matrices


def mul(outer: Matrix, inner: Matrix) -> Matrix:
    """Return outer * inner, so ``inner`` is applied to a point first (SVG transform order)."""
    a, b, c, d, e, f = outer
    a2, b2, c2, d2, e2, f2 = inner
    return (
        a * a2 + c * b2,
        b * a2 + d * b2,
        a * c2 + c * d2,
        b * c2 + d * d2,
        a * e2 + c * f2 + e,
        b * e2 + d * f2 + f,
    )


def apply(m: Matrix, x: float, y: float) -> Point:
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def scale_factor(m: Matrix) -> float:
    """Length scale of a transform (geometric mean of its axis scales)."""
    return math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))


def uniform(s: float, tx: float = 0.0, ty: float = 0.0) -> Matrix:
    return (s, 0.0, 0.0, s, tx, ty)


def parse_transform(text: str | None) -> Matrix:
    """Parse an SVG ``transform`` attribute into one matrix."""
    result = IDENTITY
    if not text:
        return result
    for name, args in _TRANSFORM_RE.findall(text):
        nums = [float(v) for v in _NUMBER_RE.findall(args)]
        if name == "matrix" and len(nums) == 6:
            step = (nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
        elif name == "translate" and len(nums) in (1, 2):
            step = (1.0, 0.0, 0.0, 1.0, nums[0], nums[1] if len(nums) == 2 else 0.0)
        elif name == "scale" and len(nums) in (1, 2):
            step = (nums[0], 0.0, 0.0, nums[-1], 0.0, 0.0)
        elif name == "rotate" and len(nums) in (1, 3):
            cos_a, sin_a = math.cos(math.radians(nums[0])), math.sin(math.radians(nums[0]))
            step = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(nums) == 3:
                cx, cy = nums[1], nums[2]
                step = mul(uniform(1.0, cx, cy), mul(step, uniform(1.0, -cx, -cy)))
        elif name == "skewX" and len(nums) == 1:
            step = (1.0, 0.0, math.tan(math.radians(nums[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and len(nums) == 1:
            step = (1.0, math.tan(math.radians(nums[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            raise ValueError(f"unsupported transform {name}({args.strip()})")
        result = mul(result, step)
    return result


# ---------------------------------------------------------------- path data


def endpoint(segment: Segment) -> Point:
    return (segment.x, segment.y)


def transform_subpath(sub: Subpath, m: Matrix) -> Subpath:
    segments: list[Segment] = []
    for seg in sub.segments:
        if isinstance(seg, Line):
            x, y = apply(m, seg.x, seg.y)
            segments.append(Line(x, y))
        else:
            x1, y1 = apply(m, seg.x1, seg.y1)
            x2, y2 = apply(m, seg.x2, seg.y2)
            x, y = apply(m, seg.x, seg.y)
            segments.append(Cubic(x1, y1, x2, y2, x, y))
    return Subpath(apply(m, *sub.start), segments, sub.closed)


class _Scanner:
    """Cursor over path data. Arc flags are single digits and may be written without separators."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def skip(self) -> None:
        while self.pos < len(self.text) and (self.text[self.pos].isspace() or self.text[self.pos] == ","):
            self.pos += 1

    def at_end(self) -> bool:
        self.skip()
        return self.pos >= len(self.text)

    def peek(self) -> str:
        self.skip()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def number(self) -> float:
        self.skip()
        match = _NUMBER_RE.match(self.text, self.pos)
        if not match:
            raise ValueError(f"expected a number at offset {self.pos} of path data")
        self.pos = match.end()
        return float(match.group(0))

    def flag(self) -> float:
        self.skip()
        ch = self.text[self.pos : self.pos + 1]
        if ch not in ("0", "1"):
            raise ValueError(f"expected an arc flag at offset {self.pos} of path data")
        self.pos += 1
        return float(ch)


def parse_path(d: str) -> list[Subpath]:
    """Parse SVG path data into absolute subpaths (H, V, S, Q, T and A are converted)."""
    sc = _Scanner(d)
    subpaths: list[Subpath] = []
    current: Subpath | None = None
    x = y = start_x = start_y = 0.0
    cmd = ""
    prev = ""
    last_c2: Point | None = None
    last_q: Point | None = None

    while not sc.at_end():
        ch = sc.peek()
        if ch in _PATH_COMMANDS:
            cmd = ch
            sc.pos += 1
        elif not cmd:
            raise ValueError("path data must start with a command")
        op = cmd.upper()
        rel = cmd.islower()

        if op == "Z":
            if current is not None:
                if (x, y) != (start_x, start_y):
                    current.segments.append(Line(start_x, start_y))
                current.closed = True
            current = None
            x, y = start_x, start_y
            last_c2 = last_q = None
            prev = op
            continue

        if op == "M":
            nx, ny = sc.number(), sc.number()
            if rel:
                nx, ny = nx + x, ny + y
            current = Subpath((nx, ny))
            subpaths.append(current)
            x, y = start_x, start_y = nx, ny
            cmd = "l" if rel else "L"
            last_c2 = last_q = None
            prev = "M"
            continue

        if current is None:
            current = Subpath((x, y))
            subpaths.append(current)
            start_x, start_y = x, y

        if op in ("L", "H", "V"):
            if op == "L":
                nx, ny = sc.number(), sc.number()
                if rel:
                    nx, ny = nx + x, ny + y
            elif op == "H":
                nx, ny = sc.number(), y
                if rel:
                    nx += x
            else:
                nx, ny = x, sc.number()
                if rel:
                    ny += y
            current.segments.append(Line(nx, ny))
            x, y = nx, ny
            last_c2 = last_q = None
        elif op in ("C", "S"):
            if op == "C":
                x1, y1 = sc.number(), sc.number()
                if rel:
                    x1, y1 = x1 + x, y1 + y
            elif prev in ("C", "S") and last_c2 is not None:
                x1, y1 = 2 * x - last_c2[0], 2 * y - last_c2[1]
            else:
                x1, y1 = x, y
            x2, y2 = sc.number(), sc.number()
            nx, ny = sc.number(), sc.number()
            if rel:
                x2, y2, nx, ny = x2 + x, y2 + y, nx + x, ny + y
            current.segments.append(Cubic(x1, y1, x2, y2, nx, ny))
            last_c2 = (x2, y2)
            x, y = nx, ny
            last_q = None
        elif op in ("Q", "T"):
            if op == "Q":
                qx, qy = sc.number(), sc.number()
                nx, ny = sc.number(), sc.number()
                if rel:
                    qx, qy, nx, ny = qx + x, qy + y, nx + x, ny + y
            else:
                nx, ny = sc.number(), sc.number()
                if rel:
                    nx, ny = nx + x, ny + y
                if prev in ("Q", "T") and last_q is not None:
                    qx, qy = 2 * x - last_q[0], 2 * y - last_q[1]
                else:
                    qx, qy = x, y
            c1 = (x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y))
            c2 = (nx + 2 / 3 * (qx - nx), ny + 2 / 3 * (qy - ny))
            current.segments.append(Cubic(c1[0], c1[1], c2[0], c2[1], nx, ny))
            last_q = (qx, qy)
            last_c2 = None
            x, y = nx, ny
        elif op == "A":
            rx, ry, rot = sc.number(), sc.number(), sc.number()
            large, sweep = sc.flag(), sc.flag()
            nx, ny = sc.number(), sc.number()
            if rel:
                nx, ny = nx + x, ny + y
            current.segments.extend(arc_to_cubics(x, y, rx, ry, rot, large, sweep, nx, ny))
            x, y = nx, ny
            last_c2 = last_q = None
        prev = op

    return [sub for sub in subpaths if sub.segments or sub.closed]


def arc_to_cubics(
    x1: float,
    y1: float,
    rx: float,
    ry: float,
    rotation_deg: float,
    large_arc: float,
    sweep: float,
    x2: float,
    y2: float,
) -> list[Segment]:
    """Convert an SVG elliptical arc (endpoint form) to cubic segments of at most 90 degrees."""
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0.0 or ry == 0.0:
        return [Line(x2, y2)]
    phi = math.radians(rotation_deg)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    lam = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if lam > 1.0:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if bool(large_arc) == bool(sweep):
        coef = -coef
    cxp = coef * rx * y1p / ry
    cyp = -coef * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    ux, uy = (x1p - cxp) / rx, (y1p - cyp) / ry
    vx, vy = (-x1p - cxp) / rx, (-y1p - cyp) / ry
    theta1 = angle(1.0, 0.0, ux, uy)
    dtheta = angle(ux, uy, vx, vy)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi

    pieces = max(1, math.ceil(abs(dtheta) / (math.pi / 2) - 1e-9))
    delta = dtheta / pieces
    t = 4.0 / 3.0 * math.tan(delta / 4.0)

    def point(a: float) -> Point:
        return (
            cx + rx * math.cos(a) * cos_phi - ry * math.sin(a) * sin_phi,
            cy + rx * math.cos(a) * sin_phi + ry * math.sin(a) * cos_phi,
        )

    def tangent(a: float) -> Point:
        return (
            -rx * math.sin(a) * cos_phi - ry * math.cos(a) * sin_phi,
            -rx * math.sin(a) * sin_phi + ry * math.cos(a) * cos_phi,
        )

    segments: list[Segment] = []
    for i in range(pieces):
        a1 = theta1 + i * delta
        a2 = a1 + delta
        p1, p2 = point(a1), point(a2)
        d1, d2 = tangent(a1), tangent(a2)
        c1 = (p1[0] + t * d1[0], p1[1] + t * d1[1])
        c2 = (p2[0] - t * d2[0], p2[1] - t * d2[1])
        if i == pieces - 1:
            p2 = (x2, y2)
        segments.append(Cubic(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1]))
    return segments


def ellipse(cx: float, cy: float, rx: float, ry: float) -> Subpath:
    k = 0.5522847498
    segments: list[Segment] = [
        Cubic(cx + rx, cy + ry * k, cx + rx * k, cy + ry, cx, cy + ry),
        Cubic(cx - rx * k, cy + ry, cx - rx, cy + ry * k, cx - rx, cy),
        Cubic(cx - rx, cy - ry * k, cx - rx * k, cy - ry, cx, cy - ry),
        Cubic(cx + rx * k, cy - ry, cx + rx, cy - ry * k, cx + rx, cy),
    ]
    return Subpath((cx + rx, cy), segments, closed=True)


def rect(x: float, y: float, w: float, h: float) -> Subpath:
    return Subpath(
        (x, y),
        [Line(x + w, y), Line(x + w, y + h), Line(x, y + h), Line(x, y)],
        closed=True,
    )


def flatten(sub: Subpath, steps: int = 12) -> list[Point]:
    """Sample a subpath into a polyline (the start point is included once, even if a closing segment
    returns to it)."""
    points = [sub.start]
    x0, y0 = sub.start
    for seg in sub.segments:
        if isinstance(seg, Line):
            points.append((seg.x, seg.y))
        else:
            for i in range(1, steps + 1):
                t = i / steps
                mt = 1.0 - t
                a = mt * mt * mt
                b = 3 * mt * mt * t
                c = 3 * mt * t * t
                d = t * t * t
                points.append(
                    (
                        a * x0 + b * seg.x1 + c * seg.x2 + d * seg.x,
                        a * y0 + b * seg.y1 + c * seg.y2 + d * seg.y,
                    )
                )
        x0, y0 = endpoint(seg)
    if sub.closed and len(points) > 1 and same_point(points[-1], points[0]):
        points.pop()
    return points


def same_point(a: Point, b: Point, eps: float = 1e-9) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) <= eps


def signed_area(points: list[Point]) -> float:
    """Shoelace area of a closed polygon: positive for counter-clockwise in y-up space."""
    total = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def reverse_subpath(sub: Subpath) -> Subpath:
    points = [sub.start] + [endpoint(seg) for seg in sub.segments]
    segments: list[Segment] = []
    for i in range(len(sub.segments) - 1, -1, -1):
        seg = sub.segments[i]
        before = points[i]
        if isinstance(seg, Line):
            segments.append(Line(before[0], before[1]))
        else:
            segments.append(Cubic(seg.x2, seg.y2, seg.x1, seg.y1, before[0], before[1]))
    return Subpath(points[-1], segments, sub.closed)


def with_orientation(sub: Subpath, positive: bool) -> Subpath:
    """Return the subpath wound counter-clockwise (positive) or clockwise (negative)."""
    area = signed_area(flatten(sub))
    if (area > 0) != positive and area != 0.0:
        return reverse_subpath(sub)
    return sub


def point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def stroke_polygon(points: list[Point], half_width: float, cap_steps: int = 4) -> list[Point]:
    """Outline of a stroked polyline with round caps, as one closed polygon."""
    pts: list[Point] = []
    for p in points:
        if not pts or (abs(p[0] - pts[-1][0]) + abs(p[1] - pts[-1][1])) > 1e-9:
            pts.append(p)
    if len(pts) < 2 or half_width <= 0.0:
        return []

    def unit(dx: float, dy: float) -> Point:
        length = math.hypot(dx, dy) or 1.0
        return (dx / length, dy / length)

    seg_dirs = [unit(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    normals: list[Point] = []
    for i in range(len(pts)):
        if i == 0:
            d = seg_dirs[0]
        elif i == len(pts) - 1:
            d = seg_dirs[-1]
        else:
            d1, d2 = seg_dirs[i - 1], seg_dirs[i]
            d = unit(d1[0] + d2[0], d1[1] + d2[1])
        normals.append((-d[1], d[0]))

    left = [(p[0] + n[0] * half_width, p[1] + n[1] * half_width) for p, n in zip(pts, normals)]
    right = [(p[0] - n[0] * half_width, p[1] - n[1] * half_width) for p, n in zip(pts, normals)]
    end_dir, start_dir = seg_dirs[-1], seg_dirs[0]
    end_normal, start_normal = normals[-1], normals[0]
    end_cap: list[Point] = []
    start_cap: list[Point] = []
    for k in range(1, cap_steps):
        theta = math.pi * k / cap_steps
        c, s = math.cos(theta), math.sin(theta)
        ex, ey = pts[-1]
        end_cap.append(
            (
                ex + half_width * (c * end_normal[0] + s * end_dir[0]),
                ey + half_width * (c * end_normal[1] + s * end_dir[1]),
            )
        )
        sx, sy = pts[0]
        start_cap.append(
            (
                sx + half_width * (-c * start_normal[0] - s * start_dir[0]),
                sy + half_width * (-c * start_normal[1] - s * start_dir[1]),
            )
        )
    return left + end_cap + list(reversed(right)) + start_cap


def bounds(points: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def format_number(value: float, digits: int = 3) -> str:
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def path_data(subpaths: list[Subpath], digits: int = 3) -> str:
    """Serialise subpaths as Android ``pathData`` (absolute M, L, C and Z commands)."""
    parts: list[str] = []
    for sub in subpaths:
        parts.append(f"M{format_number(sub.start[0], digits)},{format_number(sub.start[1], digits)}")
        for seg in sub.segments:
            if isinstance(seg, Line):
                parts.append(f"L{format_number(seg.x, digits)},{format_number(seg.y, digits)}")
            else:
                values = [seg.x1, seg.y1, seg.x2, seg.y2, seg.x, seg.y]
                parts.append("C" + ",".join(format_number(v, digits) for v in values))
        if sub.closed:
            parts.append("Z")
    return "".join(parts)


def control_points(sub: Subpath) -> list[Point]:
    """Every point a subpath mentions, control points included (a conservative bounding box)."""
    points = [sub.start]
    for seg in sub.segments:
        if isinstance(seg, Line):
            points.append((seg.x, seg.y))
        else:
            points.extend([(seg.x1, seg.y1), (seg.x2, seg.y2), (seg.x, seg.y)])
    return points


def polygon_subpath(points: list[Point]) -> Subpath:
    """A closed straight-edged subpath through ``points``."""
    return Subpath(points[0], [Line(x, y) for x, y in points[1:]], closed=True)
