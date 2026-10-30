"""Captures that start in the browser: onboarding, homepage, search, a loaded page, its menu and panel."""
from __future__ import annotations

from scripts.emulator import targets as t
from scripts.emulator import uidump
from scripts.emulator.device import StepError
from scripts.emulator.session import LaunchError, Session
from scripts.emulator.uidump import Selector

HTTPS_URL = "https://example.com/"


def onboarding_first_screen(s: Session) -> None:
    """The very first screen of a fresh install, before anything was tapped."""
    with s.capture("onboarding", label="onboarding (first screen of a fresh install)") as shot:
        # Compose screens need a moment before the dump contains their text.
        if s.dev.wait_for(Selector(text=r".+", clickable=True), Selector(label=r".{3,}"), timeout=40) is None:
            raise StepError("no UI nodes appeared after launch")
        shot.take(settle=3.0)


def complete_onboarding(s: Session, max_steps: int = 14) -> None:
    """Tap through the onboarding pages declining everything. Failing to reach the homepage fails the job."""
    previous: list[str] = []
    for step in range(max_steps):
        s.dev.sweep_dialogs()
        nodes = s.dev.dump(f"onboarding-{step}", save=True)
        button = uidump.find_first(nodes, *t.ONBOARDING_BUTTONS)
        if button is None:
            if uidump.find_first(nodes, t.HOMEPAGE_VIEW, t.HOMEPAGE_BAR) is not None:
                s.log(f"onboarding finished after {step} taps")
                return
            s.dev.sleep(2.0)
            continue
        labels = sorted({n.label for n in nodes if n.label})[:8]
        s.log(f"onboarding step {step}: buttons found, screen shows {labels}")
        try:
            s.dev.screenshot(s.debug / f"onboarding-step-{step}.png")
        except StepError:
            pass
        if step >= 2 and labels == previous:
            # Same page twice in a row: the plain tap was swallowed, press a little longer.
            x, y = button.center
            s.dev.adb.shell(f"input swipe {x} {y} {x} {y} 200")
        else:
            s.dev.tap_node(button)
        previous = labels
        s.dev.sleep(2.0)
    raise LaunchError(f"homepage not reached after {max_steps} onboarding steps")


def go_home(s: Session, *, private: bool = False) -> None:
    s.new_tab_home(private=private)
    s.wait_homepage()
    s.dev.sleep(2.0)


def homepage(s: Session, *, private: bool = False) -> None:
    with s.capture("04-homepage", private=private, label="homepage") as shot:
        go_home(s, private=private)
        shot.take(settle=2.5)


def search_bar_and_selector(s: Session) -> None:
    """Open the search from the homepage address bar, then the search engine menu."""
    opened = False
    with s.capture("search-bar", label="search bar (suggestions screen)") as shot:
        go_home(s)
        s.dev.tap(t.HOMEPAGE_BAR)
        s.dev.wait_for(t.SEARCH_ENGINE_SELECTOR, timeout=10)
        opened = True
        extras = sorted({n.label for n in uidump.find_all(s.dev.dump("search-extras"), t.SEARCH_EXTRAS)})
        shot.take(settle=2.0, note="extra actions on screen: " + (", ".join(extras) or "none"))
    with s.capture("11-search-selector", label="search engine selector") as shot:
        if not opened:
            raise StepError("search screen did not open")
        s.dev.tap(t.SEARCH_ENGINE_SELECTOR)
        if s.dev.wait_for(t.SEARCH_ENGINE_MENU_TITLE, timeout=8) is None:
            raise StepError("search engine menu did not appear")
        shot.take(settle=1.5)
    s.dev.back()
    s.dev.back()


def load_page(s: Session, url: str, host: str, *, private: bool) -> None:
    s.open_url(url, private=private)
    s.wait_page(host, timeout=45)
    s.dev.sleep(5.0)  # let the page and the toolbar settle


def close_overlay(s: Session) -> None:
    s.dev.back()
    s.dev.sleep(1.0)


def page_captures(s: Session, *, private: bool) -> None:
    """10 toolbar, 14 main menu and 13 site protection panel, on an https page and an http page."""
    loaded = False
    with s.capture("10-toolbar", private=private, label="toolbar on a loaded https page") as shot:
        load_page(s, HTTPS_URL, "example.com", private=private)
        loaded = True
        shot.take(settle=1.0)
    with s.capture("14-main-menu", private=private, label="main menu") as shot:
        if not loaded:
            raise StepError("https page did not load")
        s.dev.tap(t.MENU_BUTTON)
        if s.dev.wait_for(t.MENU_SETTINGS, timeout=10) is None:
            raise StepError("main menu did not open")
        shot.take(settle=1.5)
        close_overlay(s)
    with s.capture("13-site-protection-panel", private=private, label="site protection panel (https)") as shot:
        if not loaded:
            raise StepError("https page did not load")
        s.dev.tap(t.SITE_INFO)
        s.dev.sleep(2.5)
        shot.take(settle=1.0)
        close_overlay(s)
    with s.capture("13-site-protection-panel-http", private=private, label="site protection panel (http page, local test server)") as shot:
        load_page(s, f"{s.server}/page", "10.0.2.2", private=private)
        s.dev.tap(t.SITE_INFO)
        s.dev.sleep(2.5)
        shot.take(settle=1.0)
        close_overlay(s)


def main_menu_while_loading(s: Session) -> None:
    """The main menu opened while a page is still loading, where Refresh turns into Stop."""
    with s.capture("14-main-menu-loading", label="main menu while a page is loading (Stop state)") as shot:
        go_home(s)
        s.open_url(f"{s.server}/slow")
        s.dev.sleep(4.0)
        s.dev.tap(t.MENU_BUTTON)
        if s.dev.wait_for(t.MENU_SETTINGS, timeout=10) is None:
            raise StepError("main menu did not open")
        stop = uidump.find_first(s.dev.dump("menu-loading", save=True), Selector(label=r"Stop"))
        shot.take(settle=1.0, note="Stop item on screen" if stop else "no Stop item found in the menu dump (page may have finished loading)")
        close_overlay(s)
