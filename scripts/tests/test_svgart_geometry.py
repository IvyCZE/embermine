import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generate"))

from svgart import lottie  # noqa: E402
from svgart.geometry import (  # noqa: E402
    apply,
    bounds,
    control_points,
    flatten,
    format_number,
    parse_path,
    parse_transform,
    path_data,
    polygon_subpath,
    signed_area,
    stroke_polygon,
)
from svgart.regions import offset_closed, subtract_polygon, winding_number, without_repeats  # noqa: E402
from svgart.layers import Piece  # noqa: E402
from svgart.svgdoc import parse_document  # noqa: E402

SQUARE = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]


def _filled(loops, point):
    """Nonzero fill of signed loops: the sum of their windings is nonzero inside the region."""
    return sum(winding_number(point, loop) for loop in loops) != 0


class SubtractPolygonTest(unittest.TestCase):
    def test_disjoint_clip_leaves_subject_unchanged(self):
        loops = subtract_polygon(SQUARE, [(10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0)])
        self.assertEqual(len(loops), 1)
        self.assertAlmostEqual(signed_area(loops[0]), 16.0)

    def test_clip_inside_subject_leaves_a_clockwise_hole(self):
        clip = [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)]
        loops = subtract_polygon(SQUARE, clip)
        areas = sorted(signed_area(loop) for loop in loops)
        self.assertEqual(len(areas), 2)
        self.assertAlmostEqual(areas[0], -1.0)
        self.assertAlmostEqual(areas[1], 16.0)

    def test_subject_inside_clip_is_removed(self):
        clip = [(-1.0, -1.0), (5.0, -1.0), (5.0, 5.0), (-1.0, 5.0)]
        self.assertEqual(subtract_polygon([(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)], clip), [])

    def test_crossing_clip_gives_an_l_shape(self):
        clip = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
        loops = subtract_polygon([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)], clip)
        self.assertEqual(len(loops), 1)
        self.assertAlmostEqual(signed_area(loops[0]), 3.0)
        self.assertTrue(_filled(loops, (0.5, 0.5)))
        self.assertTrue(_filled(loops, (1.5, 0.5)))
        self.assertTrue(_filled(loops, (0.5, 1.5)))
        self.assertFalse(_filled(loops, (1.5, 1.5)))

    def test_orientation_of_the_inputs_does_not_matter(self):
        clip = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
        clockwise = list(reversed([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]))
        loops = subtract_polygon(clockwise, list(reversed(clip)))
        self.assertAlmostEqual(sum(signed_area(loop) for loop in loops), 3.0)

    def test_difference_matches_point_membership(self):
        subject = [(0.0, 0.0), (6.0, 1.0), (5.0, 6.0), (0.5, 4.0)]
        clip = [(2.0, -1.0), (4.0, 2.0), (3.0, 7.0), (-1.0, 3.0)]
        loops = subtract_polygon(subject, clip)
        for x in range(-2, 9):
            for y in range(-2, 9):
                point = (x + 0.37, y + 0.21)
                expected = winding_number(point, subject) != 0 and winding_number(point, clip) == 0
                self.assertEqual(_filled(loops, point), expected, point)


class WithoutRepeatsTest(unittest.TestCase):
    def test_drops_consecutive_and_closing_duplicates(self):
        points = [(0.0, 0.0), (0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
        self.assertEqual(without_repeats(points), [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])


class PathAndTransformTest(unittest.TestCase):
    def test_relative_and_absolute_commands_parse_to_the_same_box(self):
        subpaths = parse_path("M0 0 h10 v10 H0 z")
        self.assertEqual(len(subpaths), 1)
        self.assertTrue(subpaths[0].closed)
        self.assertEqual(bounds(flatten(subpaths[0])), (0.0, 0.0, 10.0, 10.0))

    def test_path_data_round_trips_through_parse_path(self):
        square = polygon_subpath([(0.5, 0.25), (3.0, 0.25), (3.0, 2.0)])
        again = parse_path(path_data([square]))
        self.assertEqual(len(again), 1)
        self.assertEqual(sorted(flatten(again[0])), sorted(flatten(square)))

    def test_transforms(self):
        self.assertEqual(apply(parse_transform("translate(2 3)"), 1.0, 1.0), (3.0, 4.0))
        self.assertEqual(apply(parse_transform("matrix(2 0 0 2 5 6)"), 1.0, 1.0), (7.0, 8.0))
        self.assertEqual(apply(parse_transform(None), 1.0, 2.0), (1.0, 2.0))

    def test_format_number_trims_and_avoids_negative_zero(self):
        self.assertEqual(format_number(1.5000), "1.5")
        self.assertEqual(format_number(2.0), "2")
        self.assertEqual(format_number(-0.0001), "0")


class OffsetAndStrokeTest(unittest.TestCase):
    def test_offset_grows_a_square_by_its_distance_on_every_side(self):
        grown = offset_closed(SQUARE, 0.5)
        self.assertEqual(len(grown), 4)
        x0, y0, x1, y1 = bounds(grown)
        self.assertAlmostEqual(x0, -0.5)
        self.assertAlmostEqual(y0, -0.5)
        self.assertAlmostEqual(x1, 4.5)
        self.assertAlmostEqual(y1, 4.5)

    def test_round_caps_extend_a_stroke_by_its_half_width(self):
        outline = stroke_polygon([(0.0, 0.0), (4.0, 0.0)], 1.0)
        x0, y0, x1, y1 = bounds(outline)
        self.assertAlmostEqual(x0, -1.0, places=6)
        self.assertAlmostEqual(x1, 5.0, places=6)
        self.assertAlmostEqual(y0, -1.0, places=6)
        self.assertAlmostEqual(y1, 1.0, places=6)
        self.assertTrue(all(math.hypot(x - 4.0, y) <= 1.0 + 1e-6 for x, y in outline if x > 4.0))

    def test_stroke_of_zero_width_is_empty(self):
        self.assertEqual(stroke_polygon([(0.0, 0.0), (4.0, 0.0)], 0.0), [])


class WindingTest(unittest.TestCase):
    def test_counter_clockwise_is_positive_inside(self):
        self.assertEqual(winding_number((2.0, 2.0), SQUARE), 1)
        self.assertEqual(winding_number((2.0, 2.0), list(reversed(SQUARE))), -1)
        self.assertEqual(winding_number((9.0, 2.0), SQUARE), 0)

    def test_control_points_bound_a_cubic(self):
        sub = parse_path("M0,0C0,10 10,10 10,0Z")[0]
        self.assertIn((0.0, 10.0), control_points(sub))


class SvgDocumentTest(unittest.TestCase):
    def test_rejects_elements_the_generator_cannot_draw(self):
        text = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
            '<circle cx="1" cy="1" r="1" fill="#000000"/></svg>'
        )
        with self.assertRaises(ValueError):
            parse_document(text)


class LottieTest(unittest.TestCase):
    def test_animation_is_json_with_the_requested_frame_size(self):
        square = Piece([polygon_subpath(SQUARE)], fill="#FFB561")
        data = json.loads(lottie.animation([square], 144, 80))
        self.assertEqual((data["w"], data["h"]), (144, 80))
        self.assertGreater(len(data["layers"]), 0)


if __name__ == "__main__":
    unittest.main()
