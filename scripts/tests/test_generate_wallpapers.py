"""Tests for scripts/generate/wallpapers.py.

Covers the six-gray role mapping, transform and clip baking, rejection of anything the generator
does not understand, deterministic Kotlin output, and the five real wallpaper SVGs.
"""

import contextlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "generate"))

import wallpapers  # noqa: E402
from svgart.svgdoc import parse_document  # noqa: E402

ASSETS = ROOT / "assets" / "wallpapers"
GRAYS = ("#000000", "#3E3B39", "#6D6A6A", "#9B9A9C", "#CAC9CD", "#FFFFFF")
CLIP_DEFS = '<defs><clipPath id="c"><rect x="0" y="0" width="50" height="50" /></clipPath></defs>'


def svg(body: str, view_box: str = "0 0 542.16 920.73") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="542.16" height="920.73" '
        f'viewBox="{view_box}">\n{body}\n</svg>\n'
    )


def rect(fill: str, x: float = 0, y: float = 0, w: float = 10, h: float = 10) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" style="fill:{fill};" />'


def path(d: str, fill: str = "#000000") -> str:
    return f'<path d="{d}" style="fill:{fill};" />'


def coords(d: str) -> list[tuple[float, float]]:
    """Every x,y pair in absolute path data, control points included."""
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(nums[0::2], nums[1::2]))


def convert(body: str) -> wallpapers.Artwork:
    return wallpapers.convert("test", svg(body))


class GrayRoleTest(unittest.TestCase):
    def test_six_grays_map_to_roles_zero_to_five(self):
        body = "\n".join(rect(gray, x=i * 20) for i, gray in enumerate(GRAYS))
        self.assertEqual([p.role for p in convert(body).pieces], [0, 1, 2, 3, 4, 5])

    def test_role_table_is_the_six_wallpaper_grays_in_order(self):
        self.assertEqual(wallpapers.ROLE_GRAYS, GRAYS)

    def test_hex_case_and_short_form_map_to_the_same_role(self):
        art = convert(rect("#9b9a9c") + rect("#fff", x=20))
        self.assertEqual([p.role for p in art.pieces], [3, 5])

    def test_shape_without_a_fill_is_black_as_in_svg(self):
        art = convert('<path d="M0 0 L5 0 L5 5 Z" />')
        self.assertEqual([p.role for p in art.pieces], [0])

    def test_gray_outside_the_table_fails_and_names_the_color(self):
        with self.assertRaisesRegex(wallpapers.WallpaperError, "#9B9A9D"):
            convert(rect("#9B9A9D"))

    def test_saturated_color_fails(self):
        with self.assertRaisesRegex(wallpapers.WallpaperError, "#FF0000"):
            convert(rect("#FF0000"))

    def test_fill_none_fails(self):
        with self.assertRaisesRegex(wallpapers.WallpaperError, "none"):
            convert(rect("none"))


class BakingTest(unittest.TestCase):
    def test_nested_group_and_path_transforms_are_applied_to_every_point(self):
        body = (
            '<g transform="translate(10 20)">'
            '<path transform="matrix(2,0,0,2,1,1)" d="M0 0 L1 0 L0 1 Z" style="fill:#000000;" />'
            "</g>"
        )
        # Z adds the closing edge back to the start point, as svgart's parser always does.
        self.assertEqual(convert(body).pieces[0].path, "M11,21L13,21L11,23L11,21Z")

    def test_rotation_is_baked_into_the_coordinates(self):
        body = '<path transform="rotate(90)" d="M10 0 L20 0 L20 5 Z" style="fill:#000000;" />'
        self.assertEqual(convert(body).pieces[0].path, "M0,10L0,20L-5,20L0,10Z")

    def test_root_translate_of_the_real_bloom_file_is_applied(self):
        art = wallpapers.convert("bloom", (ASSETS / "bloom.svg").read_text(encoding="utf-8"))
        # Path 34 starts at "M0 829.6 L0 214.32" in the source, under translate(-0 -79.635).
        start = coords(art.pieces[1].path)[0]
        self.assertAlmostEqual(start[0], 0.0, places=2)
        self.assertAlmostEqual(start[1], 829.6 - 79.635, places=2)

    def test_fill_rule_evenodd_is_kept_per_shape(self):
        body = '<path d="M0 0 L5 0 L5 5 Z" fill-rule="evenodd" style="fill:#000000;" />'
        self.assertTrue(convert(body).pieces[0].even_odd)
        self.assertFalse(convert(path("M0 0 L5 0 L5 5 Z")).pieces[0].even_odd)


class ClipTest(unittest.TestCase):
    def test_path_inside_its_clip_is_kept_unchanged(self):
        clipped = convert(CLIP_DEFS + '<g clip-path="url(#c)">' + path("M10 10 L20 10 L20 20 Z") + "</g>")
        plain = convert(path("M10 10 L20 10 L20 20 Z"))
        self.assertEqual(clipped.pieces[0].path, plain.pieces[0].path)

    def test_path_crossing_its_clip_is_cut_to_the_clip(self):
        art = convert(CLIP_DEFS + '<g clip-path="url(#c)">' + path("M0 0 L100 0 L100 100 L0 100 Z") + "</g>")
        points = coords(art.pieces[0].path)
        self.assertTrue(all(0 <= x <= 50 and 0 <= y <= 50 for x, y in points), points)
        self.assertIn((50.0, 50.0), points)

    def test_clip_follows_the_clipped_group_transform(self):
        square = path("M0 0 L10 0 L10 10 L0 10 Z")
        body = CLIP_DEFS + f'<g transform="translate(100 0)" clip-path="url(#c)">{square}</g>'
        points = coords(convert(body).pieces[0].path)
        self.assertEqual(min(x for x, _ in points), 100.0)
        self.assertEqual(max(x for x, _ in points), 110.0)

    def test_path_outside_its_clip_is_dropped(self):
        outside = path("M200 200 L210 200 L210 210 Z")
        body = CLIP_DEFS + f'<g clip-path="url(#c)">{outside}</g>' + rect("#000000", w=5, h=5)
        self.assertEqual(len(convert(body).pieces), 1)


class RejectionTest(unittest.TestCase):
    def assertRejected(self, body: str, pattern: str) -> None:
        with self.assertRaisesRegex(wallpapers.WallpaperError, pattern):
            convert(body)

    def test_unknown_element_fails(self):
        self.assertRejected('<circle cx="5" cy="5" r="5" style="fill:#000000;" />', "circle")

    def test_image_element_fails(self):
        self.assertRejected('<image href="x.png" width="5" height="5" />', "image")

    def test_ellipse_fails_because_the_wallpapers_do_not_use_it(self):
        self.assertRejected('<ellipse cx="5" cy="5" rx="5" ry="5" style="fill:#000000;" />', "ellipse")

    def test_stroke_fails(self):
        self.assertRejected('<path d="M0 0 L5 0 L5 5 Z" style="fill:#000000;stroke:#FFFFFF;" />', "stroke")

    def test_opacity_fails(self):
        self.assertRejected('<path d="M0 0 L5 0 L5 5 Z" style="fill:#000000;opacity:0.5;" />', "opacity")

    def test_gradient_fill_fails(self):
        self.assertRejected('<path d="M0 0 L5 0 L5 5 Z" style="fill:url(#g);" />', "url")

    def test_fill_on_a_group_fails_because_paint_is_not_inherited(self):
        self.assertRejected('<g style="fill:#9B9A9C;">' + path("M0 0 L5 0 L5 5 Z") + "</g>", "fill")

    def test_viewbox_other_than_542_by_920_fails(self):
        with self.assertRaisesRegex(wallpapers.WallpaperError, "viewBox"):
            wallpapers.convert("test", svg(rect("#000000"), view_box="0 0 100 100"))

    def test_wallpaper_with_no_visible_shape_fails(self):
        body = CLIP_DEFS + '<g clip-path="url(#c)">' + path("M200 200 L210 200 L210 210 Z") + "</g>"
        self.assertRejected(body, "no visible shapes")

    def test_malformed_svg_fails(self):
        with self.assertRaisesRegex(wallpapers.WallpaperError, "invalid"):
            wallpapers.convert("test", "<svg")


class KotlinOutputTest(unittest.TestCase):
    def artworks(self) -> list[wallpapers.Artwork]:
        return [
            wallpapers.Artwork(
                "bloom",
                (wallpapers.Piece(3, False, "M0,0L1,1Z"), wallpapers.Piece(5, True, "M2,2L3,3Z")),
            ),
            wallpapers.Artwork("grow", (wallpapers.Piece(0, False, "M4,4L5,5Z"),)),
        ]

    def test_render_declares_the_package_the_shape_and_each_wallpaper(self):
        text = wallpapers.render(self.artworks())
        self.assertIn("package org.mozilla.fenix.embermine.wallpapers\n", text)
        self.assertIn("internal class EmbermineWallpaperShape(", text)
        self.assertIn('name = "bloom"', text)
        self.assertIn('name = "grow"', text)
        self.assertIn("role = 5,", text)
        self.assertIn("evenOdd = true,", text)
        self.assertIn('path = "M2,2L3,3Z",', text)

    def test_viewbox_constants_are_written_as_floats(self):
        text = wallpapers.render(self.artworks())
        self.assertIn("const val VIEWBOX_WIDTH = 542.16f", text)
        self.assertIn("const val VIEWBOX_HEIGHT = 920.73f", text)

    def test_render_is_deterministic(self):
        self.assertEqual(wallpapers.render(self.artworks()), wallpapers.render(self.artworks()))

    def test_path_data_outside_the_kotlin_safe_alphabet_fails(self):
        with self.assertRaisesRegex(wallpapers.WallpaperError, "path data"):
            wallpapers.render([wallpapers.Artwork("bloom", (wallpapers.Piece(0, False, "M0,0 $x"),))])

    def test_string_over_the_jvm_constant_limit_fails(self):
        huge = "M0,0" + "L1,1" * 17000  # 68004 bytes, over the limit
        with self.assertRaisesRegex(wallpapers.WallpaperError, "65535"):
            wallpapers.render([wallpapers.Artwork("bloom", (wallpapers.Piece(0, False, huge),))])


class RealAssetsTest(unittest.TestCase):
    def test_all_five_wallpapers_convert_in_order_with_paths(self):
        arts = wallpapers.load_all(ASSETS)
        self.assertEqual([a.name for a in arts], ["bloom", "grow", "pattern", "rise", "triangle"])
        for art in arts:
            with self.subTest(wallpaper=art.name):
                self.assertGreater(len(art.pieces), 0)
                self.assertTrue({p.role for p in art.pieces} <= set(range(6)))

    def test_rise_uses_all_six_grays(self):
        art = wallpapers.convert("rise", (ASSETS / "rise.svg").read_text(encoding="utf-8"))
        self.assertEqual({p.role for p in art.pieces}, set(range(6)))

    def test_each_real_svg_has_the_542_by_920_viewbox(self):
        for name in wallpapers.WALLPAPERS:
            with self.subTest(wallpaper=name):
                doc = parse_document((ASSETS / f"{name}.svg").read_text(encoding="utf-8"))
                self.assertEqual((doc.width, doc.height), (542.16, 920.73))


class TreeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def fenix_tree(self, name: str) -> Path:
        tree = self.tmp / name
        (tree / wallpapers.FENIX_PACKAGE_DIR).mkdir(parents=True)
        return tree

    def assets_copy(self) -> Path:
        dest = self.tmp / "assets"
        dest.mkdir()
        for name in wallpapers.WALLPAPERS:
            shutil.copy(ASSETS / f"{name}.svg", dest / f"{name}.svg")
        return dest

    def test_two_runs_into_different_trees_write_identical_bytes(self):
        first = wallpapers.run(self.fenix_tree("a"), ASSETS)
        second = wallpapers.run(self.fenix_tree("b"), ASSETS)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_second_run_on_the_same_tree_writes_the_same_bytes(self):
        tree = self.fenix_tree("a")
        first = wallpapers.run(tree, ASSETS).read_bytes()
        self.assertEqual(wallpapers.run(tree, ASSETS).read_bytes(), first)

    def test_output_is_the_embermine_wallpaper_package_file(self):
        tree = self.fenix_tree("a")
        out = wallpapers.run(tree, ASSETS)
        self.assertEqual(out, tree / wallpapers.OUTPUT)
        self.assertEqual(out.name, "EmbermineWallpaperData.kt")
        self.assertIn("package org.mozilla.fenix.embermine.wallpapers\n", out.read_text(encoding="utf-8"))

    def test_run_rejects_a_directory_that_is_not_the_fenix_tree(self):
        with self.assertRaisesRegex(wallpapers.WallpaperError, "not a Firefox source tree"):
            wallpapers.run(self.tmp, ASSETS)

    def test_missing_wallpaper_fails_and_writes_nothing(self):
        assets = self.assets_copy()
        (assets / "grow.svg").unlink()
        tree = self.fenix_tree("a")
        with self.assertRaisesRegex(wallpapers.WallpaperError, "grow"):
            wallpapers.run(tree, assets)
        self.assertFalse((tree / wallpapers.OUTPUT).exists())

    def test_unlisted_svg_in_the_assets_fails(self):
        assets = self.assets_copy()
        (assets / "draft.svg").write_text(svg(rect("#000000")), encoding="utf-8")
        with self.assertRaisesRegex(wallpapers.WallpaperError, "draft"):
            wallpapers.run(self.fenix_tree("a"), assets)

    def test_bad_wallpaper_fails_and_writes_nothing(self):
        assets = self.assets_copy()
        (assets / "bloom.svg").write_text(svg(rect("#123456")), encoding="utf-8")
        tree = self.fenix_tree("a")
        with self.assertRaisesRegex(wallpapers.WallpaperError, "#123456"):
            wallpapers.run(tree, assets)
        self.assertFalse((tree / wallpapers.OUTPUT).exists())


class CommandLineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def fenix_tree(self) -> Path:
        tree = self.tmp / "fx"
        (tree / wallpapers.FENIX_PACKAGE_DIR).mkdir(parents=True)
        return tree

    def test_summary_lists_all_five_wallpapers_with_their_path_counts(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = wallpapers.main(["--tree", str(self.fenix_tree())])
        self.assertEqual(code, 0)
        for name in wallpapers.WALLPAPERS:
            self.assertRegex(out.getvalue(), rf"wallpaper {name}: \d+ paths")
        self.assertIn("wallpapers: wrote", out.getvalue())

    def test_bad_svg_exits_non_zero_with_an_error_message(self):
        assets = self.tmp / "assets"
        assets.mkdir()
        for name in wallpapers.WALLPAPERS:
            shutil.copy(ASSETS / f"{name}.svg", assets / f"{name}.svg")
        (assets / "pattern.svg").write_text(svg(rect("#123456")), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = wallpapers.main(["--tree", str(self.fenix_tree()), "--assets", str(assets)])
        self.assertEqual(code, 1)
        self.assertIn("error:", err.getvalue())
        self.assertIn("#123456", err.getvalue())

    def test_script_runs_the_way_run_generators_invokes_it(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate" / "wallpapers.py"), "--tree", str(self.fenix_tree())],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wallpapers: wrote", result.stdout)


if __name__ == "__main__":
    unittest.main()
