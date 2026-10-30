"""Parsing and selection against uiautomator dumps recorded from the CI emulator (API 34, Pixel 6)."""
import unittest

from scripts.emulator import targets as t
from scripts.emulator import uidump
from scripts.emulator.device import Device
from scripts.tests.emulator_fakes import FIXTURES


def load(name: str) -> list[uidump.Node]:
    return uidump.parse((FIXTURES / name).read_text(encoding="utf-8"))


class RecordedOnboardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = load("onboarding-welcome.xml")

    def test_screen_size_comes_from_the_root_node(self) -> None:
        self.assertEqual(uidump.screen_size(self.nodes), (1080, 2400))

    def test_continue_button_is_found_and_tapped_in_its_middle(self) -> None:
        button = uidump.find_first(self.nodes, *t.ONBOARDING_BUTTONS)
        self.assertEqual(button.text, "Continue")
        self.assertEqual(button.center, (540, 1930))

    def test_content_description_links_are_readable(self) -> None:
        links = uidump.find_all(self.nodes, uidump.by_desc(r".*Terms of Use.*"))
        self.assertEqual(len(links), 1)

    def test_html_entities_in_text_are_decoded(self) -> None:
        tagline = uidump.find_first(self.nodes, uidump.by_text(r"Speedy, safe.*"))
        self.assertIn("\n", tagline.text)

    def test_homepage_bar_is_not_on_the_onboarding_page(self) -> None:
        self.assertIsNone(uidump.find_first(self.nodes, t.HOMEPAGE_BAR))

    def test_no_system_dialog_over_the_onboarding_page(self) -> None:
        self.assertIsNone(Device._find_dialog(self.nodes))


class RecordedHomepageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = load("homepage-top-toolbar.xml")

    def test_homepage_is_recognised_by_its_view_and_address_bar(self) -> None:
        self.assertIsNotNone(uidump.find_first(self.nodes, t.HOMEPAGE_VIEW))
        bar = uidump.find_first(self.nodes, t.HOMEPAGE_BAR)
        self.assertEqual(bar.id_name, "ADDRESSBAR_URL_BOX")

    def test_default_toolbar_sits_at_the_top(self) -> None:
        bar = uidump.find_first(self.nodes, t.ADDRESS_BAR)
        self.assertLess(bar.center[1], uidump.screen_size(self.nodes)[1] // 2)

    def test_menu_and_tab_counter_are_found_by_stable_ids(self) -> None:
        self.assertEqual(uidump.find_first(self.nodes, t.MENU_BUTTON).desc, "More options")
        self.assertIsNotNone(uidump.find_first(self.nodes, t.TAB_COUNTER))

    def test_search_engine_selector_and_voice_search_are_found(self) -> None:
        self.assertIsNotNone(uidump.find_first(self.nodes, t.SEARCH_ENGINE_SELECTOR))
        extras = {n.label for n in uidump.find_all(self.nodes, t.SEARCH_EXTRAS)}
        self.assertEqual(extras, {"Voice search"})

    def test_onboarding_buttons_do_not_match_the_homepage(self) -> None:
        self.assertIsNone(uidump.find_first(self.nodes, *t.ONBOARDING_BUTTONS))


class RecordedAnrDialogTests(unittest.TestCase):
    def test_launcher_anr_dialog_is_recognised_and_wait_is_chosen(self) -> None:
        hit = Device._find_dialog(load("anr-launcher-dialog.xml"))
        self.assertIsNotNone(hit)
        title, button = hit
        self.assertEqual(title, "Pixel Launcher isn't responding")
        self.assertEqual(button.label, "Wait")
        self.assertEqual(button.center, (540, 1359))

    def test_dialog_screen_has_no_app_content(self) -> None:
        self.assertIsNone(uidump.find_first(load("anr-launcher-dialog.xml"), *t.ONBOARDING_BUTTONS))


if __name__ == "__main__":
    unittest.main()
