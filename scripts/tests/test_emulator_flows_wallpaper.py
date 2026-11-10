import contextlib
import re
import unittest
from collections.abc import Iterator
from types import SimpleNamespace
from unittest import mock

from scripts.emulator import devsetup, flows_settings, flows_wallpaper, run
from scripts.emulator.device import StepError

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

    def test_recent_tab_card_flow_runs_in_both_accent_passes_and_not_in_legacy(self) -> None:
        for accent in ("on", "off"):
            with self.subTest(accent=accent):
                stems = [stem for stem, _, _ in self.flow("recent tab card", accent=accent).expected]
                self.assertEqual(stems, ["homepage-recent-tab"])
        self.assertNotIn("recent tab card", {f.name for f in run.legacy_flow_list()})

    def test_recent_tab_card_capture_is_labelled_as_the_jump_back_in_card(self) -> None:
        stem, label = flows_wallpaper.RECENT_TAB_CAPTURE
        self.assertEqual(stem, "homepage-recent-tab")
        self.assertIn("Jump back in", label)
        expected = self.flow("recent tab card").expected
        self.assertEqual([(stem, label, False)], expected)

    def test_recent_tab_card_flow_comes_before_the_switch_toggle_flow(self) -> None:
        names = [f.name for f in run.flow_list()]
        self.assertLess(names.index("recent tab card"), names.index("wallpaper colors toggle"))

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


class RecentTabCardFlowTests(unittest.TestCase):
    def session(self, cards: list[object], calls: list[str]) -> SimpleNamespace:
        @contextlib.contextmanager
        def capture(stem: str, label: str | None = None) -> Iterator[SimpleNamespace]:
            yield SimpleNamespace(take=lambda settle=1.5, note="": None)

        def scroll_to(*args: object, **kwargs: object) -> object:
            if not cards:
                raise StepError("not found after scrolling")
            return cards.pop(0)

        return SimpleNamespace(
            capture=capture,
            dev=SimpleNamespace(sleep=lambda _: None, scroll_to=scroll_to),
            log=lambda _: None,
            force_stop=lambda: calls.append("force-stop"),
            launch_from_launcher=lambda: calls.append("relaunch"),
        )

    def test_the_section_is_turned_on_and_the_card_is_photographed(self) -> None:
        calls: list[str] = []
        s = self.session([object()], calls)
        with (
            mock.patch.object(flows_wallpaper, "go_home"),
            mock.patch.object(flows_settings, "set_homepage_recent_tabs") as enable,
        ):
            flows_wallpaper.recent_tab_homepage(s)
        enable.assert_called_once_with(s, True)
        self.assertEqual(calls, [])

    def test_a_missing_card_gets_one_relaunch_and_is_then_refused(self) -> None:
        calls: list[str] = []
        s = self.session([], calls)
        with (
            mock.patch.object(flows_wallpaper, "go_home"),
            mock.patch.object(flows_settings, "set_homepage_recent_tabs"),
        ):
            with self.assertRaisesRegex(StepError, "Jump back in card"):
                flows_wallpaper.recent_tab_homepage(s)
        self.assertEqual(calls, ["force-stop", "relaunch"])


if __name__ == "__main__":
    unittest.main()
