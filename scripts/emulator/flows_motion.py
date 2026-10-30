"""Captures of things that move: the page-load line and pull-to-refresh, for both toolbar positions."""
from __future__ import annotations

import subprocess
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


def page_load(s: Session, position: str) -> None:
    """The page-load line while a page is still loading and after it finished."""
    with s.capture(f"page-load-{position}-loading", label=f"page load, {position} toolbar, mid-load") as shot:
        go_home(s)
        s.open_url(f"{s.server}/slow")
        s.dev.sleep(4.0)
        shot.take(settle=0.5)
    with s.capture(f"page-load-{position}-loaded", label=f"page load, {position} toolbar, after load") as shot:
        s.open_url(f"{s.server}/page")
        s.wait_page("10.0.2.2", timeout=30)
        s.dev.sleep(5.0)
        shot.take(settle=0.5)


def pull_to_refresh(s: Session, position: str) -> None:
    """Drag the page down slowly and photograph the pull, then the reload that starts on release."""
    with s.capture(f"pull-to-refresh-{position}-pulling", label=f"pull-to-refresh, {position} toolbar, during pull") as pulling:
        s.open_url(f"{s.server}/reset")
        s.dev.sleep(1.0)
        s.open_url(f"{s.server}/refresh")
        s.wait_page("10.0.2.2", timeout=30)
        s.dev.sleep(5.0)
        width, height = s.dev.screen_size()
        drag = subprocess.Popen(  # noqa: S603 - fixed adb arguments
            [*s.dev.adb.prefix, "shell", f"input swipe {width // 2} {int(height * 0.30)} {width // 2} {int(height * 0.75)} 6000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            s.dev.sleep(3.5)
            pulling.take(settle=0.0)
        finally:
            drag.wait(timeout=30)
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
