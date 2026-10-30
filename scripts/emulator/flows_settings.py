"""Settings screens, history and about:config."""
from __future__ import annotations

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
)
SETTINGS_ROW_ROOT = t.SETTINGS_TITLE


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
    homepage_settings(s)
    ensure_settings_list(s)
    subpage(s, "about", r"About (Firefox|Embermine)", "about screen")


def homepage_settings(s: Session) -> None:
    with s.capture("settings-homepage", label="homepage settings page") as shot:
        open_row(s, r"Homepage")
        shot.take(settle=1.5)
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
    with s.capture("about-config", label="about:config page") as shot:
        s.open_url("about:config")
        try:
            s.wait_page("about:config", timeout=20)
        except StepError as exc:
            raise StepError(
                "about:config did not open; GeckoProvider enables it for Beta, Nightly and debug builds only, "
                "this build reports the release channel"
            ) from exc
        s.dev.sleep(3.0)
        shot.take(settle=1.0, note="page requested: about:config")


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
