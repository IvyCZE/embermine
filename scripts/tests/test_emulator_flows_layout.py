import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

from scripts.emulator import flows_layout, run
from scripts.emulator.device import StepError


def fake_session(calls: list[str]) -> SimpleNamespace:
    @contextmanager
    def capture(stem: str, label: str | None = None) -> Iterator[SimpleNamespace]:
        calls.append(f"capture {stem}")
        try:
            yield SimpleNamespace(take=lambda **_: None)
        except Exception:
            calls.append(f"missing {stem}")

    return SimpleNamespace(server="http://10.0.2.2:8765", log=lambda _: None, capture=capture)


def fake_set_option(calls: list[str], fail_on: tuple[str, ...] = ()):
    def set_option(s: SimpleNamespace, option: str) -> None:
        calls.append(f"set {option}")
        if option in fail_on:
            raise StepError(f"{option} not found")

    return set_option


class BottomNavigationBarFlowTests(unittest.TestCase):
    def run_flow(self, fail_on: tuple[str, ...] = ()) -> tuple[list[str], BaseException | None]:
        calls: list[str] = []
        error: BaseException | None = None
        with (
            mock.patch.object(flows_layout, "set_customize_option", fake_set_option(calls, fail_on)),
            mock.patch.object(flows_layout, "go_home"),
            mock.patch.object(flows_layout, "load_page"),
        ):
            try:
                flows_layout.bottom_navigation_bar(fake_session(calls))
            except StepError as exc:
                error = exc
        return calls, error

    def test_captures_default_back_and_home_shortcuts_then_restores_the_defaults(self) -> None:
        calls, error = self.run_flow()
        self.assertIsNone(error)
        self.assertEqual(
            calls,
            [
                "set Expanded",
                "capture bottom-navigation-bar",
                "capture bottom-navigation-bar-back",
                "set Back",
                "capture bottom-navigation-bar-home",
                "set Homepage",
                "set Add bookmark",
                "set Simple",
            ],
        )

    def test_a_failed_shortcut_is_recorded_missing_and_the_homepage_capture_and_restores_still_run(self) -> None:
        calls, error = self.run_flow(fail_on=("Back",))
        self.assertIsNone(error)
        self.assertEqual(
            calls,
            [
                "set Expanded",
                "capture bottom-navigation-bar",
                "capture bottom-navigation-bar-back",
                "set Back",
                "missing bottom-navigation-bar-back",
                "capture bottom-navigation-bar-home",
                "set Homepage",
                "set Add bookmark",
                "set Simple",
            ],
        )

    def test_failing_to_expand_the_bar_restores_only_the_simple_layout(self) -> None:
        calls, error = self.run_flow(fail_on=("Expanded",))
        self.assertIsInstance(error, StepError)
        self.assertEqual(calls, ["set Expanded", "set Simple"])

    def test_bottom_navigation_flow_expects_the_default_back_and_home_captures(self) -> None:
        flow = next(f for f in run.flow_list() if f.name == "bottom navigation bar")
        self.assertEqual(
            [stem for stem, _, _ in flow.expected],
            ["bottom-navigation-bar", "bottom-navigation-bar-back", "bottom-navigation-bar-home"],
        )


if __name__ == "__main__":
    unittest.main()
