import dataclasses
import time
import unittest
from types import SimpleNamespace

from scripts.emulator import flows_settings, run, uidump
from scripts.emulator.device import StepError
from scripts.emulator.naming import ScreenIndex
from scripts.tests.emulator_fakes import hierarchy, node

SWITCH_ID = "org.mozilla.firefox:id/switchWidget"


def switch(top: int, checked: bool) -> str:
    xml = node(rid=SWITCH_ID, bounds=f"[900,{top}][1000,{top + 60}]", cls="android.widget.Switch")
    return xml.replace('checked="false"', f'checked="{str(checked).lower()}"')


def customize(*nodes: str) -> list[uidump.Node]:
    return uidump.parse(hierarchy(*nodes))


def session(nodes: list[uidump.Node]) -> SimpleNamespace:
    return SimpleNamespace(dev=SimpleNamespace(dump=lambda label="", **_: nodes), log=lambda _: None)


def row(top: int = 560) -> str:
    return node(text="Use wallpaper colors", bounds=f"[40,{top}][860,{top + 80}]", clickable=True)


class WallpaperColorsSwitchTests(unittest.TestCase):
    def test_reads_the_checked_switch_next_to_its_row(self) -> None:
        nodes = customize(row(), switch(580, checked=True), switch(1500, checked=False))
        self.assertTrue(flows_settings.wallpaper_colors_on(session(nodes)))

    def test_unchecked_switch_next_to_the_row_is_off(self) -> None:
        nodes = customize(row(), switch(580, checked=False), switch(1500, checked=True))
        self.assertFalse(flows_settings.wallpaper_colors_on(session(nodes)))

    def test_missing_row_is_a_step_error(self) -> None:
        with self.assertRaises(StepError):
            flows_settings.wallpaper_colors_on(session(customize(switch(580, checked=True))))

    def test_require_names_the_state_that_was_found(self) -> None:
        nodes = customize(row(), switch(580, checked=True))
        with self.assertRaisesRegex(StepError, "is on, expected off"):
            flows_settings.require_wallpaper_colors(session(nodes), on=False)
        flows_settings.require_wallpaper_colors(session(nodes), on=True)


class WallpaperColorsToggleFlowTests(unittest.TestCase):
    def toggle_flow(self) -> run.Flow:
        return next(f for f in run.flow_list() if f.name == "wallpaper colors toggle")

    def test_toggle_flow_only_runs_in_the_accent_on_pass(self) -> None:
        on = {f.name for f in run.flow_list("light", "on")}
        off = {f.name for f in run.flow_list("light", "off")}
        self.assertEqual(on - off, {"wallpaper colors toggle"})

    def test_toggle_captures_have_a_switch_state_for_every_expected_stem(self) -> None:
        flow = self.toggle_flow()
        stems = [stem for stem, _, _ in flow.expected]
        self.assertEqual(stems, [stem for stem, _, _ in flows_settings.WALLPAPER_COLORS_CAPTURES])
        self.assertEqual(flow.states, {stem: on for stem, on, _ in flows_settings.WALLPAPER_COLORS_CAPTURES})
        self.assertEqual(sorted(flow.states.values()), [False, False, True, True])

    def test_missing_toggle_captures_are_named_by_their_own_switch_state(self) -> None:
        def fail(_: object) -> None:
            raise StepError("row gone")

        flow = dataclasses.replace(self.toggle_flow(), run=fail)
        index = ScreenIndex(title="test")
        s = SimpleNamespace(
            index=index,
            theme="light",
            dynamic=True,
            log=lambda _: None,
            ensure_normal=lambda: None,
            dev=SimpleNamespace(sweep_dialogs=lambda: []),
        )
        run.run_flow(s, flow, deadline=time.monotonic() + 60)
        files = {entry.file: entry.status for entry in index.entries}
        self.assertEqual(files["customize-after-toggle-off_dynamic-off_light.png"], "MISSING")
        self.assertEqual(files["customize-after-toggle-on_dynamic-on_light.png"], "MISSING")
        self.assertEqual(files["customize-after-restart-off_dynamic-off_light.png"], "MISSING")
        self.assertEqual(files["customize-after-restart-on_dynamic-on_light.png"], "MISSING")


if __name__ == "__main__":
    unittest.main()
