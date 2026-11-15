"""Write Android VectorDrawable XML from path pieces, with a fixed attribute order."""

from __future__ import annotations

from .geometry import format_number, path_data
from .layers import Piece

GENERATED_NOTE = "<!-- Generated from assets/icon/icon.svg by scripts/generate/icons.py. Do not edit. -->"


def vector_drawable(
    width: str,
    height: str,
    viewport: tuple[float, float],
    pieces: list[Piece],
) -> str:
    """A ``<vector>`` document with one ``<path>`` per piece, in piece order."""
    if not pieces:
        raise ValueError("a drawable needs at least one path")
    viewport_width, viewport_height = viewport
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        GENERATED_NOTE,
        '<vector xmlns:android="http://schemas.android.com/apk/res/android"',
        f'    android:width="{width}"',
        f'    android:height="{height}"',
        f'    android:viewportWidth="{format_number(viewport_width)}"',
        f'    android:viewportHeight="{format_number(viewport_height)}">',
    ]
    for piece in pieces:
        if not piece.subpaths:
            raise ValueError("a path piece has no contours")
        data = path_data(piece.subpaths)
        # AAPT substitutes STRING_TOO_LARGE beyond this limit, producing an XML drawable
        # that builds successfully but cannot be inflated by Android (including launcher icons).
        if len(data.encode("utf-8")) > 0x7FFF:
            raise ValueError("pathData exceeds Android's 32,767-byte resource string limit; split the paint layers")
        lines.append("    <path")
        if piece.fill is not None:
            lines.append(f'        android:fillColor="{piece.fill}"')
        if piece.evenodd:
            lines.append('        android:fillType="evenOdd"')
        if piece.stroke is not None:
            lines.append(f'        android:strokeColor="{piece.stroke}"')
            lines.append(f'        android:strokeWidth="{format_number(piece.stroke_width)}"')
            lines.append('        android:strokeLineCap="round"')
            lines.append('        android:strokeLineJoin="round"')
        lines.append(f'        android:pathData="{data}" />')
    lines.append("</vector>")
    return "\n".join(lines) + "\n"
