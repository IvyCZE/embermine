"""State shared by all capture flows: the app under test, the output folders and fail-soft captures."""
from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from scripts.emulator import uidump
from scripts.emulator.targets import ADDRESS_BAR, HOMEPAGE_BAR, HOMEPAGE_VIEW, PRIVATE_BUTTON, TAB_COUNTER_DESC
from scripts.emulator.device import Device, StepError
from scripts.emulator.naming import ScreenIndex, capture_name
from scripts.emulator.uidump import Node, Selector


class LaunchError(RuntimeError):
    """The app could not be installed or started. This one fails the whole job."""


class Shot:
    """Handle given to the body of a capture block."""

    def __init__(self, session: Session, file: str) -> None:
        self.session = session
        self.file = file
        self.taken = False
        self.note = ""

    def take(self, settle: float = 1.5, note: str = "") -> None:
        self.session.dev.sleep(settle)
        swept = self.session.dev.sweep_dialogs()
        if swept:
            self.session.dev.sleep(1.0)
        self.session.dev.screenshot(self.session.out / self.file)
        self.taken = True
        try:
            self.session.dev.dump(f"shot-{self.file}", retries=2, save=True)
        except StepError:
            pass
        self.note = "; ".join(filter(None, [note, f"dismissed dialog: {', '.join(swept)}" if swept else ""]))
        self.session.log(f"shot {self.file}")


@dataclass
class Session:
    dev: Device
    package: str
    theme: str
    out: Path
    debug: Path
    index: ScreenIndex
    dynamic: bool = False
    server: str = "http://10.0.2.2:8765"
    visited: list[str] = field(default_factory=list)
    in_private: bool = False
    private_screenshots: bool = False
    _t0: float = field(default_factory=time.monotonic)

    def log(self, message: str) -> None:
        print(f"[{time.monotonic() - self._t0:7.1f}s] {message}", flush=True)

    # ---- fail-soft captures -------------------------------------------------------------------

    @contextmanager
    def capture(
        self,
        screen: str,
        *,
        private: bool = False,
        label: str | None = None,
        file: str | None = None,
        combination: str | None = None,
    ) -> Iterator[Shot]:
        """Run one capture. Any failure is recorded as MISSING with the reason and the walk goes on.

        `screen` is the file name stem (with its NN- prefix when the screen has one); `label` is the human
        description shown in the index. `file` and `combination` override the standard naming for captures
        that do not belong to the dynamic on/off matrix.
        """
        if file is None:
            file = capture_name(screen, theme=self.theme, dynamic=self.dynamic, private=private)
        if combination is None:
            combination = f"dynamic-{'on' if self.dynamic else 'off'} {self.theme}{' private' if private else ''}"
        shot = Shot(self, file)
        name = label or screen
        try:
            yield shot
        except Exception as exc:  # noqa: BLE001 - every failure of one screen must stay local to it
            reason = f"{type(exc).__name__}: {exc}"
            self.log(f"MISSING {file}: {reason}")
            self._failure_evidence(file)
            self.index.missing(name, combination, file, reason)
            return
        if shot.taken:
            self.index.ok(name, combination, file, shot.note)
        else:
            self.index.missing(name, combination, file, "capture block finished without taking a screenshot")

    def _failure_evidence(self, file: str) -> None:
        try:
            self.debug.mkdir(parents=True, exist_ok=True)
            self.dev.screenshot(self.debug / f"failed-{file}")
            self.dev.dump(f"failed-{file}", retries=2, save=True)
        except Exception:  # noqa: BLE001 - best effort evidence only
            pass

    # ---- app control --------------------------------------------------------------------------

    def am_start(self, *args: str) -> str:
        out = self.dev.adb.shell("am start " + " ".join(args))
        if "Error" in out or "Exception" in out:
            raise StepError(f"am start failed: {out.strip()[:200]}")
        return out

    def focus_lines(self) -> str:
        return self.dev.adb.shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'").strip()

    def wait_focus(self, timeout: float = 60) -> bool:
        """The app owns the focused window (the splash screen counts, it is the app's own window)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.package in self.focus_lines():
                return True
            self.dev.sleep(1.0)
        return False

    def launch_from_launcher(self) -> None:
        self.dev.adb.shell(f"monkey -p {self.package} -c android.intent.category.LAUNCHER 1")
        if not self.wait_focus():
            raise LaunchError(f"{self.package} never got window focus (focus: {self.focus_lines()!r})")

    def force_stop(self) -> None:
        self.dev.adb.shell(f"am force-stop {self.package}")
        self.dev.sleep(1.5)

    def is_running(self) -> bool:
        return bool(self.dev.adb.shell(f"pidof {self.package}").strip())

    def open_url(self, url: str, *, private: bool = False) -> None:
        self.visited.append(url)
        self.in_private = self.in_private or private
        extra = "--ez private_browsing_mode true " if private else ""
        self.am_start(f"-a android.intent.action.VIEW -d '{url}' {extra}-p {self.package}")
        self.dev.sleep(1.0)

    def deep_link(self, host: str) -> None:
        self.am_start(f"-a android.intent.action.VIEW -d 'fenix://{host}' -p {self.package}")
        self.dev.sleep(1.5)

    def new_tab_home(self, *, private: bool = False) -> None:
        """Show the homepage in normal or private mode."""
        if not private:
            self.ensure_normal()
        self.deep_link("enable_private_browsing" if private else "home")
        self.in_private = self.in_private or private

    def ensure_normal(self) -> None:
        """Leave private browsing. Intents do not do it (the theme stays private), the homepage mask button does."""
        if not self.in_private:
            return
        self.deep_link("home")
        counter = uidump.find_first(self.dev.dump("browsing-mode"), TAB_COUNTER_DESC)
        if counter is not None and counter.desc.lower().startswith("private"):
            self.dev.tap(PRIVATE_BUTTON, settle=2.5)
        self.in_private = False

    # ---- screen state -------------------------------------------------------------------------

    def nodes(self, label: str = "") -> list[Node]:
        return self.dev.dump(label)

    def on_homepage(self) -> bool:
        return self.dev.visible(HOMEPAGE_VIEW) or self.dev.visible(HOMEPAGE_BAR)

    def wait_homepage(self, timeout: float = 30) -> None:
        if self.dev.wait_for(HOMEPAGE_VIEW, HOMEPAGE_BAR, timeout=timeout, label="homepage") is None:
            raise StepError("homepage address bar not found")

    def toolbar_at_top(self) -> bool:
        """True when the address bar sits in the upper half of the screen."""
        nodes = self.nodes("toolbar-position")
        bar = uidump.find_first(nodes, URL_BAR)
        if bar is None:
            raise StepError("address bar not found")
        return bar.center[1] < uidump.screen_size(nodes)[1] // 2

    def wait_page(self, host: str, timeout: float = 30) -> None:
        """Wait until the toolbar shows the page's host name."""
        sel = Selector(id="ADDRESSBAR_URL_BOX", desc=rf".*{re.escape(host)}.*")
        if self.dev.wait_for(sel, timeout=timeout, label=f"page-{host}") is None:
            raise StepError(f"toolbar never showed {host}")


URL_BAR = ADDRESS_BAR
