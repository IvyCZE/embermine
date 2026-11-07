"""Settings screens, history and about:config."""
from __future__ import annotations

import re

from scripts.emulator import targets as t
from scripts.emulator.device import StepError
from scripts.emulator.flows_browse import go_home
from scripts.emulator.session import Session
from scripts.emulator.uidump import Selector

# (file stem, row title in the Settings list, label for the index)
SUBPAGES = (
    ("settings-subpage-search", r"Search", "settings sub-page: Search"),
    ("settings-subpage-tabs", r"Tabs", "settings sub-page: Tabs"),
    ("settings-subpage-accessibility", r"Accessibility", "settings sub-page: Accessibility"),
    ("settings-subpage-tracking-protection", r"Enhanced Tracking Protection", "settings sub-page: Enhanced Tracking Protection"),
    ("settings-subpage-site-settings", r"Site settings", "settings sub-page: Site settings"),
    ("settings-subpage-download-settings", r"Download Settings", "settings sub-page: Download Settings"),
    ("settings-subpage-sign-in", r"Sign in", "settings sub-page: Sign in (Turn on Sync)"),
    ("settings-subpage-firefox-labs", r"Firefox Labs", "settings sub-page: Firefox Labs"),
)
SETTINGS_ROW_ROOT = t.SETTINGS_TITLE
ABOUT_ROW = r"About (Firefox|Embermine)"
ABOUT_FIRST_ROW = Selector(label=r"What.s new in Embermine")
TECHNICAL_DATA_ROW = Selector(label=r"Send technical and interaction data")
PREF_NAME = re.compile(r"[a-z][A-Za-z0-9]*(\.[A-Za-z0-9_]+)+")


def _toolbar_shows(url: str) -> Selector:
    return Selector(id="ADDRESSBAR_URL_BOX", desc=url)


# (file stem, row title in the About list, what shows the page opened, label for the index)
ABOUT_PAGES = (
    (
        "about-whatsnew",
        r"What.s new in Embermine",
        _toolbar_shows(r".*github\.com/IvyCZE/embermine/releases.*"),
        "About > What's new (GitHub releases)",
    ),
    (
        "about-support",
        r"Support",
        _toolbar_shows(r".*github\.com/IvyCZE/embermine/issues.*"),
        "About > Support (GitHub issues)",
    ),
    (
        "about-privacy",
        r"Privacy notice",
        _toolbar_shows(r".*github\.com/IvyCZE/embermine/blob/master/PRIVACY\.md.*"),
        "About > Privacy notice (PRIVACY.md on GitHub)",
    ),
    (
        "about-licenses",
        r"Licensing information",
        _toolbar_shows(r"about:license.*"),
        "About > Licensing information (about:license)",
    ),
    (
        "about-crashes",
        r"Crashes",
        Selector(label=r"Crash Reports|No crash reports have been submitted\."),
        "About > Crashes (crash list)",
    ),
)


def open_settings(s: Session) -> None:
    """Home -> main menu -> Settings. Falls back to the fenix://settings deep link when the menu fails."""
    go_home(s)
    try:
        s.dev.tap(t.MENU_BUTTON)
        s.dev.tap(t.MENU_SETTINGS, timeout=10, settle=2.0)
        if s.dev.wait_for(SETTINGS_ROW_ROOT, timeout=10) is None:
            raise StepError("settings list did not appear")
    except StepError as exc:
        s.log(f"settings via menu failed ({exc}); using deep link")
        s.deep_link("settings")
        if s.dev.wait_for(SETTINGS_ROW_ROOT, timeout=15) is None:
            raise StepError("settings list did not appear (deep link)") from exc


def open_row(s: Session, title: str, *, wait: Selector | None = None) -> None:
    """Scroll the Settings list to a row and open it."""
    s.dev.scroll_top()
    row = s.dev.scroll_to(Selector(label=title), max_swipes=10)
    s.dev.tap_node(row)
    s.dev.sleep(2.0)
    if wait is not None and s.dev.wait_for(wait, timeout=10) is None:
        raise StepError(f"page for row {title!r} did not open")


def settings_root(s: Session) -> None:
    with s.capture("05-settings", label="settings root") as shot:
        open_settings(s)
        shot.take(settle=1.5)


def subpage(s: Session, stem: str, title: str, label: str, *, back_steps: int = 1) -> None:
    with s.capture(stem, label=label) as shot:
        open_row(s, title)
        shot.take(settle=1.5)
        for _ in range(back_steps):
            s.dev.back()


def settings_pages(s: Session) -> None:
    """All settings captures. Each page starts from the Settings list, which is re-opened when lost."""
    settings_root(s)
    for stem, title, label in SUBPAGES:
        ensure_settings_list(s)
        subpage(s, stem, title, label)
    ensure_settings_list(s)
    subpage(s, "customize", r"Customize", "customize screen")
    ensure_settings_list(s)
    subpage(s, "settings-data-collection", r"Data collection", "settings data collection page")
    ensure_settings_list(s)
    data_collection_scrolled(s)
    ensure_settings_list(s)
    homepage_settings(s)
    ensure_settings_list(s)
    subpage(s, "about", r"About (Firefox|Embermine)", "about screen")


def legacy_pages(s: Session) -> None:
    """The settings captures of the API 30 job: Customize, the Homepage page and the wallpaper picker."""
    open_settings(s)
    subpage(s, "customize", r"Customize", "customize screen")
    ensure_settings_list(s)
    homepage_settings(s)


def homepage_settings(s: Session) -> None:
    with s.capture("settings-homepage", label="homepage settings page") as shot:
        open_row(s, r"Homepage")
        shot.take(settle=1.5)
    with s.capture("settings-homepage-sponsored", label="homepage settings page, Stories and Sponsored stories toggles") as shot:
        s.dev.scroll_to(Selector(label=r"Sponsored stories"), max_swipes=8)
        shot.take(settle=1.5)
    s.dev.scroll_top()
    with s.capture("wallpaper-picker", label="wallpaper picker (Homepage > Wallpapers)") as shot:
        s.dev.tap(Selector(label=r"Wallpapers?"), timeout=8, settle=2.5)
        s.dev.wait_for(Selector(desc=r".*[Ww]allpaper.*"), Selector(label=r".*[Ww]allpaper.*"), timeout=8)
        shot.take(settle=2.0)
        s.dev.back()
    s.dev.back()


def ensure_settings_list(s: Session) -> None:
    for _ in range(3):
        if s.dev.visible(SETTINGS_ROW_ROOT):
            return
        s.dev.back()
    try:
        open_settings(s)
    except StepError as exc:
        s.log(f"cannot get back to the settings list: {exc}")


def history(s: Session) -> None:
    with s.capture("09-history", label="history") as shot:
        go_home(s)
        try:
            s.dev.tap(t.MENU_BUTTON)
            s.dev.tap(t.MENU_HISTORY, timeout=10, settle=2.5)
        except StepError:
            s.log("history via menu failed; using deep link")
            s.deep_link("urls_history")
        s.dev.wait_for(Selector(label=r"History|Recently closed tabs|No history here"), timeout=10)
        shot.take(settle=2.0)
        s.dev.back()


def about_config(s: Session) -> None:
    """Fenix ignores about: URLs sent as intents, so about:config is typed into the address bar."""
    with s.capture("about-config", label="about:config page") as shot:
        go_home(s)
        s.visited.append("about:config")
        s.dev.tap(t.HOMEPAGE_BAR, timeout=10, settle=1.5)
        s.dev.type_text("about:config")
        s.dev.key("KEYCODE_ENTER")
        try:
            s.wait_page("about:config", timeout=20)
        except StepError as exc:
            raise StepError(
                "about:config did not open after it was typed into the address bar; check aboutConfigEnabled in GeckoProvider"
            ) from exc
        s.dev.try_tap(Selector(label=r"Accept the [Rr]isk.*"), timeout=3)
        s.dev.sleep(3.0)
        prefs = [n for n in s.dev.dump("about-config-prefs", save=True) if PREF_NAME.fullmatch(n.text or "")]
        shot.take(settle=1.0, note=f"about:config open; {len(prefs)} preference names in the UI dump")


def open_about(s: Session) -> None:
    open_settings(s)
    open_row(s, ABOUT_ROW, wait=ABOUT_FIRST_ROW)


def about_pages(s: Session) -> None:
    """Each About row that opens a page or screen. Every capture starts again from Settings."""
    for stem, row, opened, label in ABOUT_PAGES:
        with s.capture(stem, label=label) as shot:
            open_about(s)
            open_row(s, row)
            if s.dev.wait_for(opened, timeout=30) is None:
                raise StepError(f"{label}: the page did not open")
            shot.take(settle=3.0)


def data_collection_scrolled(s: Session) -> None:
    """The lower part of Data collection. The five controls do not fit on one screen, so the top capture and this one together show all of them."""
    label = "settings data collection page, scrolled to crash reports and campaign measurement data"
    with s.capture("settings-data-collection-scrolled", label=label) as shot:
        open_row(s, r"Data collection")
        s.dev.scroll_down()
        s.dev.scroll_to(Selector(label=r"Campaign measurement data"), max_swipes=4)
        shot.take(settle=1.5)
        s.dev.back()


def data_collection_opt_in(s: Session) -> None:
    """Turns on the technical and interaction data switch once. The default page is captured by settings_pages."""
    label = "settings data collection page, after turning on technical and interaction data"
    with s.capture("settings-data-collection-opt-in", label=label) as shot:
        open_settings(s)
        open_row(s, r"Data collection")
        s.dev.tap(TECHNICAL_DATA_ROW, timeout=10, settle=2.0)
        shot.take(settle=1.5, note="switch tapped once from off")


def allow_private_screenshots(s: Session) -> None:
    """Private tabs set FLAG_SECURE, which turns screencap into 0 bytes; the opt-in setting lifts it."""
    s.ensure_normal()
    s.deep_link("settings_private_browsing")
    row = s.dev.wait_for(Selector(label=r"Allow screenshots in private browsing"), timeout=15)
    if row is None:
        raise StepError("'Allow screenshots in private browsing' row not found")
    nodes = s.dev.dump("private-screenshots-setting", save=True)
    switches = [n for n in nodes if n.id_name == "switchWidget"]
    mine = min(switches, key=lambda n: abs(n.center[1] - row.center[1]), default=None)
    if mine is not None and mine.checked:
        s.log("private screenshots already allowed")
    else:
        s.dev.tap_node(row)
        s.dev.sleep(1.5)
        after = s.dev.dump("private-screenshots-after", save=True)
        now = [n for n in after if n.id_name == "switchWidget" and abs(n.center[1] - row.center[1]) < 80]
        s.log(f"private screenshots switch now checked={[n.checked for n in now]}")
    s.dev.back()
    s.dev.back()
