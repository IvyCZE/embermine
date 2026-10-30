import unittest
from pathlib import Path
import tempfile

from scripts.emulator.device import Device, MIN_PNG_BYTES, PNG_MAGIC, StepError
from scripts.emulator.uidump import Selector
from scripts.tests.emulator_fakes import FakeAdb, hierarchy, node, tty_output


def make_device(adb: FakeAdb, **kwargs) -> Device:
    clock = iter(float(i) for i in range(10_000))
    return Device(adb, sleep=lambda _: None, clock=lambda: next(clock), log=lambda _: None, **kwargs)  # type: ignore[arg-type]


HOME = tty_output(hierarchy(node(text="Search or enter address", bounds="[100,2100][900,2200]"), node(desc="More options", bounds="[940,2100][1040,2200]")))
ANR = tty_output(
    hierarchy(
        node(text="Firefox isn't responding", package="android"),
        node(text="Close app", bounds="[200,1200][500,1300]", clickable=True, package="android"),
        node(text="Wait", bounds="[600,1200][900,1300]", clickable=True, package="android"),
    )
)


class DumpTests(unittest.TestCase):
    def test_dump_retries_while_uiautomator_has_no_idle_state(self) -> None:
        adb = FakeAdb(["ERROR: could not get idle state.\n", "", HOME])
        nodes = make_device(adb).dump("home")
        self.assertEqual(len(nodes), 3)

    def test_dump_gives_up_after_the_retries(self) -> None:
        adb = FakeAdb(["ERROR: could not get idle state.\n"])
        with self.assertRaises(StepError) as ctx:
            make_device(adb).dump("home", retries=3)
        self.assertIn("3 times", str(ctx.exception))

    def test_dumps_are_saved_only_on_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dev = make_device(FakeAdb([HOME]), dump_dir=Path(tmp))
            dev.dump("quiet")
            self.assertEqual(list(Path(tmp).iterdir()), [])
            dev.dump("shot 04 homepage", save=True)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["001-shot-04-homepage.xml"])


class TapTests(unittest.TestCase):
    def test_tap_hits_the_center_of_the_first_matching_selector(self) -> None:
        adb = FakeAdb([HOME])
        node_ = make_device(adb).tap(Selector(desc="More options"))
        self.assertEqual(node_.desc, "More options")
        self.assertIn("input tap 990 2150", adb.commands)

    def test_tap_raises_with_the_selectors_when_nothing_matches(self) -> None:
        with self.assertRaises(StepError) as ctx:
            make_device(FakeAdb([HOME])).tap(Selector(text="Nope"), timeout=3)
        self.assertIn("not found", str(ctx.exception))
        self.assertIn("Nope", str(ctx.exception))

    def test_wait_for_polls_until_the_element_appears(self) -> None:
        adb = FakeAdb([tty_output(hierarchy()), tty_output(hierarchy()), HOME])
        self.assertIsNotNone(make_device(adb).wait_for(Selector(desc="More options"), timeout=10))

    def test_try_tap_returns_false_instead_of_raising(self) -> None:
        self.assertFalse(make_device(FakeAdb([HOME])).try_tap(Selector(text="Nope"), timeout=2))

    def test_scroll_to_swipes_until_found(self) -> None:
        empty = tty_output(hierarchy())
        adb = FakeAdb([empty, empty, HOME], shell_answers={"wm size": "Physical size: 1080x2400"})
        found = make_device(adb).scroll_to(Selector(desc="More options"), max_swipes=5)
        self.assertEqual(found.desc, "More options")
        self.assertEqual(sum(c.startswith("input swipe") for c in adb.commands), 2)


class DialogTests(unittest.TestCase):
    def test_not_responding_dialog_is_dismissed_with_wait(self) -> None:
        adb = FakeAdb([ANR, HOME])
        dismissed = make_device(adb).sweep_dialogs()
        self.assertEqual(len(dismissed), 1)
        self.assertIn("-> Wait", dismissed[0])
        self.assertIn("input tap 750 1250", adb.commands)

    def test_no_dialog_means_no_taps(self) -> None:
        adb = FakeAdb([HOME])
        self.assertEqual(make_device(adb).sweep_dialogs(), [])
        self.assertFalse(any(c.startswith("input tap") for c in adb.commands))


class ScreenshotTests(unittest.TestCase):
    def test_blank_or_non_png_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.png"
            for png in (b"not a png", PNG_MAGIC + b"\0" * 100):
                with self.subTest(size=len(png)), self.assertRaises(StepError):
                    make_device(FakeAdb(png=png)).screenshot(target)
            self.assertFalse(target.exists())

    def test_real_sized_png_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.png"
            make_device(FakeAdb(png=PNG_MAGIC + b"\1" * MIN_PNG_BYTES)).screenshot(target)
            self.assertTrue(target.is_file())
