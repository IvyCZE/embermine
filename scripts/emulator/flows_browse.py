"""Captures that start in the browser: onboarding, homepage, search, a loaded page, its menu and panel."""
from __future__ import annotations

from scripts.emulator import targets as t
from scripts.emulator import uidump
from scripts.emulator.device import StepError
from scripts.emulator.session import LaunchError, Session
from scripts.emulator.uidump import Selector

HTTPS_URL = "https://example.com/"
TERMS_PAGE = Selector(label=r".*(Terms of Use|Privacy Notice).*")
# The onboarding view is drawn when one of its buttons or its Terms text is in the UI dump.
ONBOARDING_READY = (*t.ONBOARDING_BUTTONS, TERMS_PAGE)
ONBOARDING_VIEW_SECONDS = 120
FRAME_ATTEMPTS = 3
FRAME_WAIT_SECONDS = 3.0


def onboarding_first_screen(s: Session) -> None:
    """The very first screen of a fresh install, before anything was tapped.

    The capture waits for the onboarding view itself, not just for any text: right after launch the app can
    still draw an empty window, and that blank frame must not become the first screen. A frame the screenshot
    reports as blank is taken again a few seconds later.
    """
    with s.capture("onboarding", label="onboarding (first screen of a fresh install)") as shot:
        if s.dev.wait_for(*ONBOARDING_READY, timeout=ONBOARDING_VIEW_SECONDS, label="onboarding-view") is None:
            raise StepError(f"the onboarding view did not render within {ONBOARDING_VIEW_SECONDS} s")
        for attempt in range(1, FRAME_ATTEMPTS + 1):
            try:
                shot.take(settle=FRAME_WAIT_SECONDS)
                return
            except StepError as exc:
                if attempt == FRAME_ATTEMPTS:
                    raise
                s.log(f"onboarding frame {attempt} of {FRAME_ATTEMPTS} was not usable ({exc}); waiting for the next frame")
                s.dev.sleep(FRAME_WAIT_SECONDS)


def complete_onboarding(s: Session, max_steps: int = 14) -> None:
    """Tap through the onboarding pages declining everything. Failing to reach the homepage fails the job."""
    previous: list[str] = []
    terms_captured = False
    for step in range(max_steps):
        s.dev.sweep_dialogs()
        nodes = s.dev.dump(f"onboarding-{step}", save=True)
        if not terms_captured and uidump.find_first(nodes, TERMS_PAGE) is not None:
            terms_captured = True
            with s.capture("onboarding-terms-of-use", label="onboarding Terms of Use page") as shot:
                shot.take(settle=1.0)
        button = uidump.find_first(nodes, *t.ONBOARDING_BUTTONS)
        if button is None:
            if uidump.find_first(nodes, t.HOMEPAGE_VIEW, t.HOMEPAGE_BAR) is not None:
                s.log(f"onboarding finished after {step} taps")
                if not terms_captured:
                    record_missing_terms_page(s)
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


def record_missing_terms_page(s: Session) -> None:
    with s.capture("onboarding-terms-of-use", label="onboarding Terms of Use page"):
        raise StepError("the Terms of Use onboarding page was not on screen during the onboarding taps")


def go_home(s: Session, *, private: bool = False) -> None:
    s.new_tab_home(private=private)
    s.wait_homepage()
    s.dev.sleep(2.0)


def homepage(s: Session, *, private: bool = False) -> None:
    with s.capture("04-homepage", private=private, label="homepage") as shot:
        go_home(s, private=private)
        shot.take(settle=2.5)


def homepage_main_menu(s: Session) -> None:
    """The main menu opened from the homepage. The API 30 pass uses it, as it has no loaded page to open the menu from."""
    with s.capture("14-main-menu", label="main menu, opened from the homepage") as shot:
        go_home(s)
        s.dev.tap(t.MENU_BUTTON)
        if s.dev.wait_for(t.MENU_SETTINGS, timeout=10) is None:
            raise StepError("main menu did not open")
        shot.take(settle=1.5)
        close_overlay(s)


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
        s.open_url(f"{s.server}/slow?menu=1")
        s.dev.sleep(4.0)
        s.dev.tap(t.MENU_BUTTON)
        if s.dev.wait_for(t.MENU_SETTINGS, timeout=10) is None:
            raise StepError("main menu did not open")
        stop = uidump.find_first(s.dev.dump("menu-loading", save=True), Selector(label=r"Stop"))
        shot.take(settle=1.0, note="Stop item on screen" if stop else "no Stop item found in the menu dump (page may have finished loading)")
        close_overlay(s)
