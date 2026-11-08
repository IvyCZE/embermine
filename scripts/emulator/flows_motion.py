"""Captures of things that move: the page-load line and pull-to-refresh, for both toolbar positions."""
from __future__ import annotations

from collections.abc import Callable

from scripts.emulator import targets as t
from scripts.emulator import uidump
from scripts.emulator.flows_browse import go_home
from scripts.emulator.flows_settings import open_row, open_settings
from scripts.emulator.session import Session
from scripts.emulator.uidump import Selector


def toolbar_at_top(s: Session) -> bool:
    nodes = s.dev.dump("toolbar-position")
    button = uidump.find_first(nodes, t.MENU_BUTTON)
    if button is None:
        raise RuntimeError("menu button not found, cannot tell where the toolbar is")
    return button.center[1] < uidump.screen_size(nodes)[1] // 2


def set_toolbar_position(s: Session, position: str) -> None:
    """Settings > Customize > Toolbar: Top or Bottom."""
    open_settings(s)
    open_row(s, r"Customize")
    row = s.dev.scroll_to(Selector(text=position.capitalize()), max_swipes=6)
    s.dev.tap_node(row)
    s.dev.sleep(1.5)
    s.log(f"toolbar position set to {position}")
    s.dev.back()
    s.dev.back()
    s.dev.sleep(1.0)


PULL_START_FRACTION = 0.30
PULL_PAUSE_FRACTION = 0.37
PULL_RELEASE_FRACTION = 0.50
PULL_STEPS = 6


def page_load(s: Session, position: str) -> None:
    """The page-load line while a page is still loading and after it finished."""
    with s.capture(f"page-load-{position}-loading", label=f"page load, {position} toolbar, mid-load") as shot:
        go_home(s)
        s.open_url(f"{s.server}/slow?pos={position}")
        s.dev.sleep(4.0)
        shot.take(settle=0.5)
    with s.capture(f"page-load-{position}-loaded", label=f"page load, {position} toolbar, after load") as shot:
        s.open_url(f"{s.server}/page?pos={position}")
        s.wait_page("10.0.2.2", timeout=30)
        s.dev.sleep(5.0)
        shot.take(settle=0.5)


def _touch(s: Session, action: str, x: int, y: int) -> None:
    s.dev.adb.shell(f"input motionevent {action} {x} {y}")


def _drag_to(s: Session, x: int, y_from: int, y_to: int) -> None:
    for step in range(1, PULL_STEPS + 1):
        _touch(s, "MOVE", x, y_from + (y_to - y_from) * step // PULL_STEPS)
        s.dev.sleep(0.15)


def pull_to_refresh(s: Session, position: str) -> None:
    """Hold the page part way down and photograph the pull, then release past the trigger so the reload starts."""
    with s.capture(f"pull-to-refresh-{position}-pulling", label=f"pull-to-refresh, {position} toolbar, during pull") as pulling:
        s.open_url(f"{s.server}/reset?pos={position}")
        s.dev.sleep(1.0)
        s.open_url(f"{s.server}/refresh?pos={position}")
        s.wait_page("10.0.2.2", timeout=30)
        s.dev.sleep(5.0)
        width, height = s.dev.screen_size()
        x = width // 2
        top, pause, release = (int(height * f) for f in (PULL_START_FRACTION, PULL_PAUSE_FRACTION, PULL_RELEASE_FRACTION))
        _touch(s, "DOWN", x, top)
        try:
            _drag_to(s, x, top, pause)
            s.dev.sleep(0.5)
            pulling.take(settle=0.0)
            _drag_to(s, x, pause, release)
        finally:
            _touch(s, "UP", x, release)
    with s.capture(f"pull-to-refresh-{position}-reloading", label=f"pull-to-refresh, {position} toolbar, while reloading") as reloading:
        s.dev.sleep(0.8)
        reloading.take(settle=0.0)


def both_positions(s: Session, step: Callable[[Session, str], None]) -> None:
    """Run `step` with the toolbar where it is, then again after moving it to the other side."""
    go_home(s)
    first = "top" if toolbar_at_top(s) else "bottom"
    other = "bottom" if first == "top" else "top"
    step(s, first)
    set_toolbar_position(s, other)
    go_home(s)
    step(s, other)
