import contextlib
import unittest
from collections.abc import Iterator
from types import SimpleNamespace
from unittest import mock

from scripts.emulator import flows_cross, flows_motion, flows_settings, flows_tabs
from scripts.emulator.naming import capture_name

SWITCH_STATES = (flows_cross.TOGGLE_OFF, flows_cross.TOGGLE_ON, flows_cross.RESTART_OFF, flows_cross.RESTART_ON)
NORMAL_STEMS = ("10-toolbar", "14-main-menu", "12-tab-tray-header", "page-load-top-loading", "pull-to-refresh-top-pulling")


class RecordingSession:
    """Stands in for Session: records each capture with the switch state it was taken in."""

    def __init__(self, private_screenshots: bool = True) -> None:
        self.dynamic = False
        self.private_screenshots = private_screenshots
        self.captures: list[str] = []
        self.ensure_normal_calls = 0
        self.dev = SimpleNamespace(
            tap=lambda *args, **kwargs: None,
            try_tap=lambda *args, **kwargs: True,
            wait_for=lambda *args, **kwargs: object(),
            sleep=lambda seconds: None,
        )

    @contextlib.contextmanager
    def capture(self, screen, *, private=False, label=None, file=None, combination=None):
        self.captures.append(capture_name(screen, theme="light", dynamic=self.dynamic, private=private))
        yield SimpleNamespace(take=lambda settle=1.5, note="": None)

    def ensure_normal(self) -> None:
        self.ensure_normal_calls += 1


@contextlib.contextmanager
def recorded_helpers() -> Iterator[dict[str, mock.Mock]]:
    """Replaces the browser, tab tray, motion and settings helpers with recorders, so a group's own order is tested."""
    targets = {
        "go_home": (flows_cross, "go_home"),
        "load_page": (flows_cross, "load_page"),
        "close_overlay": (flows_cross, "close_overlay"),
        "open_tray": (flows_tabs, "open_tray"),
        "ensure_tray": (flows_tabs, "ensure_tray"),
        "show_page": (flows_tabs, "show_page"),
        "close_tray": (flows_tabs, "close_tray"),
        "ensure_toolbar_position": (flows_motion, "ensure_toolbar_position"),
        "page_load": (flows_motion, "page_load"),
        "pull_to_refresh": (flows_motion, "pull_to_refresh"),
        "allow_private_screenshots": (flows_settings, "allow_private_screenshots"),
    }
    patches = {name: mock.patch.object(owner, attr) for name, (owner, attr) in targets.items()}
    started = {name: patch.start() for name, patch in patches.items()}
    try:
        yield started
    finally:
        for patch in patches.values():
            patch.stop()


class CrossGroupTests(unittest.TestCase):
    def test_screen_group_takes_the_normal_screens_in_one_state_and_hands_the_indicators_to_motion(self) -> None:
        s = RecordingSession()
        with recorded_helpers() as helpers:
            flows_cross.screen_group(s, flows_cross.TOGGLE_OFF)
        self.assertEqual(
            s.captures,
            [
                "10-toolbar-after-toggle-off_dynamic-off_light.png",
                "14-main-menu-after-toggle-off_dynamic-off_light.png",
                "12-tab-tray-header-after-toggle-off_dynamic-off_light.png",
            ],
        )
        helpers["page_load"].assert_called_once_with(
            s, "top", suffix="-after-toggle-off", label=", switch turned off", after_load=False
        )
        helpers["pull_to_refresh"].assert_called_once_with(
            s, "top", suffix="-after-toggle-off", label=", switch turned off", reloading=False
        )

    def test_screen_group_of_a_restart_names_the_state_it_is_taken_in(self) -> None:
        s = RecordingSession()
        with recorded_helpers() as helpers:
            flows_cross.screen_group(s, flows_cross.RESTART_ON)
        self.assertEqual(s.captures[0], "10-toolbar-after-restart-on_dynamic-on_light.png")
        helpers["pull_to_refresh"].assert_called_once_with(
            s, "top", suffix="-after-restart-on", label=", switch on after a restart", reloading=False
        )

    def test_screen_group_puts_the_toolbar_at_the_top_before_the_top_named_captures(self) -> None:
        s = RecordingSession()
        calls: list[str] = []
        with recorded_helpers() as helpers:
            helpers["ensure_toolbar_position"].side_effect = lambda *args, **kwargs: calls.append("ensure-toolbar")
            helpers["page_load"].side_effect = lambda *args, **kwargs: calls.append("page-load")
            helpers["pull_to_refresh"].side_effect = lambda *args, **kwargs: calls.append("pull-to-refresh")
            flows_cross.screen_group(s, flows_cross.TOGGLE_ON)
        self.assertEqual(calls, ["ensure-toolbar", "page-load", "pull-to-refresh"])
        helpers["ensure_toolbar_position"].assert_called_once_with(s, "top")

    def test_every_switch_state_puts_its_switch_value_in_every_file_name(self) -> None:
        for state in SWITCH_STATES:
            with self.subTest(state=state.suffix), recorded_helpers():
                s = RecordingSession()
                flows_cross.screen_group(s, state)
            for name in s.captures:
                self.assertIn(f"{state.suffix}_dynamic-{'on' if state.on else 'off'}_light.png", name)

    def test_normal_groups_cover_the_accent_shapes_and_indicators_in_all_four_states(self) -> None:
        names = {(stem, on) for stem, on, _ in flows_cross.NORMAL_CAPTURES}
        for state in SWITCH_STATES:
            for stem in NORMAL_STEMS:
                with self.subTest(stem=stem, state=state.suffix):
                    self.assertIn((stem + state.suffix, state.on), names)
        self.assertEqual(len(flows_cross.NORMAL_CAPTURES), len(SWITCH_STATES) * len(NORMAL_STEMS))

    def test_private_group_is_taken_with_the_switch_off_and_covers_homepage_menu_and_tab_tray(self) -> None:
        self.assertEqual(
            [stem for stem, _, _ in flows_cross.PRIVATE_CAPTURES],
            [
                "04-homepage-after-toggle-off",
                "10-toolbar-after-toggle-off",
                "14-main-menu-after-toggle-off",
                "12-tab-tray-header-after-toggle-off",
            ],
        )
        self.assertTrue(all(on is False for _, on, _ in flows_cross.PRIVATE_CAPTURES))

    def test_private_group_takes_its_captures_in_private_mode_and_returns_to_normal_mode(self) -> None:
        s = RecordingSession()
        with recorded_helpers():
            flows_cross.private_group(s, flows_cross.TOGGLE_OFF)
        self.assertEqual(
            s.captures,
            [
                "04-homepage-after-toggle-off_dynamic-off_light_private.png",
                "10-toolbar-after-toggle-off_dynamic-off_light_private.png",
                "14-main-menu-after-toggle-off_dynamic-off_light_private.png",
                "12-tab-tray-header-after-toggle-off_dynamic-off_light_private.png",
            ],
        )
        self.assertEqual(s.ensure_normal_calls, 1)

    def test_private_group_allows_private_screenshots_first_when_the_walk_has_not_yet(self) -> None:
        s = RecordingSession(private_screenshots=False)
        with recorded_helpers() as helpers:
            flows_cross.private_group(s, flows_cross.TOGGLE_OFF)
        helpers["allow_private_screenshots"].assert_called_once_with(s)
        self.assertTrue(s.private_screenshots)

    def test_private_group_leaves_the_setting_alone_when_it_is_already_allowed(self) -> None:
        with recorded_helpers() as helpers:
            flows_cross.private_group(RecordingSession(private_screenshots=True), flows_cross.TOGGLE_OFF)
        helpers["allow_private_screenshots"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
