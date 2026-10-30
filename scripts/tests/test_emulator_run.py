import unittest

from scripts.emulator import flows_browse, flows_motion, flows_settings, run


class FlowWiringTests(unittest.TestCase):
    def test_flow_list_builds_and_every_flow_is_callable(self) -> None:
        flows = run.flow_list()
        self.assertGreaterEqual(len(flows), 9)
        for flow in flows:
            self.assertTrue(callable(flow.run), flow.name)
            self.assertTrue(flow.expected, flow.name)

    def test_private_flows_are_marked_and_cover_the_four_private_screens(self) -> None:
        private = [f for f in run.flow_list() if f.private]
        stems = {stem for f in private for stem, _, is_private in f.expected if is_private}
        self.assertTrue({"04-homepage", "10-toolbar", "14-main-menu", "13-site-protection-panel"} <= stems)

    def test_every_requested_screen_is_expected_by_some_flow(self) -> None:
        stems = {(stem, private) for f in run.flow_list() for stem, _, private in f.expected}
        wanted = {
            "12-tab-tray-header", "06-tab-tray-overflow-menu", "07-tab-selection-mode", "02-tab-groups-list",
            "03-tab-group-sheet", "08-tab-group-menu", "tab-grid-group-header", "01-synced-tabs", "15-downloads",
            "downloads-active", "downloads-paused", "download-notification", "wallpaper-picker", "customize",
            "bottom-navigation-bar", "14-main-menu-loading", "secret-settings-before", "secret-settings-unlocked",
            "secret-settings-after-restart",
        }
        self.assertEqual(wanted - {stem for stem, _ in stems}, set())
        self.assertIn(("12-tab-tray-header", True), stems)

    def test_expected_stems_are_unique_per_privacy_mode(self) -> None:
        seen: set[tuple[str, bool]] = set()
        for flow in run.flow_list():
            for stem, _, private in flow.expected:
                self.assertNotIn((stem, private), seen, stem)
                seen.add((stem, private))

    def test_legacy_flow_list_has_homepage_customize_and_wallpaper_picker(self) -> None:
        stems = {stem for f in run.flow_list("legacy") for stem, _, _ in f.expected}
        self.assertEqual(stems, {"04-homepage", "customize", "settings-homepage", "wallpaper-picker"})
        for flow in run.flow_list("legacy"):
            self.assertTrue(callable(flow.run), flow.name)

    def test_run_helpers_exist(self) -> None:
        for module, name in (
            (flows_settings, "allow_private_screenshots"),
            (flows_settings, "about_config"),
            (flows_browse, "complete_onboarding"),
            (flows_motion, "both_positions"),
        ):
            self.assertTrue(callable(getattr(module, name)), name)


if __name__ == "__main__":
    unittest.main()
