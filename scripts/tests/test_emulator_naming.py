import tempfile
import unittest
from pathlib import Path

from scripts.emulator.naming import ScreenIndex, capture_name, check_index_matches_files


class CaptureNameTests(unittest.TestCase):
    def test_numbered_screen(self) -> None:
        self.assertEqual(
            capture_name("04-homepage", theme="light"),
            "04-homepage_dynamic-off_light.png",
        )

    def test_private_and_dynamic_flags(self) -> None:
        self.assertEqual(
            capture_name("14-main-menu", theme="dark", dynamic=True, private=True),
            "14-main-menu_dynamic-on_dark_private.png",
        )

    def test_extra_screen_without_number(self) -> None:
        self.assertEqual(capture_name("settings-subpage-search", theme="dark"), "settings-subpage-search_dynamic-off_dark.png")

    def test_legacy_theme_names_the_api_30_set(self) -> None:
        self.assertEqual(capture_name("customize", theme="legacy"), "customize_dynamic-off_legacy.png")

    def test_rejects_bad_input(self) -> None:
        for kwargs in ({"screen": "Bad Name", "theme": "light"}, {"screen": "ok", "theme": "sepia"}, {"screen": "a_b", "theme": "dark"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                capture_name(**kwargs)


class ScreenIndexTests(unittest.TestCase):
    def make_index(self) -> ScreenIndex:
        index = ScreenIndex(title="screens-index (light)", header=["Variant: light"])
        index.ok("homepage", "dynamic-off light", "04-homepage_dynamic-off_light.png")
        index.missing("history", "dynamic-off light", "09-history_dynamic-off_light.png", "StepError: not found:\n  History")
        index.add_report("coinstall.txt", "co-install check")
        return index

    def test_render_lists_status_reason_and_counts(self) -> None:
        text = self.make_index().render()
        self.assertIn("Captures: 1 OK, 1 MISSING of 2 expected.", text)
        self.assertIn("| homepage | dynamic-off light | 04-homepage_dynamic-off_light.png | OK |  |", text)
        self.assertIn("| MISSING | StepError: not found: History |", text)
        self.assertIn("| coinstall.txt | co-install check |", text)

    def test_index_and_files_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "04-homepage_dynamic-off_light.png").write_bytes(b"x")
            (out / "coinstall.txt").write_text("x")
            text = self.make_index().render()
            (out / "screens-index.md").write_text(text)
            self.assertEqual(check_index_matches_files(text, out), [])

    def test_mismatches_are_reported_in_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "extra_dynamic-off_light.png").write_bytes(b"x")
            (out / "09-history_dynamic-off_light.png").write_bytes(b"x")
            text = self.make_index().render()
            problems = check_index_matches_files(text, out)
            self.assertIn("not in index: extra_dynamic-off_light.png", problems)
            self.assertIn("OK entry without file: 04-homepage_dynamic-off_light.png", problems)
            self.assertIn("MISSING entry has a file: 09-history_dynamic-off_light.png", problems)
            self.assertIn("REPORT entry without file: coinstall.txt", problems)

    def test_deferred_reports_are_not_problems(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            index = ScreenIndex(title="t")
            index.add_report("network-hosts.txt", "later")
            self.assertEqual(check_index_matches_files(index.render(), out, deferred=frozenset({"network-hosts.txt"})), [])
