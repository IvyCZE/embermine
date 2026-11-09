import re
import unittest

from scripts.emulator import devsetup, flows_wallpaper, run

EMBERMINE_WALLPAPERS = ("bloom", "grow", "pattern", "rise", "triangle")


class WallpaperFlowWiringTests(unittest.TestCase):
    def flow(self, name: str, variant: str = "light", accent: str = "on") -> run.Flow:
        return next(f for f in run.flow_list(variant, accent) if f.name == name)

    def test_picked_wallpaper_flow_runs_in_both_accent_passes_and_not_in_legacy(self) -> None:
        self.assertTrue(self.flow("wallpaper selection", accent="on").expected)
        self.assertTrue(self.flow("wallpaper selection", accent="off").expected)
        self.assertNotIn("wallpaper selection", {f.name for f in run.legacy_flow_list()})

    def test_picked_wallpaper_captures_show_the_pick_and_the_restart(self) -> None:
        stems = [stem for stem, _, _ in self.flow("wallpaper selection").expected]
        self.assertEqual(stems, ["wallpaper-select-triangle", "homepage-wallpaper-triangle", "04-homepage-after-restart"])

    def test_picked_wallpaper_is_one_of_the_embermine_wallpapers(self) -> None:
        self.assertIn(flows_wallpaper.PICKED_WALLPAPER, EMBERMINE_WALLPAPERS)

    def test_switch_captures_have_homepage_and_picker_for_each_switch_change(self) -> None:
        states = {stem: on for stem, on, _ in flows_wallpaper.TOGGLE_CAPTURES}
        self.assertEqual(states["homepage-after-toggle-off"], False)
        self.assertEqual(states["wallpaper-picker-after-toggle-off"], False)
        self.assertEqual(states["homepage-after-toggle-on"], True)
        self.assertEqual(states["wallpaper-picker-after-toggle-on"], True)
        self.assertEqual(states["homepage-after-restart-off"], False)
        self.assertEqual(states["homepage-after-restart-on"], True)

    def test_palette_change_homepage_is_captured_in_the_dynamic_on_pass(self) -> None:
        states = {stem: on for stem, on, _ in flows_wallpaper.TOGGLE_CAPTURES}
        self.assertIs(states["04-homepage-after-palette-change"], True)
        toggle = {stem for stem, _, _ in self.flow("wallpaper colors toggle").expected}
        self.assertIn("04-homepage-after-palette-change", toggle)
        with self.assertRaises(StopIteration):
            self.flow("wallpaper colors toggle", accent="off")

    def test_changed_palette_is_green_like_the_default_seed_but_not_the_same(self) -> None:
        self.assertNotEqual(flows_wallpaper.CHANGED_PALETTE_SEED, devsetup.GREEN_SEED)
        self.assertTrue(devsetup.is_greenish("ff" + devsetup.GREEN_SEED))
        self.assertTrue(devsetup.is_greenish("ff" + flows_wallpaper.CHANGED_PALETTE_SEED))

    def test_thumbnail_selector_matches_the_picker_content_description(self) -> None:
        pattern = flows_wallpaper.thumbnail("triangle").desc
        self.assertIsNotNone(re.fullmatch(pattern, "Wallpaper Item: triangle", re.IGNORECASE))
        self.assertIsNone(re.fullmatch(pattern, "Wallpaper Item: bloom", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
