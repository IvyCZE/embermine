import unittest

from scripts.emulator import uidump
from scripts.emulator.uidump import Selector
from scripts.tests.emulator_fakes import hierarchy, node, tty_output


class ParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = tty_output(
            hierarchy(
                node(text="Search or enter address", bounds="[100,2100][900,2200]"),
                node(desc="More options", rid="org.mozilla.firefox:id/menuButton", bounds="[940,2100][1040,2200]", clickable=True),
                node(text="Hidden", bounds="[0,0][0,0]"),
                node(desc="3 open tabs. Tap to switch tabs.", bounds="[820,2100][920,2200]"),
            )
        )
        self.nodes = uidump.parse(self.raw)

    def test_trailing_status_line_is_ignored(self) -> None:
        self.assertEqual(len(self.nodes), 5)

    def test_bounds_center_and_screen_size(self) -> None:
        bar = uidump.find_first(self.nodes, Selector(text="Search or enter address"))
        self.assertEqual(bar.center, (500, 2150))
        self.assertEqual(uidump.screen_size(self.nodes), (1080, 2400))

    def test_find_by_resource_id_ignores_the_package(self) -> None:
        for package in ("org.mozilla.firefox", "yt.ivy.embermine"):
            raw = hierarchy(node(rid=f"{package}:id/menuButton", bounds="[1,1][3,3]"))
            self.assertIsNotNone(uidump.find_first(uidump.parse(raw), uidump.by_id("menuButton")), package)

    def test_content_desc_regex_matches_the_whole_value(self) -> None:
        self.assertIsNotNone(uidump.find_first(self.nodes, uidump.by_desc(r"\d+ open tabs?\. Tap to switch tabs\.")))
        self.assertIsNone(uidump.find_first(self.nodes, uidump.by_desc(r"More")))

    def test_text_match_is_case_insensitive(self) -> None:
        self.assertIsNotNone(uidump.find_first(self.nodes, uidump.by_text("search or ENTER address")))

    def test_invisible_nodes_are_skipped(self) -> None:
        self.assertEqual(uidump.find_all(self.nodes, uidump.by_text("Hidden")), [])

    def test_selectors_are_tried_in_order_of_preference(self) -> None:
        found = uidump.find_first(self.nodes, uidump.by_id("menuButton"), uidump.by_text("Search or enter address"))
        self.assertEqual(found.desc, "More options")
        found = uidump.find_first(self.nodes, uidump.by_id("missing"), uidump.by_desc("More options"))
        self.assertEqual(found.id_name, "menuButton")

    def test_label_matches_text_or_content_desc(self) -> None:
        self.assertEqual(len(uidump.find_all(self.nodes, uidump.by_label("More options|Search or enter address"))), 2)

    def test_garbage_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            uidump.parse("ERROR: could not get idle state.")
        with self.assertRaises(ValueError):
            uidump.parse("<hierarchy rotation='0'><node")
