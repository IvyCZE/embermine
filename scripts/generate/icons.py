#!/usr/bin/env python3
"""Generate Embermine's icon and artwork resources from assets/icon/icon.svg.

Writes into the release source set of a patched Firefox tree: the adaptive launcher (background,
foreground and monochrome), the splash and notification icons, the in-app logo and wordmark,
the Android Components logo override, and an ermine drawing for every Kit fox drawable it replaces
(same names, same sizes). Only icon.svg and the Firefox drawable sizes are read, so the output is
deterministic. Changing icon.svg needs no patch edit.

    usage: icons.py --tree <patched Firefox tree> [--icon <path to icon.svg>]
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from svgart import lottie
from svgart.layers import (
    Box,
    IconArt,
    Piece,
    art_bounds,
    background_pieces,
    canvas_matrix,
    color_pieces,
    fit_matrix,
    load_icon,
    margin_box,
    monochrome_pieces,
)
from svgart.vectordrawable import vector_drawable
from svgart.wordmark import WORDMARK_TEXT, wordmark_pieces

ICON_REL = "assets/icon/icon.svg"
APP_SRC = "mobile/android/fenix/app/src"
RELEASE = f"{APP_SRC}/release/res"
MAIN = f"{APP_SRC}/main/res"
AC_ICONS = "mobile/android/android-components/components/ui/icons/src/main/res/drawable"
AC_LLM = "mobile/android/android-components/components/lib/llm-mlpa/src/main/res/drawable"
AC_PROTECTION = (
    "mobile/android/android-components/components/feature/protection-dashboard/src/main/res/drawable"
)
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
MONOCHROME_FILL = "#000000"
WORDMARK_NORMAL = "#15141A"
WORDMARK_PRIVATE = "#FFFFFF"
ADAPTIVE_SIZE = ("108dp", "108dp", 108.0, 108.0)
LOCKUP_SIZE = ("424dp", "80dp", 424.0, 80.0)
LOCKUP_LOGO_BOX: Box = (2.0, 2.0, 78.0, 78.0)
LOCKUP_TEXT_BOX: Box = (100.0, 16.0, 424.0, 64.0)
ANIMATION_SIZE = (144, 80)
DENSITIES = ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")

# Kit fox drawables in main/res/drawable that Embermine replaces with the ermine drawing.
KIT_DRAWABLES = (
    "kit_head_protection_blocker_banner",
    "protection_panel_not_secure",
    "protection_panel_not_protected",
    "ic_onboarding_bottom_toolbar",
    "ic_onboarding_customize_toolbar",
    "ic_onboarding_key_features",
    "ic_onboarding_key_features_icons_only",
    "ic_onboarding_search_widget",
    "ic_onboarding_sync",
    "ic_onboarding_top_toolbar",
    "ic_onboarding_welcome",
    "nova_onboarding_marketing",
    "nova_onboarding_notifications",
    "nova_onboarding_sync",
    "nova_onboarding_sync_qr",
    "nova_onboarding_tou",
    "nova_onboarding_tou_2",
    "nova_onboarding_widget",
    "ic_kit_heart",
    "ic_kit_bookmarks_empty_state",
    "ic_kit_plug_error",
    "ic_kit_shield_on_state",
    "ic_kit_shield_off_state",
    "kit_devices_sync",
    "kit_devices_sync_error",
    "kit_plug_error",
    "kit_search_error",
    "kit_expressive_full",
    "mozac_ic_kit_tab_groups",
    "mozac_ic_kit_tab_groups_list_view",
    "illustration_fox_box_inside_light",
    "fox_ai_on_state",
    "fox_exclamation_alert",
    "expressive_firefox",
    "ic_firefox",
)


@dataclass(frozen=True)
class Target:
    """One generated file. ``kind`` picks the artwork; sizes come from ``size`` or from ``src``."""

    out: str
    kind: str
    src: str | None = None
    size: tuple[str, str, float, float] | None = None
    fill: str | None = None


def _art(name: str) -> Target:
    return Target(f"{RELEASE}/drawable/{name}.xml", "art", src=f"{MAIN}/drawable/{name}.xml")


TARGETS: tuple[Target, ...] = (
    Target(f"{RELEASE}/drawable/embermine_launcher_background.xml", "background", size=ADAPTIVE_SIZE),
    Target(f"{RELEASE}/drawable/ic_launcher_foreground.xml", "launcher", size=ADAPTIVE_SIZE),
    Target(f"{RELEASE}/drawable/ic_launcher_monochrome.xml", "launcher-mono", size=ADAPTIVE_SIZE),
    Target(
        f"{RELEASE}/drawable/ic_splash_logo.xml",
        "launcher",
        src=f"{MAIN}/drawable/ic_splash_logo.xml",
    ),
    Target(
        f"{RELEASE}/drawable/ic_status_logo.xml",
        "mono",
        src=f"{MAIN}/drawable/ic_status_logo.xml",
        fill="#FFFFFF",
    ),
    *(_art(name) for name in KIT_DRAWABLES),
    Target(
        f"{RELEASE}/drawable-nodpi/firefox_as_default_banner_illustration.xml",
        "art",
        src=f"{MAIN}/drawable-nodpi/firefox_as_default_banner_illustration.xml",
    ),
    Target(
        f"{RELEASE}/drawable-nodpi/kit_sleeping_under_laptop.xml",
        "art",
        size=("180dp", "103dp", 180.0, 103.0),
    ),
    Target(f"{RELEASE}/drawable-nodpi/ic_wordmark_logo.xml", "art", size=("160dp", "160dp", 160.0, 160.0)),
    Target(
        f"{RELEASE}/drawable-nodpi/ic_wordmark_text_normal.xml",
        "wordmark",
        src=f"{MAIN}/drawable-nodpi/ic_wordmark_text_normal.xml",
        fill=WORDMARK_NORMAL,
    ),
    Target(
        f"{RELEASE}/drawable-nodpi/ic_wordmark_text_private.xml",
        "wordmark",
        src=f"{MAIN}/drawable-nodpi/ic_wordmark_text_private.xml",
        fill=WORDMARK_PRIVATE,
    ),
    *(
        Target(f"{RELEASE}/drawable-{d}/ic_logo_wordmark_{mode}.xml", "lockup", size=LOCKUP_SIZE, fill=fill)
        for d in DENSITIES
        for mode, fill in (("normal", WORDMARK_NORMAL), ("private", WORDMARK_PRIVATE))
    ),
    Target(f"{RELEASE}/raw/mozac_ic_kit_tab_groups_animation.json", "lottie"),
    Target(
        f"{APP_SRC}/release/res/drawable/mozac_ic_logo_firefox_24.xml",
        "mono",
        src=f"{AC_ICONS}/mozac_ic_logo_firefox_24.xml",
        fill="@color/mozac_ui_icons_fill",
    ),
    Target(f"{RELEASE}/drawable/firefox_icon.xml", "art", src=f"{AC_LLM}/firefox_icon.xml"),
    Target(
        f"{RELEASE}/drawable/firefox_pictorgram_shield_check_rgb_2.xml",
        "art",
        src=f"{AC_PROTECTION}/firefox_pictorgram_shield_check_rgb_2.xml",
    ),
)


def _number(text: str) -> float:
    return float(text.removesuffix("dp"))


def _dimensions(target: Target, tree: Path) -> tuple[str, str, float, float]:
    """Width and height strings plus viewport size: explicit, or copied from the source XML."""
    if target.size is not None:
        return target.size
    if target.src is None:
        raise SystemExit(f"error: {target.out} has neither a size nor a source")
    path = tree / target.src
    if not path.is_file():
        raise SystemExit(f"error: {path} not found; this Firefox tree does not match the generator")
    root = ET.parse(path).getroot()
    width = root.get(f"{ANDROID_NS}width")
    height = root.get(f"{ANDROID_NS}height")
    if width is None or height is None:
        raise SystemExit(f"error: {path} has no android:width or android:height")
    viewport_width = float(root.get(f"{ANDROID_NS}viewportWidth", _number(width)))
    viewport_height = float(root.get(f"{ANDROID_NS}viewportHeight", _number(height)))
    return width, height, viewport_width, viewport_height


def _render(target: Target, art: IconArt, tree: Path) -> str:
    bounds = art_bounds(art)
    if target.kind == "lottie":
        width, height = ANIMATION_SIZE
        pieces = color_pieces(art, fit_matrix(bounds, margin_box(width, height)))
        return lottie.animation(pieces, width, height)

    width, height, vw, vh = _dimensions(target, tree)
    fill = target.fill or MONOCHROME_FILL
    if target.kind == "background":
        pieces: list[Piece] = background_pieces(art, canvas_matrix(art, vw, vh), vw, vh)
    elif target.kind == "launcher":
        pieces = color_pieces(art, canvas_matrix(art, vw, vh))
    elif target.kind == "launcher-mono":
        pieces = monochrome_pieces(art, canvas_matrix(art, vw, vh), fill)
    elif target.kind == "art":
        pieces = color_pieces(art, fit_matrix(bounds, margin_box(vw, vh)))
    elif target.kind == "mono":
        pieces = monochrome_pieces(art, fit_matrix(bounds, margin_box(vw, vh)), fill)
    elif target.kind == "wordmark":
        pieces = wordmark_pieces(WORDMARK_TEXT, margin_box(vw, vh), fill)
    elif target.kind == "lockup":
        logo = color_pieces(art, fit_matrix(bounds, LOCKUP_LOGO_BOX))
        pieces = logo + wordmark_pieces(WORDMARK_TEXT, LOCKUP_TEXT_BOX, fill)
    else:
        raise SystemExit(f"error: unknown artwork kind {target.kind!r}")
    return vector_drawable(width, height, (vw, vh), pieces)


def build_outputs(art: IconArt, tree: Path) -> dict[str, str]:
    """Every generated file as {tree-relative path: content}, in a fixed order."""
    return {target.out: _render(target, art, tree) for target in TARGETS}


def run(tree: Path, icon: Path) -> list[str]:
    if not (tree / MAIN).is_dir():
        raise SystemExit(f"error: {tree} is not a Firefox source tree (no {MAIN})")
    try:
        art = load_icon(icon)
    except ValueError as exc:
        raise SystemExit(f"error: {icon}: {exc}") from exc
    outputs = build_outputs(art, tree)
    for rel, content in outputs.items():
        path = tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote {rel}")
    print(f"icons: wrote {len(outputs)} files from {icon.name}")
    return list(outputs)


def main(argv: list[str] | None = None) -> int:
    default_icon = Path(__file__).resolve().parents[2] / ICON_REL
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", required=True, type=Path, help="patched Firefox source tree")
    parser.add_argument("--icon", type=Path, default=default_icon, help="icon.svg to read")
    args = parser.parse_args(argv)
    run(args.tree.resolve(), args.icon.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
