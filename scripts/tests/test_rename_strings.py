import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rename_strings", Path(__file__).resolve().parents[1] / "generate" / "rename-strings.py"
)
assert _SPEC and _SPEC.loader
rs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rs)

FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<resources xmlns:tools="http://schemas.android.com/tools">
    <!-- %1$s is the name of the app (for example "Firefox"). -->
    <string name="onboarding_welcome_to_firefox" tools:ignore="BrandUsage">Welcome to Firefox</string>
    <string name="default_browser_text">Make Firefox your default browser. Firefox's tabs are safe.</string>
    <string name="user_text">You’re a Firefox user</string>
    <string name="onboarding_term_of_service_line_one_link_text_2">Firefox Terms of Use</string>
    <string name="onboarding_term_of_service_line_two_2">Firefox cares about your privacy. Learn more in our %1$s.</string>
    <string name="preference_search_address_bar_fx_suggest">Address bar - Firefox Suggest</string>
    <string name="firefox_suggest_header">Firefox Suggest</string>
    <string name="firefox_labs_title">Firefox Labs</string>
    <string name="sync_connect_device_dialog">To send a tab, sign in to Firefox on at least one other device.</string>
    <string name="synced_tabs_no_tabs">You don’t have any tabs open in Firefox on your other devices.</string>
    <string name="fxa_received_tab_channel_description">Notifications for tabs received from other Firefox devices.</string>
    <string name="sign_in_instructions"><![CDATA[On your computer open Firefox and go to <b>https://firefox.com/pair</b>]]></string>
    <string name="other_text">See your Firefox account or Mozilla account. Based on Firefox, built on Firefox.</string>
    <string name="based_text">Embermine is based on Firefox and uses Firefox.</string>
    <string name="no_brand">Nothing to see here</string>
    <plurals name="tabs_open">
        <item quantity="one">%d tab open in Firefox</item>
        <item quantity="other">%d tabs open in Firefox</item>
    </plurals>
</resources>
"""


class RenameTextTests(unittest.TestCase):
    def test_plain_app_name_is_renamed(self) -> None:
        self.assertEqual(
            rs.rename_text("onboarding_welcome_to_firefox", "Welcome to Firefox"),
            "Welcome to Embermine",
        )

    def test_possessive_and_repeats(self) -> None:
        self.assertEqual(
            rs.rename_text("x", "Firefox's tabs, Firefox settings"),
            "Embermine's tabs, Embermine settings",
        )

    def test_indefinite_article_follows_the_new_name(self) -> None:
        self.assertEqual(rs.rename_text("x", "a Firefox user"), "an Embermine user")
        self.assertEqual(rs.rename_text("x", "A Firefox user"), "An Embermine user")

    def test_keep_list_phrases_are_unchanged(self) -> None:
        for text in (
            "Firefox Terms of Use",
            "Address bar - Firefox Suggest",
            "Learn more about Firefox Suggest",
            "Firefox Labs",
            "Sign in to Firefox on at least one other device",
            "tabs open in Firefox on your other devices",
            "tabs received from other Firefox devices",
            "Your Firefox account",
            "Embermine is based on Firefox",
            "open Firefox and go to https://firefox.com/pair",
        ):
            with self.subTest(text=text):
                self.assertEqual(rs.rename_text("plain_name", text), text)

    def test_keep_list_names_are_unchanged(self) -> None:
        for name in (
            "sync_connect_device_dialog",
            "synced_tabs_no_tabs",
            "fxa_received_tab_channel_description",
            "sign_in_instructions",
            "firefox_suggest_header",
            "firefox_labs_title",
            "preference_search_address_bar_fx_suggest",
            "onboarding_redesign_sync_title",
        ):
            with self.subTest(name=name):
                self.assertEqual(rs.rename_text(name, "Use Firefox"), "Use Firefox")

    def test_only_the_keep_phrase_is_protected(self) -> None:
        self.assertEqual(
            rs.rename_text("x", "Firefox cares. See Firefox Terms of Use and Firefox."),
            "Embermine cares. See Firefox Terms of Use and Embermine.",
        )

    def test_lowercase_and_words_containing_firefox_are_untouched(self) -> None:
        self.assertEqual(rs.rename_text("x", "firefox.com FirefoxOS"), "firefox.com FirefoxOS")


class RenameStringsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.out, self.names = rs.rename_strings(FIXTURE)

    def test_replaced_names(self) -> None:
        self.assertEqual(
            self.names,
            [
                "onboarding_welcome_to_firefox",
                "default_browser_text",
                "user_text",
                "onboarding_term_of_service_line_two_2",
                "other_text",
                "based_text",
                "tabs_open",
            ],
        )

    def test_welcome_renamed_and_keep_list_untouched(self) -> None:
        self.assertIn(">Welcome to Embermine<", self.out)
        for kept in (
            ">Firefox Terms of Use<",
            ">Address bar - Firefox Suggest<",
            ">Firefox Suggest<",
            ">Firefox Labs<",
            "sign in to Firefox on at least one other device.<",
            "open in Firefox on your other devices.<",
            "from other Firefox devices.<",
            "open Firefox and go to <b>https://firefox.com/pair</b>",
            "Embermine is based on Firefox and uses Embermine.",
        ):
            with self.subTest(kept=kept):
                self.assertIn(kept, self.out)

    def test_mixed_string(self) -> None:
        self.assertIn(
            "See your Firefox account or Mozilla account. Based on Firefox, built on Embermine.",
            self.out,
        )

    def test_plurals_items_are_renamed(self) -> None:
        self.assertIn("%d tab open in Embermine<", self.out)
        self.assertIn("%d tabs open in Embermine<", self.out)

    def test_comments_are_not_modified(self) -> None:
        self.assertIn('(for example "Firefox")', self.out)

    def test_everything_else_is_byte_identical(self) -> None:
        self.assertIn('<string name="no_brand">Nothing to see here</string>', self.out)
        self.assertEqual(self.out.count("\n"), FIXTURE.count("\n"))

    def test_second_run_finds_nothing_more_to_rename(self) -> None:
        again, names = rs.rename_strings(self.out)
        self.assertEqual(names, [])
        self.assertEqual(again, self.out)


class RunTests(unittest.TestCase):
    def _tree(self, tmp: str, xml: str | None) -> Path:
        tree = Path(tmp)
        if xml is not None:
            path = tree / rs.STRINGS_REL
            path.parent.mkdir(parents=True)
            path.write_text(xml, encoding="utf-8")
        return tree

    def test_rewrites_english_file_prints_names_and_leaves_locales(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree(tmp, FIXTURE)
            locale = tree / "mobile/android/fenix/app/src/main/res/values-de/strings.xml"
            locale.parent.mkdir(parents=True)
            locale.write_text(FIXTURE, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rs.run(tree)
            printed = buf.getvalue()
            self.assertIn("renamed onboarding_welcome_to_firefox", printed)
            self.assertIn("renamed tabs_open", printed)
            self.assertNotIn("renamed firefox_labs_title", printed)
            self.assertIn("in 7 strings", printed)
            self.assertIn("Welcome to Embermine", (tree / rs.STRINGS_REL).read_text(encoding="utf-8"))
            self.assertEqual(locale.read_text(encoding="utf-8"), FIXTURE)

    def test_missing_strings_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                rs.run(self._tree(tmp, None))
            self.assertIn("not found", str(ctx.exception))

    def test_no_match_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml = '<resources><string name="a">Nothing</string></resources>'
            with self.assertRaises(SystemExit) as ctx:
                rs.run(self._tree(tmp, xml))
            self.assertIn("no 'Firefox' strings", str(ctx.exception))

    def test_main_requires_tree_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree(tmp, FIXTURE)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(rs.main(["--tree", str(tree)]), 0)


if __name__ == "__main__":
    unittest.main()
