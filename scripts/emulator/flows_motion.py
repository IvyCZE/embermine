"""Captures of things that move: the page-load line and pull-to-refresh, for both toolbar positions."""
from __future__ import annotations

import re
from collections.abc import Callable

from scripts.emulator import targets as t
from scripts.emulator import uidump
from scripts.emulator.flows_browse import go_home
from scripts.emulator.flows_settings import open_row, open_settings
from scripts.emulator.session import Session
from scripts.emulator.uidump import Selector

TOOLBAR_POSITIONS = ("top", "bottom")
_QUERY_KEY = re.compile(r"[^a-z0-9]+")


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


def ensure_toolbar_position(s: Session, position: str) -> None:
    """Put the toolbar where the capture names say it is, changing the setting only when it is elsewhere.

    The both-positions flow leaves the toolbar at the bottom, so a later capture named for the top would show the
    bottom toolbar. Checking the address bar first keeps an unchanged position free of a Settings trip."""
    if position not in TOOLBAR_POSITIONS:
        raise ValueError(f"unknown toolbar position {position!r}")
    go_home(s)
    if s.toolbar_at_top() == (position == "top"):
        s.log(f"toolbar already at the {position}")
        return
    set_toolbar_position(s, position)
    go_home(s)
    if s.toolbar_at_top() != (position == "top"):
        raise RuntimeError(f"toolbar did not move to the {position} of the screen")
    s.log(f"toolbar now at the {position}")


def state_key(suffix: str) -> str:
    """Query value that names one switch state: '-after-toggle-off' becomes 'after-toggle-off'.

    The page URLs of the switch-state groups carry it, so every group loads a URL Fenix has not opened yet and
    starts a new load instead of selecting the finished tab of the previous group."""
    return _QUERY_KEY.sub("-", suffix.strip().lower()).strip("-")


def _state_query(suffix: str) -> str:
    key = state_key(suffix)
    return f"&state={key}" if key else ""


PULL_START_FRACTION = 0.30
PULL_PAUSE_FRACTION = 0.37
PULL_RELEASE_FRACTION = 0.50
PULL_STEPS = 6


def page_load(s: Session, position: str, *, suffix: str = "", label: str = "", after_load: bool = True) -> None:
    """The page-load line while a page is still loading and, unless `after_load` is off, after it finished.

    `suffix` (file name) and `label` (index text) tell the captures of one switch state apart from the others."""
    with s.capture(f"page-load-{position}-loading{suffix}", label=f"page load, {position} toolbar, mid-load{label}") as shot:
        go_home(s)
        s.open_url(f"{s.server}/slow?pos={position}{_state_query(suffix)}")
        s.dev.sleep(4.0)
        shot.take(settle=0.5)
    if not after_load:
        return
    with s.capture(f"page-load-{position}-loaded{suffix}", label=f"page load, {position} toolbar, after load{label}") as shot:
        s.open_url(f"{s.server}/page?pos={position}{_state_query(suffix)}")
        s.wait_page("10.0.2.2", timeout=30)
        s.dev.sleep(5.0)
        shot.take(settle=0.5)


def _touch(s: Session, action: str, x: int, y: int) -> None:
    s.dev.adb.shell(f"input motionevent {action} {x} {y}")


def _drag_to(s: Session, x: int, y_from: int, y_to: int) -> None:
    for step in range(1, PULL_STEPS + 1):
        _touch(s, "MOVE", x, y_from + (y_to - y_from) * step // PULL_STEPS)
        s.dev.sleep(0.15)


def pull_to_refresh(s: Session, position: str, *, suffix: str = "", label: str = "", reloading: bool = True) -> None:
    """Hold the page part way down and photograph the pull, then release past the trigger so the reload starts.

    `suffix`, `label` and `reloading` work as in `page_load`; `reloading` off skips the capture taken during the reload."""
    with s.capture(f"pull-to-refresh-{position}-pulling{suffix}", label=f"pull-to-refresh, {position} toolbar, during pull{label}") as pulling:
        s.open_url(f"{s.server}/reset?pos={position}{_state_query(suffix)}")
        s.dev.sleep(1.0)
        s.open_url(f"{s.server}/refresh?pos={position}{_state_query(suffix)}")
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
    if not reloading:
        return
    with s.capture(f"pull-to-refresh-{position}-reloading{suffix}", label=f"pull-to-refresh, {position} toolbar, while reloading{label}") as shot:
        s.dev.sleep(0.8)
        shot.take(settle=0.0)


def both_positions(s: Session, step: Callable[[Session, str], None]) -> None:
    """Run `step` with the toolbar where it is, then again after moving it to the other side."""
    go_home(s)
    first = "top" if toolbar_at_top(s) else "bottom"
    other = "bottom" if first == "top" else "top"
    step(s, first)
    set_toolbar_position(s, other)
    go_home(s)
    step(s, other)
