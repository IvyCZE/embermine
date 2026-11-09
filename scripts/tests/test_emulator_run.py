import re
import unittest

from scripts.emulator import flows_browse, flows_motion, flows_settings, run
from scripts.emulator.naming import capture_name
from scripts.tests.helpers import REPO_ROOT


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
            "bottom-navigation-bar", "bottom-navigation-bar-back", "bottom-navigation-bar-home", "14-main-menu-loading",
            "secret-settings-before", "secret-settings-unlocked",
            "secret-settings-after-restart", "about", "about-whatsnew", "about-support", "about-privacy",
            "about-licenses", "about-crashes", "about-before-logo-taps", "about-after-logo-taps",
            "settings-data-collection", "settings-data-collection-scrolled", "settings-homepage-sponsored",
        }
        self.assertEqual(wanted - {stem for stem, _ in stems}, set())
        self.assertIn(("12-tab-tray-header", True), stems)

    def test_about_config_pref_pattern_matches_pref_names_only(self) -> None:
        for name in ("general.aboutConfig.enable", "browser.tabs.warnOnClose", "devtools.console.stdout.chrome"):
            self.assertIsNotNone(flows_settings.PREF_NAME.fullmatch(name), name)
        for text in ("About", "Search preference name", "https://example.com", "Embermine 159.0"):
            self.assertIsNone(flows_settings.PREF_NAME.fullmatch(text), text)

    def test_expected_stems_are_unique_per_privacy_mode(self) -> None:
        seen: set[tuple[str, bool]] = set()
        for flow in run.flow_list():
            for stem, _, private in flow.expected:
                self.assertNotIn((stem, private), seen, stem)
                seen.add((stem, private))

    def test_legacy_flow_list_has_homepage_menu_tray_customize_wallpaper_picker_and_the_opt_in(self) -> None:
        stems = {stem for f in run.flow_list("legacy") for stem, _, _ in f.expected}
        self.assertEqual(
            stems,
            {
                "04-homepage",
                "14-main-menu",
                "12-tab-tray-header",
                "customize",
                "settings-homepage",
                "settings-homepage-sponsored",
                "wallpaper-picker",
                "settings-data-collection-opt-in",
            },
        )
        for flow in run.flow_list("legacy"):
            self.assertTrue(callable(flow.run), flow.name)

    def test_legacy_customize_is_labelled_as_the_android_11_screen_without_the_switch(self) -> None:
        customize = next(label for f in run.legacy_flow_list() for stem, label, _ in f.expected if stem == "customize")
        self.assertIn("Android 11", customize)
        self.assertNotIn("first run", customize)

    def test_first_run_customize_is_the_second_flow_and_only_runs_with_the_switch_on(self) -> None:
        on = run.flow_list("light", "on")
        self.assertEqual(on[1].name, "first run customize")
        self.assertEqual(on[1].states, {"customize-first-run": True})
        self.assertNotIn("first run customize", {f.name for f in run.flow_list("dark", "off")})

    def test_every_capture_of_a_walk_has_its_own_file_name(self) -> None:
        for accent in ("on", "off"):
            with self.subTest(accent=accent):
                names: list[str] = []
                for flow in run.flow_list("light", accent):
                    for stem, _, private in flow.expected:
                        dynamic = flow.states.get(stem, accent == "on")
                        names.append(capture_name(stem, theme="light", dynamic=dynamic, private=private))
                duplicates = sorted({name for name in names if names.count(name) > 1})
                self.assertEqual(duplicates, [])

    def test_flow_budget_leaves_room_in_the_emulator_job_limit(self) -> None:
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        job = ci[ci.index("  emulator:") : ci.index("  emulator-legacy:")]
        limit = int(re.search(r"timeout-minutes: (\d+)", job)[1])
        # the boot, the install, the network report and the upload take about 25 minutes around the walk
        self.assertLessEqual(run.FLOW_BUDGET_SECONDS / 60 + 25, limit)

    def test_data_collection_opt_in_runs_only_in_the_legacy_pass_without_packet_capture(self) -> None:
        main = {stem for f in run.flow_list() for stem, _, _ in f.expected}
        self.assertNotIn("settings-data-collection-opt-in", main)
        self.assertEqual(run.legacy_flow_list()[-1].name, "data collection opt-in")

    def test_run_helpers_exist(self) -> None:
        for module, name in (
            (flows_settings, "allow_private_screenshots"),
            (flows_settings, "about_config"),
            (flows_browse, "complete_onboarding"),
            (flows_motion, "both_positions"),
            (flows_settings, "about_pages"),
        ):
            self.assertTrue(callable(getattr(module, name)), name)

    def test_about_pages_cover_each_row_that_opens_something(self) -> None:
        stems = [stem for stem, _, _, _ in flows_settings.ABOUT_PAGES]
        self.assertEqual(stems, ["about-whatsnew", "about-support", "about-privacy", "about-licenses", "about-crashes"])
        expected = {stem for f in run.flow_list() for stem, _, _ in f.expected}
        self.assertTrue(set(stems) <= expected)


if __name__ == "__main__":
    unittest.main()
