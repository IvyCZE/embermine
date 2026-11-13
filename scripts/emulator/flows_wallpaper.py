"""Embermine wallpapers: a picked wallpaper, the homepage and picker after each switch change, and a system palette change."""
from __future__ import annotations

import re

from scripts.emulator import devsetup, flows_cross, flows_settings
from scripts.emulator.device import StepError
from scripts.emulator.flows_browse import go_home
from scripts.emulator.session import Session
from scripts.emulator.uidump import Node, Selector

# rise is the only wallpaper that uses all six gray roles, and its portrait center-crop keeps every role visible on the
# homepage (VAL-WALL-005). The picked wallpaper is the one the 6-tone capture checks.
PICKED_WALLPAPER = "rise"
# A lime green seed: the palette check still requires green, and the wallpapers recolor visibly against the default seed.
CHANGED_PALETTE_SEED = "7BC043"
PICKER_ROW = Selector(label=r"Wallpapers?")
ANY_THUMBNAIL = Selector(desc=r"Wallpaper Item: .*")

# (file stem, label) of the captures of the picked wallpaper flow, in the order the flow takes them
PICKED_PICKER = ("wallpaper-select-rise", "wallpaper picker, rise selected")
PICKED_HOMEPAGE = ("homepage-wallpaper-rise", "homepage with the rise wallpaper")
PICKED_RESTART = ("04-homepage-after-restart", "homepage after a force stop and relaunch, rise kept")
PICKED_CAPTURES = (PICKED_PICKER, PICKED_HOMEPAGE, PICKED_RESTART)

# (file stem, switch state in the capture, label) of the captures taken right after each switch change
TOGGLE_OFF_HOMEPAGE = ("homepage-after-toggle-off", False, "homepage, switch turned off")
TOGGLE_OFF_PICKER = ("wallpaper-picker-after-toggle-off", False, "wallpaper picker, switch turned off")
TOGGLE_ON_HOMEPAGE = ("homepage-after-toggle-on", True, "homepage, switch turned on again")
TOGGLE_ON_PICKER = ("wallpaper-picker-after-toggle-on", True, "wallpaper picker, switch turned on again")
RESTART_OFF_HOMEPAGE = ("homepage-after-restart-off", False, "homepage, switch off after a restart")
RESTART_ON_HOMEPAGE = ("homepage-after-restart-on", True, "homepage, switch on after a restart")
RESTART_OFF_PICKER = ("wallpaper-picker-after-restart-off", False, "wallpaper picker, switch off after a restart")
RESTART_ON_PICKER = ("wallpaper-picker-after-restart-on", True, "wallpaper picker, switch on after a restart")
PALETTE_HOMEPAGE = ("04-homepage-after-palette-change", True, "homepage after the system palette changed mid-session")
# The homepage card whose text has to stay light on the translucent dark palette card of the wallpaper
RECENT_TAB_CAPTURE = ("homepage-recent-tab", "homepage with a populated Jump back in (recent tab) card over the wallpaper")
RECENT_TABS = Selector(id="recent.tabs")
RECENT_TAB_TITLE = Selector(id="recent.tab.title")
TOGGLE_HOMEPAGES = (TOGGLE_OFF_HOMEPAGE, TOGGLE_ON_HOMEPAGE, RESTART_OFF_HOMEPAGE, RESTART_ON_HOMEPAGE)
TOGGLE_PICKERS = (TOGGLE_OFF_PICKER, TOGGLE_ON_PICKER, RESTART_OFF_PICKER, RESTART_ON_PICKER)
# The Customize, homepage and picker captures above, the cross-area groups of flows_cross (each in its own switch
# state), then the palette change. TOGGLE_PRIVATE_CAPTURES is the private set of the switch-off state.
TOGGLE_CAPTURES = (
    flows_settings.WALLPAPER_COLORS_CAPTURES + TOGGLE_HOMEPAGES + TOGGLE_PICKERS + flows_cross.NORMAL_CAPTURES + (PALETTE_HOMEPAGE,)
)
TOGGLE_PRIVATE_CAPTURES = flows_cross.PRIVATE_CAPTURES


def thumbnail(name: str) -> Selector:
    return Selector(desc=rf"Wallpaper Item: {re.escape(name)}")


def open_picker(s: Session) -> None:
    flows_settings.open_settings(s)
    flows_settings.open_row(s, r"Homepage")
    s.dev.tap(PICKER_ROW, timeout=8, settle=2.5)
    if s.dev.wait_for(ANY_THUMBNAIL, timeout=10) is None:
        raise StepError("wallpaper picker thumbnails did not appear")


def select_picked_wallpaper(s: Session) -> None:
    """Picks the rise wallpaper, then checks the homepage before and after a force stop and relaunch."""
    with s.capture(PICKED_PICKER[0], label=PICKED_PICKER[1]) as shot:
        open_picker(s)
        s.dev.tap(thumbnail(PICKED_WALLPAPER), timeout=10, settle=2.0)
        shot.take(settle=2.0)
    with s.capture(PICKED_HOMEPAGE[0], label=PICKED_HOMEPAGE[1]) as shot:
        go_home(s)
        shot.take(settle=2.5)
    with s.capture(PICKED_RESTART[0], label=PICKED_RESTART[1]) as shot:
        s.force_stop()
        s.launch_from_launcher()
        go_home(s)
        shot.take(settle=2.5)


def homepage_capture(s: Session, capture: tuple[str, bool, str]) -> None:
    stem, on, label = capture
    s.dynamic = on
    with s.capture(stem, label=label) as shot:
        go_home(s)
        shot.take(settle=2.5)


def picker_capture(s: Session, capture: tuple[str, bool, str]) -> None:
    stem, on, label = capture
    s.dynamic = on
    with s.capture(stem, label=label) as shot:
        open_picker(s)
        shot.take(settle=2.0)


def show_recent_tab_card(s: Session) -> Node | None:
    """Scroll the homepage to the Jump back in card. None when the card is not there."""
    go_home(s)
    s.dev.sleep(1.5)
    try:
        return s.dev.scroll_to(RECENT_TAB_TITLE, RECENT_TABS, max_swipes=3)
    except StepError:
        return None


def recent_tab_homepage(s: Session) -> None:
    """The homepage Jump back in card over the wallpaper, in the switch state and theme of this pass.

    Its title and URL are the text that must stay light on the translucent dark palette card (VAL-WALL-011).
    The section is off on a fresh profile, because the Nimbus homescreen defaults leave it out, so it is turned
    on first. A relaunch makes the homepage rebuild with the section enabled."""
    stem, label = RECENT_TAB_CAPTURE
    with s.capture(stem, label=label) as shot:
        flows_settings.set_homepage_recent_tabs(s, True)
        card = show_recent_tab_card(s)
        if card is None:
            s.log("no Jump back in card on the homepage yet; relaunching the app once")
            s.force_stop()
            s.launch_from_launcher()
            card = show_recent_tab_card(s)
        if card is None:
            raise StepError("no populated Jump back in card on the homepage")
        shot.take(settle=1.5, note="recent-tab card over the wallpaper: title and URL must be light on the dark card")


def palette_change(s: Session) -> None:
    """Changes the system palette mid-session. The app takes it up after a relaunch, then the forced green palette
    is put back so the palette check at the end of the walk still sees green."""
    stem, on, label = PALETTE_HOMEPAGE
    s.dynamic = on
    try:
        with s.capture(stem, label=label) as shot:
            devsetup.force_palette(s.dev.adb, s.log, s.dev.sleep, seed=CHANGED_PALETTE_SEED)
            s.force_stop()
            s.launch_from_launcher()
            go_home(s)
            shot.take(settle=2.5, note=f"system palette changed to seed #{CHANGED_PALETTE_SEED}, then restored to green")
    finally:
        devsetup.force_palette(s.dev.adb, s.log, s.dev.sleep)


def wallpaper_colors_toggle(s: Session) -> None:
    """Dynamic-on pass, after the walk: starts from the default (on). After each switch change and each restart it
    captures the Customize screen, the homepage, the picker and the cross-area group of that switch state
    (flows_cross); the switch-off state also gets the private set. Then it changes the system palette."""
    try:
        s.dynamic = True
        flows_settings.open_customize(s)
        flows_settings.require_wallpaper_colors(s, True)
        flows_settings.set_wallpaper_colors(s, False)
        flows_settings.toggle_capture(s, "customize-after-toggle-off", on=False)
        homepage_capture(s, TOGGLE_OFF_HOMEPAGE)
        picker_capture(s, TOGGLE_OFF_PICKER)
        flows_cross.screen_group(s, flows_cross.TOGGLE_OFF)
        flows_cross.private_group(s, flows_cross.TOGGLE_OFF)
        flows_settings.open_customize(s)
        flows_settings.set_wallpaper_colors(s, True)
        flows_settings.toggle_capture(s, "customize-after-toggle-on", on=True)
        homepage_capture(s, TOGGLE_ON_HOMEPAGE)
        picker_capture(s, TOGGLE_ON_PICKER)
        flows_cross.screen_group(s, flows_cross.TOGGLE_ON)
        flows_settings.open_customize(s)
        flows_settings.set_wallpaper_colors(s, False)
        s.force_stop()
        s.launch_from_launcher()
        flows_settings.open_customize(s)
        flows_settings.toggle_capture(s, "customize-after-restart-off", on=False)
        homepage_capture(s, RESTART_OFF_HOMEPAGE)
        picker_capture(s, RESTART_OFF_PICKER)
        flows_cross.screen_group(s, flows_cross.RESTART_OFF)
        flows_settings.open_customize(s)
        flows_settings.set_wallpaper_colors(s, True)
        s.force_stop()
        s.launch_from_launcher()
        flows_settings.open_customize(s)
        flows_settings.toggle_capture(s, "customize-after-restart-on", on=True)
        homepage_capture(s, RESTART_ON_HOMEPAGE)
        picker_capture(s, RESTART_ON_PICKER)
        flows_cross.screen_group(s, flows_cross.RESTART_ON)
        palette_change(s)
    finally:
        s.dynamic = True
