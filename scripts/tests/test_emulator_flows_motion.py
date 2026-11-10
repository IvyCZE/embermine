import contextlib
import unittest
from collections.abc import Iterator
from types import SimpleNamespace
from unittest import mock

from scripts.emulator import flows_motion

SERVER = "http://10.0.2.2:8765"


def fake_session(opened: list[str], *, at_top: bool = True) -> SimpleNamespace:
    @contextlib.contextmanager
    def capture(screen: str, label: str | None = None) -> Iterator[SimpleNamespace]:
        yield SimpleNamespace(take=lambda settle=1.5, note="": None)

    return SimpleNamespace(
        server=SERVER,
        dev=SimpleNamespace(sleep=lambda _: None),
        log=lambda _: None,
        capture=capture,
        open_url=opened.append,
        wait_page=lambda *args, **kwargs: None,
        toolbar_at_top=lambda: at_top,
    )


class SwitchStateKeyTests(unittest.TestCase):
    def test_suffixes_become_a_query_value(self) -> None:
        self.assertEqual(flows_motion.state_key("-after-toggle-off"), "after-toggle-off")
        self.assertEqual(flows_motion.state_key("-after-restart-on"), "after-restart-on")

    def test_no_suffix_gives_no_key(self) -> None:
        self.assertEqual(flows_motion.state_key(""), "")

    def test_odd_characters_are_normalized(self) -> None:
        self.assertEqual(flows_motion.state_key("-After Toggle/Off-"), "after-toggle-off")


class PageLoadUrlTests(unittest.TestCase):
    def load(self, suffix: str, position: str = "top", *, after_load: bool = False) -> list[str]:
        opened: list[str] = []
        s = fake_session(opened)
        with mock.patch.object(flows_motion, "go_home"):
            flows_motion.page_load(s, position, suffix=suffix, after_load=after_load)
        return opened

    def test_each_switch_state_requests_its_own_stalled_load(self) -> None:
        suffixes = ("-after-toggle-off", "-after-toggle-on", "-after-restart-off", "-after-restart-on")
        urls = {suffix: self.load(suffix)[0] for suffix in suffixes}
        self.assertEqual(len(set(urls.values())), len(suffixes), urls)
        for suffix, url in urls.items():
            self.assertIn(f"/slow?pos=top&state={flows_motion.state_key(suffix)}", url)

    def test_every_switch_state_requests_its_own_loaded_page_too(self) -> None:
        off = self.load("-after-toggle-off", after_load=True)
        on = self.load("-after-toggle-on", after_load=True)
        self.assertEqual(off[1], f"{SERVER}/page?pos=top&state=after-toggle-off")
        self.assertEqual(on[1], f"{SERVER}/page?pos=top&state=after-toggle-on")

    def test_the_unsuffixed_motion_flow_keeps_the_plain_urls(self) -> None:
        self.assertEqual(self.load("", after_load=True), [f"{SERVER}/slow?pos=top", f"{SERVER}/page?pos=top"])
        self.assertEqual(self.load("", position="bottom"), [f"{SERVER}/slow?pos=bottom"])


class PullToRefreshUrlTests(unittest.TestCase):
    def test_each_switch_state_resets_and_reloads_its_own_url(self) -> None:
        def refresh(suffix: str) -> list[str]:
            opened: list[str] = []
            s = fake_session(opened)
            s.dev.adb = SimpleNamespace(shell=lambda _: None)
            s.dev.screen_size = lambda: (1080, 2400)
            with mock.patch.object(flows_motion, "go_home"):
                flows_motion.pull_to_refresh(s, "top", suffix=suffix, reloading=False)
            return opened

        off = refresh("-after-toggle-off")
        on = refresh("-after-toggle-on")
        self.assertEqual(off[:2], [f"{SERVER}/reset?pos=top&state=after-toggle-off", f"{SERVER}/refresh?pos=top&state=after-toggle-off"])
        self.assertEqual(on[:2], [f"{SERVER}/reset?pos=top&state=after-toggle-on", f"{SERVER}/refresh?pos=top&state=after-toggle-on"])


class ToolbarPositionTests(unittest.TestCase):
    def test_top_is_established_when_the_toolbar_is_at_the_bottom(self) -> None:
        s = fake_session([], at_top=False)
        states = iter([False, True])
        s.toolbar_at_top = lambda: next(states)
        with (
            mock.patch.object(flows_motion, "go_home") as go_home,
            mock.patch.object(flows_motion, "set_toolbar_position") as set_position,
        ):
            flows_motion.ensure_toolbar_position(s, "top")
        set_position.assert_called_once_with(s, "top")
        self.assertEqual(go_home.call_count, 2)

    def test_a_toolbar_already_at_the_top_costs_no_settings_trip(self) -> None:
        s = fake_session([], at_top=True)
        with (
            mock.patch.object(flows_motion, "go_home"),
            mock.patch.object(flows_motion, "set_toolbar_position") as set_position,
        ):
            flows_motion.ensure_toolbar_position(s, "top")
        set_position.assert_not_called()

    def test_a_toolbar_that_stays_on_the_other_side_is_an_error(self) -> None:
        s = fake_session([], at_top=False)
        with (
            mock.patch.object(flows_motion, "go_home"),
            mock.patch.object(flows_motion, "set_toolbar_position"),
        ):
            with self.assertRaisesRegex(RuntimeError, "did not move to the top"):
                flows_motion.ensure_toolbar_position(s, "top")

    def test_an_unknown_position_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            flows_motion.ensure_toolbar_position(fake_session([]), "middle")


if __name__ == "__main__":
    unittest.main()
