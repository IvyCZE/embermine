"""A static Lottie document that draws path pieces, used in place of Kit's tab-group animation."""

from __future__ import annotations

import json

from .geometry import Point, flatten
from .layers import Piece

FRAME_RATE = 10
FRAME_COUNT = 40


def _rgba(color: str) -> list[float]:
    if len(color) != 7 or not color.startswith("#"):
        raise ValueError(f"Lottie colours must be #RRGGBB, got {color!r}")
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return [round(c, 4) for c in channels] + [1]


def _static(value: object) -> dict[str, object]:
    return {"a": 0, "k": value}


def _outline(piece: Piece) -> list[dict[str, object]]:
    """Each contour as a polyline shape (zero tangents), closed when the contour is."""
    shapes: list[dict[str, object]] = []
    for sub in piece.subpaths:
        points: list[Point] = [(round(x, 3), round(y, 3)) for x, y in flatten(sub)]
        if sub.closed and len(points) > 1 and points[0] == points[-1]:
            points.pop()
        vertices = [[x, y] for x, y in points]
        zeros = [[0, 0] for _ in points]
        shapes.append(
            {
                "ty": "sh",
                "ks": _static({"i": zeros, "o": zeros, "v": vertices, "c": sub.closed}),
            }
        )
    return shapes


def _group(piece: Piece) -> dict[str, object]:
    items: list[dict[str, object]] = _outline(piece)
    if piece.fill is not None:
        items.append(
            {
                "ty": "fl",
                "c": _static(_rgba(piece.fill)),
                "o": _static(100),
                "r": 2 if piece.evenodd else 1,
            }
        )
    if piece.stroke is not None:
        items.append(
            {
                "ty": "st",
                "c": _static(_rgba(piece.stroke)),
                "o": _static(100),
                "w": _static(round(piece.stroke_width, 3)),
                "lc": 2,
                "lj": 2,
            }
        )
    items.append(
        {
            "ty": "tr",
            "p": _static([0, 0]),
            "a": _static([0, 0]),
            "s": _static([100, 100]),
            "r": _static(0),
            "o": _static(100),
        }
    )
    return {"ty": "gr", "it": items}


def animation(pieces: list[Piece], width: float, height: float) -> str:
    """A still Lottie document (no keyframes) showing ``pieces`` in a ``width`` x ``height`` box."""
    if not pieces:
        raise ValueError("a Lottie animation needs at least one piece")
    layer = {
        "ddd": 0,
        "ind": 1,
        "ty": 4,
        "nm": "embermine",
        "sr": 1,
        "ks": {
            "o": _static(100),
            "r": _static(0),
            "p": _static([0, 0, 0]),
            "a": _static([0, 0, 0]),
            "s": _static([100, 100, 100]),
        },
        "ao": 0,
        "shapes": [_group(piece) for piece in pieces],
        "ip": 0,
        "op": FRAME_COUNT,
        "st": 0,
        "bm": 0,
    }
    document = {
        "v": "5.7.0",
        "fr": FRAME_RATE,
        "ip": 0,
        "op": FRAME_COUNT,
        "w": int(width),
        "h": int(height),
        "nm": "embermine",
        "ddd": 0,
        "assets": [],
        "layers": [layer],
    }
    return json.dumps(document, separators=(",", ":")) + "\n"
