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
