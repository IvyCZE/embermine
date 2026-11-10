"""Cross-area groups: every screen that shows the accent, the shapes or the indicators, taken in one switch state.

flows_wallpaper calls these after each switch change and after each restart of the walk, so the groups of one state
come from the same session as the Customize and homepage captures next to them. Like those, the file names carry
the state: `10-toolbar-after-toggle-off_dynamic-off_light.png`. The page-load and pull-to-refresh captures are named
for the top toolbar, so each group puts the toolbar there first and gives its page URLs a query string of its own.
"""
from __future__ import annotations

from dataclasses import dataclass

from scripts.emulator import flows_motion, flows_settings, flows_tabs
from scripts.emulator import targets as t
from scripts.emulator.device import StepError
from scripts.emulator.flows_browse import HTTPS_URL, close_overlay, go_home, load_page
from scripts.emulator.session import Session


@dataclass(frozen=True)
class SwitchState:
    suffix: str  # appended to every file stem of the group
    on: bool  # the 'Use wallpaper colors' state of the group
    label: str  # the state as written in the index labels


TOGGLE_OFF = SwitchState("-after-toggle-off", False, "switch turned off")
TOGGLE_ON = SwitchState("-after-toggle-on", True, "switch turned on again")
RESTART_OFF = SwitchState("-after-restart-off", False, "switch off after a restart")
RESTART_ON = SwitchState("-after-restart-on", True, "switch on after a restart")
SWITCH_STATES = (TOGGLE_OFF, TOGGLE_ON, RESTART_OFF, RESTART_ON)

# (file stem, label) of the normal screens of a group: the accent (menu, tray), the shapes and the indicators
NORMAL_SCREENS = (
    ("10-toolbar", "toolbar on a loaded https page"),
    ("14-main-menu", "main menu"),
    ("12-tab-tray-header", "tab tray header (normal tabs)"),
    ("page-load-top-loading", "page load, top toolbar, mid-load"),
    ("pull-to-refresh-top-pulling", "pull-to-refresh, top toolbar, during pull"),
)
# (file stem, label) of the private group: the homepage, a private tab's toolbar and menu, and the private tab tray
PRIVATE_SCREENS = (
    ("04-homepage", "homepage (private)"),
    ("10-toolbar", "toolbar on a loaded https page (private)"),
    ("14-main-menu", "main menu (private)"),
    ("12-tab-tray-header", "tab tray header (private tabs)"),
)


def _name(state: SwitchState, stem: str, *, private: bool = False) -> tuple[str, str]:
    """File stem and index label of one screen of a group in this switch state."""
    screens = PRIVATE_SCREENS if private else NORMAL_SCREENS
    label = next(text for key, text in screens if key == stem)
    return stem + state.suffix, f"{label}, {state.label}"


def group_captures(state: SwitchState, *, private: bool = False) -> tuple[tuple[str, bool, str], ...]:
    """(file stem, switch state in the capture, label) of one group, in the order the group takes them."""
    screens = PRIVATE_SCREENS if private else NORMAL_SCREENS
    names = [_name(state, stem, private=private) for stem, _ in screens]
    return tuple((stem, state.on, label) for stem, label in names)


# (file stem, switch state, label) of the normal groups of all four switch states
NORMAL_CAPTURES = tuple(c for state in SWITCH_STATES for c in group_captures(state))
# The private group is taken once, in the switch-off state. The switch-on private captures are the walk's own
# private captures, which run before the switch is first changed.
PRIVATE_CAPTURES = group_captures(TOGGLE_OFF, private=True)


def screen_group(s: Session, state: SwitchState) -> None:
    """Toolbar, main menu, tab tray header, page-load line and pull-to-refresh, in the switch state set now."""
    s.dynamic = state.on
    go_home(s)
    flows_motion.ensure_toolbar_position(s, "top")
    stem, label = _name(state, "10-toolbar")
    with s.capture(stem, label=label) as shot:
        load_page(s, HTTPS_URL, "example.com", private=False)
        shot.take(settle=1.0)
    stem, label = _name(state, "14-main-menu")
    with s.capture(stem, label=label) as shot:
        s.dev.tap(t.MENU_BUTTON)
        if s.dev.wait_for(t.MENU_SETTINGS, timeout=10) is None:
            raise StepError("main menu did not open")
        shot.take(settle=1.5)
        close_overlay(s)
    stem, label = _name(state, "12-tab-tray-header")
    with s.capture(stem, label=label) as shot:
        flows_tabs.open_tray(s)
        flows_tabs.ensure_tray(s, flows_tabs.BANNER_NORMAL, "normal tabs")
        shot.take(settle=1.0)
    flows_tabs.close_tray(s)
    flows_motion.page_load(s, "top", suffix=state.suffix, label=f", {state.label}", after_load=False)
    flows_motion.pull_to_refresh(s, "top", suffix=state.suffix, label=f", {state.label}", reloading=False)


def private_group(s: Session, state: SwitchState) -> None:
    """Private homepage, a private tab's toolbar and main menu, and the private tab tray, in the switch state set now."""
    s.dynamic = state.on
    if not s.private_screenshots:
        flows_settings.allow_private_screenshots(s)
        s.private_screenshots = True
    stem, label = _name(state, "04-homepage", private=True)
    with s.capture(stem, private=True, label=label) as shot:
        go_home(s, private=True)
        shot.take(settle=2.5)
    stem, label = _name(state, "10-toolbar", private=True)
    with s.capture(stem, private=True, label=label) as shot:
        load_page(s, HTTPS_URL, "example.com", private=True)
        shot.take(settle=1.0)
    stem, label = _name(state, "14-main-menu", private=True)
    with s.capture(stem, private=True, label=label) as shot:
        s.dev.tap(t.MENU_BUTTON)
        if s.dev.wait_for(t.MENU_SETTINGS, timeout=10) is None:
            raise StepError("main menu did not open")
        shot.take(settle=1.5)
        close_overlay(s)
    stem, label = _name(state, "12-tab-tray-header", private=True)
    with s.capture(stem, private=True, label=label) as shot:
        flows_tabs.open_tray(s)
        flows_tabs.show_page(s, flows_tabs.BANNER_PRIVATE, "private tabs")
        s.dev.try_tap(flows_tabs.LOCK_BANNER_DISMISS, timeout=2)
        shot.take(settle=1.0)
    flows_tabs.close_tray(s)
    s.ensure_normal()
