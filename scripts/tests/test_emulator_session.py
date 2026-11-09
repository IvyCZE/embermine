import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.emulator import flows_browse
from scripts.emulator.device import MIN_PNG_BYTES, Device
from scripts.emulator.naming import ScreenIndex
from scripts.emulator.session import LaunchError, Session
from scripts.tests.emulator_fakes import FakeAdb, hierarchy, node, tty_output

PACKAGE = "yt.ivy.embermine"
FOCUSED = f"mCurrentFocus=Window{{1a2b u0 {PACKAGE}/org.mozilla.fenix.HomeActivity}}"
LAUNCHER_FOCUSED = "mCurrentFocus=Window{3c4d u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity}"
PNG = b"\x89PNG\r\n\x1a\n"
BLANK_FRAME = PNG + b"0" * 100
REAL_FRAME = PNG + b"0" * MIN_PNG_BYTES


class FakeClock:
    """Time that only moves when something sleeps, so polling loops finish at once."""

    def __init__(self) -> None:
        self.now_seconds = 0.0

    def now(self) -> float:
        return self.now_seconds

    def sleep(self, seconds: float) -> None:
        self.now_seconds += seconds


class LaunchAdb(FakeAdb):
    """Records adb calls. The app gets window focus once `focus_after` monkey launches have been sent."""

    def __init__(self, focus_after: int = 1, wait_result: subprocess.CompletedProcess | None = None) -> None:
        super().__init__()
        self.focus_after = focus_after
        self.monkeys = 0
        self.runs: list[tuple[str, ...]] = []
        self.wait_result = wait_result

    def run(self, *args: str, timeout: float = 60) -> subprocess.CompletedProcess[bytes]:
        self.runs.append(args)
        if args == ("wait-for-device",):
            if self.wait_result is not None:
                if isinstance(self.wait_result, BaseException):
                    raise self.wait_result
                return self.wait_result
            return subprocess.CompletedProcess(args, 0, b"", b"")
        return super().run(*args, timeout=timeout)

    def shell(self, command: str, timeout: float = 60) -> str:
        self.commands.append(command)
        if command.startswith("monkey -p"):
            self.monkeys += 1
            return ""
        if "dumpsys window" in command:
            return FOCUSED if self.monkeys >= self.focus_after else LAUNCHER_FOCUSED
        return ""


def make_session(adb: FakeAdb, clock: FakeClock, out: Path) -> Session:
    dev = Device(adb, dump_dir=None, sleep=clock.sleep, clock=clock.now, log=lambda _: None)
    return Session(dev, PACKAGE, "light", out, out, ScreenIndex(title="test"), dynamic=True)


class LaunchFromLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeClock()
        self.out = Path(self.tmp.name)

    def launch(self, adb: LaunchAdb) -> Session:
        session = make_session(adb, self.clock, self.out)
        session.launch_from_launcher()
        return session

    def test_waits_for_the_device_first_and_launches_once_when_the_app_gets_focus(self) -> None:
        adb = LaunchAdb(focus_after=1)
        self.launch(adb)
        self.assertEqual(adb.runs[0], ("wait-for-device",))
        self.assertEqual(adb.monkeys, 1)

    def test_a_launch_without_window_focus_is_repeated_once(self) -> None:
        adb = LaunchAdb(focus_after=2)
        self.launch(adb)
        self.assertEqual(adb.monkeys, 2)

    def test_no_focus_after_two_launches_is_a_launch_error(self) -> None:
        adb = LaunchAdb(focus_after=99)
        with self.assertRaisesRegex(LaunchError, "after 2 launches"):
            self.launch(adb)
        self.assertEqual(adb.monkeys, 2)

    def test_a_device_that_does_not_come_back_is_a_launch_error(self) -> None:
        adb = LaunchAdb(wait_result=subprocess.TimeoutExpired(["adb"], 120))
        with self.assertRaisesRegex(LaunchError, "did not see the device"):
            self.launch(adb)
        self.assertEqual(adb.monkeys, 0)

    def test_a_failed_device_wait_is_a_launch_error(self) -> None:
        adb = LaunchAdb(wait_result=subprocess.CompletedProcess(("wait-for-device",), 1, b"", b"error"))
        with self.assertRaisesRegex(LaunchError, "exit code 1"):
            self.launch(adb)
        self.assertEqual(adb.monkeys, 0)


class OnboardingFirstScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeClock()
        self.out = Path(self.tmp.name)

    def session(self, adb: "FramesAdb") -> Session:
        return make_session(adb, self.clock, self.out)

    def test_the_capture_waits_for_the_onboarding_buttons_before_the_frame_is_taken(self) -> None:
        loading = tty_output(hierarchy(node(text="Loading")))
        onboarding = tty_output(hierarchy(node(text="Continue", clickable=True)))
        adb = FramesAdb(frames=[REAL_FRAME], dumps=[loading, onboarding])
        session = self.session(adb)
        flows_browse.onboarding_first_screen(session)
        self.assertEqual([e.status for e in session.index.entries], ["OK"])
        self.assertEqual(adb.screencaps, 1)
        self.assertGreaterEqual(self.clock.now_seconds, 1.0)

    def test_a_blank_first_frame_is_taken_again_a_few_seconds_later(self) -> None:
        onboarding = tty_output(hierarchy(node(text="Continue", clickable=True)))
        adb = FramesAdb(frames=[BLANK_FRAME, REAL_FRAME], dumps=[onboarding])
        session = self.session(adb)
        flows_browse.onboarding_first_screen(session)
        self.assertEqual([e.status for e in session.index.entries], ["OK"])
        self.assertEqual(adb.screencaps, 2)
        self.assertTrue((self.out / "onboarding_dynamic-on_light.png").exists())

    def test_frames_that_stay_blank_are_missing_with_the_blank_reason(self) -> None:
        onboarding = tty_output(hierarchy(node(text="Continue", clickable=True)))
        adb = FramesAdb(frames=[BLANK_FRAME], dumps=[onboarding])
        session = self.session(adb)
        flows_browse.onboarding_first_screen(session)
        # every attempt is one screencap; the failure evidence adds one more
        self.assertGreaterEqual(adb.screencaps, flows_browse.FRAME_ATTEMPTS)
        [entry] = session.index.entries
        self.assertEqual(entry.status, "MISSING")
        self.assertIn("looks blank", entry.detail)
        self.assertFalse((self.out / "onboarding_dynamic-on_light.png").exists())

    def test_an_onboarding_view_that_never_renders_is_missing_and_no_frame_is_saved(self) -> None:
        loading = tty_output(hierarchy(node(text="Loading")))
        adb = FramesAdb(frames=[REAL_FRAME], dumps=[loading])
        session = self.session(adb)
        flows_browse.onboarding_first_screen(session)
        [entry] = session.index.entries
        self.assertEqual(entry.status, "MISSING")
        self.assertIn("did not render", entry.detail)
        self.assertFalse((self.out / "onboarding_dynamic-on_light.png").exists())


class FramesAdb(FakeAdb):
    """Serves one screencap per call from `frames` (the last frame repeats) and counts them."""

    def __init__(self, frames: list[bytes], dumps: list[str]) -> None:
        super().__init__(dumps=dumps)
        self.frames = list(frames)
        self.screencaps = 0

    def run(self, *args: str, timeout: float = 60) -> subprocess.CompletedProcess[bytes]:
        if args[:2] == ("exec-out", "screencap"):
            self.screencaps += 1
            frame = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
            return subprocess.CompletedProcess(args, 0, frame, b"")
        return super().run(*args, timeout=timeout)


if __name__ == "__main__":
    unittest.main()
