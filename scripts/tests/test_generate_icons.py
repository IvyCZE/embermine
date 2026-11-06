import contextlib
import io
import json
import math
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "generate"))

import icons  # noqa: E402
from svgart.geometry import apply, bounds, flatten, parse_path  # noqa: E402
from svgart.regions import winding_number  # noqa: E402
from svgart.layers import (  # noqa: E402
    art_bounds,
    art_from_document,
    fit_matrix,
    load_icon,
    safe_zone_box,
)
from svgart.svgdoc import parse_document  # noqa: E402

ICON = ROOT / "assets" / "icon" / "icon.svg"
ANDROID = "{http://schemas.android.com/apk/res/android}"
SOURCE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
    '    android:width="24dp" android:height="24dp"\n'
    '    android:viewportWidth="24" android:viewportHeight="24">\n'
    '    <path android:fillColor="#000000" android:pathData="M0,0h24v24H0z" />\n'
    "</vector>\n"
)
# Eye, ear and body points of icon.svg, in icon canvas units (830.6 square).
EYE = (237.07, 438.87)
EAR = (323.0, 218.0)
FLOWER = (413.0, 368.0)
BODY = (300.0, 600.0)


def _fake_tree(root: Path) -> Path:
    """A tree with every source file the generator reads, each one a 24 dp placeholder."""
    (root / icons.MAIN).mkdir(parents=True)
    for target in icons.TARGETS:
        if target.src:
            path = root / target.src
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(SOURCE, encoding="utf-8")
    return root


def _pieces(xml_text: str) -> list[tuple[dict[str, str], list]]:
    """Each path of a generated drawable as (attributes, flattened loops in viewport units)."""
    root = ET.fromstring(xml_text)
    out = []
    for path in root.findall("path"):
        loops = [flatten(sub) for sub in parse_path(path.get(ANDROID + "pathData"))]
        out.append((dict(path.attrib), loops))
    return out


def _filled(loops, point) -> bool:
    return sum(winding_number(point, loop) for loop in loops) != 0


class IconLayerTest(unittest.TestCase):
    def setUp(self):
        self.art = load_icon(ICON)

    def test_layers_are_read_from_icon_svg(self):
        self.assertEqual(self.art.size, 830.6)
        self.assertEqual(self.art.background, "#471B18")
        self.assertEqual(self.art.sunny.fill, "#823C35")
        self.assertEqual(self.art.flower.fill, "#FFB561")
        self.assertEqual(len(self.art.ermine), 12)

    def test_art_bounds_cover_flower_and_ermine_only(self):
        x0, y0, x1, y1 = art_bounds(self.art)
        self.assertLess(x0, 100)
        self.assertGreater(x1, 680)
        self.assertLess(y0, 160)
        self.assertGreater(y1, 675)

    def test_document_without_background_is_rejected(self):
        text = ICON.read_text(encoding="utf-8").replace('id="Ellipse 5"', 'id="Ellipse 9"')
        with self.assertRaises(ValueError):
            art_from_document(parse_document(text))

    def test_non_square_canvas_is_rejected(self):
        text = ICON.read_text(encoding="utf-8").replace('viewBox="0 0 830.6 830.6"', 'viewBox="0 0 830.6 800"')
        with self.assertRaises(ValueError):
            art_from_document(parse_document(text))


class OutputTest(unittest.TestCase):
    """Generated drawables from the real icon.svg, written against a fake source tree."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tree = _fake_tree(Path(cls._tmp.name))
        cls.art = load_icon(ICON)
        cls.outputs = icons.build_outputs(cls.art, cls.tree)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _output(self, suffix: str) -> str:
        matches = [text for rel, text in self.outputs.items() if rel.endswith(suffix)]
        self.assertEqual(len(matches), 1, suffix)
        return matches[0]

    def test_every_target_is_written(self):
        self.assertEqual(len(self.outputs), len(icons.TARGETS))

    def test_nova_onboarding_illustrations_with_the_fox_are_replaced(self):
        # The first onboarding page (Terms of Use) and the sync, notification, widget and
        # marketing pages draw the Kit fox; the toolbar mock-ups and background do not.
        for name in ("tou", "tou_2", "sync", "sync_qr", "notifications", "widget", "marketing"):
            self._output(f"drawable/nova_onboarding_{name}.xml")
        for name in ("toolbar_top_active", "toolbar_bottom_inactive", "background", "set_to_default"):
            self.assertFalse(any(rel.endswith(f"nova_onboarding_{name}.xml") for rel in self.outputs), name)

    def test_xml_outputs_parse_and_json_outputs_load(self):
        for rel, text in self.outputs.items():
            if rel.endswith(".json"):
                json.loads(text)
            else:
                root = ET.fromstring(text)
                self.assertEqual(root.tag, "vector", rel)

    def test_outputs_are_deterministic(self):
        again = icons.build_outputs(self.art, self.tree)
        self.assertEqual(again, self.outputs)

    def test_background_is_full_bleed_with_sunny_on_top(self):
        pieces = _pieces(self._output("embermine_launcher_background.xml"))
        self.assertEqual(len(pieces), 2)
        (rect_attrs, rect_loops), (sunny_attrs, _) = pieces
        self.assertEqual(rect_attrs[ANDROID + "fillColor"], "#471B18")
        self.assertEqual(sunny_attrs[ANDROID + "fillColor"], "#823C35")
        self.assertEqual(bounds(rect_loops[0]), (0.0, 0.0, 108.0, 108.0))

    def test_launcher_art_stays_inside_the_safe_zone_circle(self):
        # Google's adaptive icon safe zone is a 66 dp circle centred on the 108 dp canvas.
        for suffix in ("ic_launcher_foreground.xml", "ic_launcher_monochrome.xml"):
            for _, loops in _pieces(self._output(suffix)):
                for loop in loops:
                    for x, y in loop:
                        self.assertLessEqual(math.hypot(x - 54.0, y - 54.0), 33.0, suffix)

    def test_launcher_art_keeps_the_palette_and_outlines(self):
        pieces = _pieces(self._output("ic_launcher_foreground.xml"))
        fills = {attrs.get(ANDROID + "fillColor") for attrs, _ in pieces}
        self.assertIn("#FFB561", fills)
        self.assertIn("#F5EBE0", fills)
        self.assertTrue(any(attrs.get(ANDROID + "strokeColor") == "#000000" for attrs, _ in pieces))

    def test_monochrome_is_one_solid_colour_with_cut_outs(self):
        text = self._output("ic_launcher_monochrome.xml")
        pieces = _pieces(text)
        self.assertEqual(len(pieces), 1)
        attrs, loops = pieces[0]
        self.assertEqual(attrs[ANDROID + "fillColor"], "#000000")
        self.assertNotIn(ANDROID + "strokeColor", attrs)
        matrix = fit_matrix(art_bounds(self.art), safe_zone_box(108.0, 108.0))
        self.assertTrue(_filled(loops, apply(matrix, *FLOWER)))
        self.assertTrue(_filled(loops, apply(matrix, *BODY)))
        for cut in (EYE, EAR):
            self.assertFalse(_filled(loops, apply(matrix, *cut)), cut)

    def test_status_and_splash_icons_take_their_size_from_the_source(self):
        self.assertIn('android:width="24dp"', self._output("ic_status_logo.xml"))
        self.assertIn('android:fillColor="#FFFFFF"', self._output("ic_status_logo.xml"))
        self.assertIn('android:width="24dp"', self._output("ic_splash_logo.xml"))

    def test_wordmarks_use_their_own_colours(self):
        self.assertIn('android:fillColor="#15141A"', self._output("ic_wordmark_text_normal.xml"))
        self.assertIn('android:fillColor="#FFFFFF"', self._output("ic_wordmark_text_private.xml"))
        self.assertIn('android:fillColor="#15141A"', self._output("drawable-xxhdpi/ic_logo_wordmark_normal.xml"))

    def test_android_components_override_keeps_the_theme_colour_reference(self):
        text = self._output("mozac_ic_logo_firefox_24.xml")
        self.assertIn('android:fillColor="@color/mozac_ui_icons_fill"', text)
        self.assertIn("<path", text)

    def test_animation_has_the_source_frame_size(self):
        data = json.loads(self._output("mozac_ic_kit_tab_groups_animation.json"))
        self.assertEqual((data["w"], data["h"]), (144, 80))


class IconChangeTest(unittest.TestCase):
    def test_changing_icon_svg_changes_the_generated_output_without_code_edits(self):
        text = ICON.read_text(encoding="utf-8").replace("#471B18", "#102030")
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "icon.svg"
            icon.write_text(text, encoding="utf-8")
            tree = _fake_tree(Path(tmp) / "tree")
            outputs = icons.build_outputs(load_icon(icon), tree)
        background = next(v for k, v in outputs.items() if k.endswith("embermine_launcher_background.xml"))
        self.assertIn('android:fillColor="#102030"', background)
        self.assertNotIn("#471B18", background)


class RunTest(unittest.TestCase):
    def test_run_writes_every_target_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = _fake_tree(Path(tmp) / "tree")
            with contextlib.redirect_stdout(io.StringIO()):
                first = icons.run(tree, ICON)
            snapshot = {rel: (tree / rel).read_bytes() for rel in first}
            with contextlib.redirect_stdout(io.StringIO()):
                second = icons.run(tree, ICON)
            self.assertEqual(first, second)
            self.assertEqual(len(first), len(icons.TARGETS))
            self.assertEqual({rel: (tree / rel).read_bytes() for rel in second}, snapshot)

    def test_run_refuses_a_directory_that_is_not_a_firefox_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                icons.run(Path(tmp), ICON)

    def test_run_names_a_missing_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = _fake_tree(Path(tmp) / "tree")
            (tree / next(t.src for t in icons.TARGETS if t.src)).unlink()
            with self.assertRaises(SystemExit) as raised:
                with contextlib.redirect_stdout(io.StringIO()):
                    icons.run(tree, ICON)
            self.assertIn("not found", str(raised.exception))

    def test_main_takes_tree_and_icon_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = _fake_tree(Path(tmp) / "tree")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(icons.main(["--tree", str(tree), "--icon", str(ICON)]), 0)
            self.assertTrue((tree / icons.RELEASE / "drawable" / "ic_launcher_monochrome.xml").is_file())


if __name__ == "__main__":
    unittest.main()
