"""Read the SVG subset that assets/icon/icon.svg uses, as flat shapes in canvas coordinates.

Supported: nested ``g`` elements with transforms, ``path``, ``ellipse`` and ``line`` shapes,
and ``clip-path`` references to a clipPath that holds one rect. Anything else raises, so an
artwork change that the generator does not understand fails the build instead of shipping
wrong art.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .geometry import (
    IDENTITY,
    Line,
    Matrix,
    Point,
    Subpath,
    apply,
    ellipse,
    flatten,
    mul,
    parse_path,
    parse_transform,
    polygon_subpath,
    scale_factor,
    transform_subpath,
)
from .regions import clip_convex, inside_convex

_CLIP_REF = re.compile(r"url\(#([^)]+)\)")
_HEX_COLOR = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
_STRUCTURAL = frozenset({"defs", "clipPath", "title", "desc", "metadata"})
_SHAPES = frozenset({"path", "ellipse", "line"})


@dataclass
class Shape:
    """One filled and/or stroked outline in canvas coordinates, clipped to its ancestors."""

    name: str
    ancestors: tuple[str, ...]
    subpaths: list[Subpath]
    fill: str | None
    evenodd: bool
    stroke: str | None
    stroke_width: float


@dataclass
class Document:
    width: float
    height: float
    shapes: list[Shape] = field(default_factory=list)


def parse_document(text: str) -> Document:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"invalid SVG: {exc}") from exc
    if _local(root.tag) != "svg":
        raise ValueError("root element is not <svg>")
    view_box = root.get("viewBox")
    if view_box is None:
        raise ValueError("SVG has no viewBox")
    values = [float(v) for v in view_box.replace(",", " ").split()]
    if len(values) != 4 or values[0] != 0 or values[1] != 0:
        raise ValueError("viewBox must be '0 0 width height'")
    defs = {el.get("id", ""): _clip_rect(el) for el in root.iter() if _local(el.tag) == "clipPath"}
    document = Document(values[2], values[3])
    _walk(root, IDENTITY, (), (), defs, document.shapes)
    return document


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clip_rect(clip: ET.Element) -> tuple[float, float, float, float]:
    children = list(clip)
    if len(children) != 1 or _local(children[0].tag) != "rect":
        raise ValueError(f"clipPath {clip.get('id')!r} must hold exactly one rect")
    rect = children[0]
    return (
        float(rect.get("x", "0")),
        float(rect.get("y", "0")),
        float(rect.get("width", "0")),
        float(rect.get("height", "0")),
    )


def _walk(
    parent: ET.Element,
    parent_matrix: Matrix,
    ancestors: tuple[str, ...],
    clips: tuple[list[Point], ...],
    defs: dict[str, tuple[float, float, float, float]],
    out: list[Shape],
) -> None:
    for child in parent:
        tag = _local(child.tag)
        if tag in _STRUCTURAL:
            continue
        if tag != "g" and tag not in _SHAPES:
            raise ValueError(f"unsupported SVG element <{tag}>")
        matrix = mul(parent_matrix, parse_transform(child.get("transform")))
        child_clips = clips
        clip_id = _clip_id(child.get("clip-path"))
        if clip_id is not None:
            if clip_id not in defs:
                raise ValueError(f"clip-path refers to unknown clipPath {clip_id!r}")
            x, y, w, h = defs[clip_id]
            window = [
                apply(matrix, x, y),
                apply(matrix, x + w, y),
                apply(matrix, x + w, y + h),
                apply(matrix, x, y + h),
            ]
            child_clips = clips + (window,)
        if tag == "g":
            _walk(child, matrix, ancestors + (child.get("id", ""),), child_clips, defs, out)
        else:
            out.append(_shape(child, tag, matrix, ancestors, child_clips))


def _clip_id(value: str | None) -> str | None:
    if value is None:
        return None
    match = _CLIP_REF.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"unsupported clip-path value {value!r}")
    return match.group(1)


def _style(el: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in ("fill", "fill-rule", "stroke", "stroke-width"):
        if el.get(key) is not None:
            values[key] = el.get(key, "").strip()
    for item in (el.get("style") or "").split(";"):
        if ":" in item:
            key, _, value = item.partition(":")
            values[key.strip()] = value.strip()
    return values


def _color(value: str | None) -> str | None:
    if value is None or value == "none":
        return None
    if not _HEX_COLOR.fullmatch(value):
        raise ValueError(f"unsupported colour {value!r}; use #RRGGBB or none")
    digits = value[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits.upper()


def _geometry(el: ET.Element, tag: str) -> list[Subpath]:
    if tag == "path":
        return parse_path(el.get("d", ""))
    if tag == "ellipse":
        return [ellipse(_num(el, "cx"), _num(el, "cy"), _num(el, "rx"), _num(el, "ry"))]
    return [Subpath((_num(el, "x1"), _num(el, "y1")), [Line(_num(el, "x2"), _num(el, "y2"))])]


def _num(el: ET.Element, name: str) -> float:
    return float(el.get(name, "0"))


def _shape(
    el: ET.Element,
    tag: str,
    matrix: Matrix,
    ancestors: tuple[str, ...],
    clips: tuple[list[Point], ...],
) -> Shape:
    subpaths = [transform_subpath(sub, matrix) for sub in _geometry(el, tag)]
    for window in clips:
        clipped: list[Subpath] = []
        for sub in subpaths:
            kept = _clip_subpath(sub, window)
            if kept is not None:
                clipped.append(kept)
        subpaths = clipped
    style = _style(el)
    stroke = _color(style.get("stroke", "none"))
    stroke_width = float(style.get("stroke-width", "1")) * scale_factor(matrix) if stroke else 0.0
    return Shape(
        name=el.get("id", ""),
        ancestors=ancestors,
        subpaths=subpaths,
        fill=_color(style.get("fill", "#000000")),
        evenodd=style.get("fill-rule", "nonzero") == "evenodd",
        stroke=stroke,
        stroke_width=stroke_width,
    )


def _clip_subpath(sub: Subpath, window: list[Point]) -> Subpath | None:
    points = flatten(sub)
    if all(inside_convex(p, window) for p in points):
        return sub
    if not sub.closed:
        raise ValueError("an open path crosses a clip-path, which the generator does not support")
    clipped = clip_convex(points, window)
    if len(clipped) < 3:
        return None
    return polygon_subpath(clipped)
