import unittest

from scripts.release import detect as d
from scripts.version import VersionError


def releases(*tags: str) -> list[d.Release]:
    return d.parse_release_tags(tags)


class TagParsingTests(unittest.TestCase):
    def test_android_and_desktop_release_tags_map_to_versions(self) -> None:
        self.assertEqual(d.tag_to_version("FIREFOX-ANDROID_159_0_RELEASE"), "159.0")
        self.assertEqual(d.tag_to_version("FIREFOX_159_0_1_RELEASE"), "159.0.1")
        self.assertEqual(d.tag_to_version("FIREFOX-ANDROID_158_0_2_RELEASE"), "158.0.2")

    def test_betas_builds_and_esr_tags_are_not_releases(self) -> None:
        for tag in (
            "FIREFOX-ANDROID_161_0b1_RELEASE",
            "FIREFOX-ANDROID_161_0b1_BUILD1",
            "FIREFOX_91_0esr_RELEASE",
            "FIREFOX_BETA_161_END",
            "FIREFOX_159_0_RC_BUILD1",
            "v159.0",
        ):
            with self.subTest(tag=tag):
                self.assertIsNone(d.tag_to_version(tag))

    def test_ls_remote_output_is_deduplicated_and_peeled(self) -> None:
        output = (
            "aaa\trefs/tags/FIREFOX_159_0_RELEASE\n"
            "bbb\trefs/tags/FIREFOX_159_0_RELEASE^{}\n"
            "ccc\trefs/heads/main\n"
            "ddd\trefs/tags/FIREFOX-ANDROID_159_0_RELEASE\n"
        )
        self.assertEqual(d.parse_ls_remote_tags(output), ["FIREFOX-ANDROID_159_0_RELEASE", "FIREFOX_159_0_RELEASE"])

    def test_highest_tag_version_compares_numerically(self) -> None:
        tags = ["FIREFOX_159_0_9_RELEASE", "FIREFOX_159_0_10_RELEASE", "FIREFOX_159_0_RELEASE"]
        self.assertEqual(d.highest_tag_version(tags), "159.0.10")

    def test_android_only_dot_release_is_found_when_product_details_lags(self) -> None:
        tags = ["FIREFOX_159_0_RELEASE", "FIREFOX-ANDROID_159_0_1_RELEASE"]
        self.assertEqual(d.upstream_version("159.0", tags), "159.0.1")

    def test_upstream_is_the_larger_of_product_details_and_tags(self) -> None:
        self.assertEqual(d.upstream_version("160.0", ["FIREFOX_159_0_2_RELEASE"]), "160.0")
        self.assertEqual(d.upstream_version("159.0", ["FIREFOX_159_0_RELEASE"]), "159.0")

    def test_no_release_tags_at_all_uses_product_details(self) -> None:
        self.assertEqual(d.upstream_version("159.0", []), "159.0")

    def test_parse_release_tags_reads_base_and_rebuild_numbers(self) -> None:
        parsed = d.parse_release_tags(["v159.0", "v159.0-r2", "v159.0.1", "v159.0-dev.3", "latest", "v159.0-r10"])
        self.assertEqual(
            [(r.tag, r.firefox, r.number) for r in parsed],
            [("v159.0", "159.0", 1), ("v159.0-r2", "159.0", 2), ("v159.0.1", "159.0.1", 1), ("v159.0-r10", "159.0", 10)],
        )


class ChooseTests(unittest.TestCase):
    def test_no_github_release_yet_is_new(self) -> None:
        choice = d.choose(upstream="159.0", releases=[], requested=None, rebuild=False)
        self.assertTrue(choice.build)
        self.assertEqual((choice.firefox, choice.rebuild), ("159.0", None))
        self.assertEqual((choice.embermine_version, choice.tag), ("159.0", "v159.0"))

    def test_latest_release_equal_to_upstream_is_nothing_new(self) -> None:
        choice = d.choose(upstream="159.0", releases=releases("v159.0"), requested=None, rebuild=False)
        self.assertFalse(choice.build)
        self.assertIn("nothing new", choice.reason)

    def test_rebuild_suffix_on_the_latest_release_still_counts_as_the_same_version(self) -> None:
        choice = d.choose(upstream="159.0", releases=releases("v159.0", "v159.0-r2"), requested=None, rebuild=False)
        self.assertFalse(choice.build)

    def test_dot_release_upstream_is_new(self) -> None:
        choice = d.choose(upstream="159.0.1", releases=releases("v159.0", "v159.0-r2"), requested=None, rebuild=False)
        self.assertTrue(choice.build)
        self.assertEqual(choice.tag, "v159.0.1")

    def test_numeric_comparison_of_dot_releases(self) -> None:
        self.assertTrue(d.choose(upstream="159.0.10", releases=releases("v159.0.9"), requested=None, rebuild=False).build)
        self.assertFalse(d.choose(upstream="159.0.9", releases=releases("v159.0.10"), requested=None, rebuild=False).build)

    def test_new_major_version_beats_an_older_dot_release(self) -> None:
        choice = d.choose(upstream="160.0", releases=releases("v159.0.2"), requested=None, rebuild=False)
        self.assertTrue(choice.build)
        self.assertEqual(choice.firefox, "160.0")

    def test_older_upstream_than_the_latest_release_is_nothing_new(self) -> None:
        self.assertFalse(d.choose(upstream="159.0", releases=releases("v159.0.2"), requested=None, rebuild=False).build)

    def test_requested_version_overrides_detection(self) -> None:
        choice = d.choose(upstream="159.0", releases=releases("v159.0"), requested="150.0", rebuild=False)
        self.assertTrue(choice.build)
        self.assertEqual(choice.firefox, "150.0")

    def test_requested_version_that_already_has_a_release_is_skipped_without_rebuild(self) -> None:
        choice = d.choose(upstream="160.0", releases=releases("v159.0"), requested="159.0", rebuild=False)
        self.assertFalse(choice.build)
        self.assertIn("already has release v159.0", choice.reason)

    def test_requested_version_is_validated(self) -> None:
        with self.assertRaises(VersionError):
            d.choose(upstream="159.0", releases=[], requested="159", rebuild=False)
        with self.assertRaises(VersionError):
            d.choose(upstream="159.0", releases=[], requested="latest", rebuild=False)

    def test_rebuild_of_an_existing_release_is_r2(self) -> None:
        choice = d.choose(upstream="159.0", releases=releases("v159.0"), requested=None, rebuild=True)
        self.assertTrue(choice.build)
        self.assertEqual((choice.rebuild, choice.embermine_version, choice.tag), (2, "159.0-r2", "v159.0-r2"))

    def test_rebuild_takes_one_more_than_the_highest_existing_number(self) -> None:
        choice = d.choose(upstream="159.0", releases=releases("v159.0", "v159.0-r2", "v159.0-r3"), requested=None, rebuild=True)
        self.assertEqual(choice.rebuild, 4)
        choice = d.choose(upstream="159.0", releases=releases("v159.0", "v159.0-r3"), requested=None, rebuild=True)
        self.assertEqual(choice.rebuild, 4)

    def test_rebuild_up_to_r9_is_allowed(self) -> None:
        existing = releases("v159.0", *[f"v159.0-r{n}" for n in range(2, 9)])
        choice = d.choose(upstream="159.0", releases=existing, requested=None, rebuild=True)
        self.assertEqual(choice.rebuild, 9)
        self.assertEqual(choice.tag, "v159.0-r9")

    def test_rebuild_that_would_need_r10_is_rejected(self) -> None:
        existing = releases("v159.0", *[f"v159.0-r{n}" for n in range(2, 10)])
        with self.assertRaisesRegex(d.DetectError, "r10"):
            d.choose(upstream="159.0", releases=existing, requested=None, rebuild=True)

    def test_rebuild_without_any_existing_release_is_a_plain_release(self) -> None:
        choice = d.choose(upstream="159.0", releases=[], requested=None, rebuild=True)
        self.assertTrue(choice.build)
        self.assertEqual((choice.rebuild, choice.tag), (None, "v159.0"))

    def test_rebuild_of_a_requested_version(self) -> None:
        choice = d.choose(upstream="160.0", releases=releases("v159.0"), requested="159.0", rebuild=True)
        self.assertEqual((choice.firefox, choice.rebuild), ("159.0", 2))

    def test_rebuild_of_a_detected_version_uses_the_upstream_version(self) -> None:
        choice = d.choose(upstream="159.0", releases=releases("v159.0", "v159.0-r2"), requested=None, rebuild=True)
        self.assertEqual(choice.firefox, "159.0")
        self.assertEqual(choice.rebuild, 3)


class GateTests(unittest.TestCase):
    def new_release(self) -> d.Choice:
        return d.choose(upstream="159.0", releases=[], requested=None, rebuild=False)

    def test_only_the_exact_value_true_opens_the_gate(self) -> None:
        for value in ("true", "True", "TRUE", "1", "yes", "false", "", "tru"):
            with self.subTest(value=value):
                self.assertEqual(d.is_gate_open(value), value == "true")

    def test_schedule_while_gated_detects_only(self) -> None:
        outcome = d.apply_gate(self.new_release(), event="schedule", gate_open=False, dry_run_input="")
        self.assertFalse(outcome.build)
        self.assertFalse(outcome.publish)
        self.assertIn("detection only", outcome.reason)
        self.assertIn("build skipped", outcome.reason)

    def test_schedule_with_the_gate_open_builds_and_publishes(self) -> None:
        outcome = d.apply_gate(self.new_release(), event="schedule", gate_open=True, dry_run_input="")
        self.assertTrue(outcome.build)
        self.assertTrue(outcome.publish)

    def test_schedule_with_nothing_new_never_builds(self) -> None:
        choice = d.choose(upstream="159.0", releases=releases("v159.0"), requested=None, rebuild=False)
        for gate in (True, False):
            with self.subTest(gate=gate):
                outcome = d.apply_gate(choice, event="schedule", gate_open=gate, dry_run_input="")
                self.assertFalse(outcome.build)
                self.assertFalse(outcome.publish)

    def test_dispatch_dry_run_builds_without_publishing(self) -> None:
        outcome = d.apply_gate(self.new_release(), event="workflow_dispatch", gate_open=False, dry_run_input="true")
        self.assertTrue(outcome.build)
        self.assertFalse(outcome.publish)

    def test_dispatch_dry_run_is_the_default_while_gated(self) -> None:
        outcome = d.apply_gate(self.new_release(), event="workflow_dispatch", gate_open=True, dry_run_input="")
        self.assertTrue(outcome.build)
        self.assertFalse(outcome.publish)

    def test_dispatch_without_dry_run_is_still_gated_while_the_gate_is_closed(self) -> None:
        outcome = d.apply_gate(self.new_release(), event="workflow_dispatch", gate_open=False, dry_run_input="false")
        self.assertTrue(outcome.build)
        self.assertFalse(outcome.publish)
        self.assertIn("gated", outcome.reason)

    def test_dispatch_publishes_only_when_the_gate_is_open_and_dry_run_is_off(self) -> None:
        outcome = d.apply_gate(self.new_release(), event="workflow_dispatch", gate_open=True, dry_run_input="false")
        self.assertTrue(outcome.build)
        self.assertTrue(outcome.publish)

    def test_dispatch_of_a_version_that_is_already_released_does_nothing(self) -> None:
        choice = d.choose(upstream="159.0", releases=releases("v159.0"), requested="159.0", rebuild=False)
        outcome = d.apply_gate(choice, event="workflow_dispatch", gate_open=True, dry_run_input="false")
        self.assertFalse(outcome.build)
        self.assertFalse(outcome.publish)

    def test_dry_run_flag_parses_true_and_false_strings(self) -> None:
        self.assertTrue(d.is_dry_run("true"))
        self.assertTrue(d.is_dry_run(""))
        self.assertFalse(d.is_dry_run("false"))


if __name__ == "__main__":
    unittest.main()
