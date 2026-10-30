import unittest

from scripts.emulator import flows_tabs, uidump
from scripts.tests.emulator_fakes import hierarchy, node


def dump(*nodes: str) -> list[uidump.Node]:
    return uidump.parse(hierarchy(*nodes))


def card(left: int, top: int, right: int, bottom: int, clickable: bool = True) -> str:
    return node(bounds=f"[{left},{top}][{right},{bottom}]", clickable=clickable)


class TabCardTests(unittest.TestCase):
    def test_cards_come_in_reading_order(self) -> None:
        nodes = dump(
            card(560, 900, 1040, 1500),
            card(40, 300, 520, 900),
            card(40, 900, 520, 1500),
            card(560, 300, 1040, 900),
        )
        found = flows_tabs.tab_cards(nodes)
        self.assertEqual([c.bounds[:2] for c in found], [(40, 300), (560, 300), (40, 900), (560, 900)])

    def test_small_buttons_banner_and_full_width_views_are_not_cards(self) -> None:
        nodes = dump(
            card(40, 20, 520, 160),  # inside the banner
            card(900, 320, 1000, 420),  # close button
            card(0, 200, 1080, 2300),  # whole list
            card(40, 300, 520, 900, clickable=False),  # not clickable
            card(560, 300, 1040, 900),
        )
        found = flows_tabs.tab_cards(nodes)
        self.assertEqual([c.bounds for c in found], [(560, 300, 1040, 900)])

    def test_banner_buttons_match_the_strings_fenix_sets(self) -> None:
        samples = {
            flows_tabs.BANNER_NORMAL: "Normal Tabs Open: 3. Tap to switch tabs.",
            flows_tabs.BANNER_PRIVATE: "Private Tabs Open: 1. Tap to switch tabs.",
            flows_tabs.BANNER_GROUPS: "1 tab group open. Tap to switch tabs.",
            flows_tabs.BANNER_SYNCED: "Synced Tabs Open: 0. Tap to switch tabs.",
        }
        for selector, desc in samples.items():
            with self.subTest(desc=desc):
                self.assertIsNotNone(uidump.find_first(dump(node(desc=desc, bounds="[0,0][200,100]")), selector))
        plural = dump(node(desc="2 tab groups open. Tap to switch tabs.", bounds="[0,0][200,100]"))
        self.assertIsNotNone(uidump.find_first(plural, flows_tabs.BANNER_GROUPS))

    def test_group_card_and_selection_title_selectors(self) -> None:
        self.assertIsNotNone(uidump.find_first(dump(node(text="Group 1", bounds="[0,0][200,100]")), flows_tabs.GROUP_CARD))
        row = dump(node(desc="Add to Group 1 tab group, 2 tabs, color Yellow", bounds="[0,0][200,100]"))
        self.assertIsNotNone(uidump.find_first(row, flows_tabs.GROUP_CARD))
        self.assertIsNotNone(uidump.find_first(dump(node(text="2 selected", bounds="[0,0][200,100]")), flows_tabs.SELECTION_TITLE))


if __name__ == "__main__":
    unittest.main()
