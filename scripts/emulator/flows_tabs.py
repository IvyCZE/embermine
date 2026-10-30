"""The tab tray: header, overflow menu, selection mode, tab groups and synced tabs.

Compose draws the whole tray, and Fenix does not expose its test tags as resource ids there, so every
target is a content description or visible label. Tab cards have neither, they are found by their size.
"""
from __future__ import annotations

from scripts.emulator import targets as t
from scripts.emulator import uidump
from scripts.emulator.device import StepError
from scripts.emulator.flows_browse import load_page
from scripts.emulator.session import Session
from scripts.emulator.uidump import Node, Selector

BANNER_NORMAL = Selector(desc=r"Normal Tabs Open.*")
BANNER_PRIVATE = Selector(desc=r"Private Tabs Open.*")
BANNER_GROUPS = Selector(desc=r".*tab groups? open.*")
BANNER_SYNCED = Selector(desc=r"Synced Tabs Open.*")
TRAY_MENU = Selector(desc=r"Open tabs menu")
MENU_SELECT_TABS = Selector(label=r"Select tabs")
EXIT_SELECT_MODE = Selector(desc=r"Exit multiselect mode")
SELECTED_MENU = Selector(desc=r"Selected tabs menu")
SELECTION_TITLE = Selector(label=r"\d+ selected")
MENU_ADD_TO_GROUP = Selector(label=r"Add to group")
NEW_GROUP_ROW = Selector(desc=r"Add to new tab group")
NEW_GROUP_TEXT = Selector(label=r"New tab group")
CREATE_GROUP_TITLE = Selector(label=r"Create tab group")
SAVE_BUTTON = Selector(label=r"Save")
# The grid card shows "Group 1"; the row of the Tab groups page describes itself as "Add to Group 1 tab group, 2 tabs, ...".
GROUP_CARD = Selector(label=r"(Add to )?Group \d+.*")
GROUP_MORE = Selector(desc=r"More options")
GROUP_MENU_UNGROUP = Selector(label=r"Ungroup")
SHEET_HANDLE = Selector(desc=r"View tab group, collapse drag handle")
LOCK_BANNER_DISMISS = Selector(label=r"No thanks")
ONBOARDING_DISMISS = Selector(desc=r"Dismiss tab group onboarding")
SYNCED_MENU_ACCOUNT = Selector(label=r"Account settings")

# Card width as a share of the screen width: two columns with margins.
CARD_MIN_WIDTH, CARD_MAX_WIDTH = 0.30, 0.62
CARD_MIN_HEIGHT = 0.10
BANNER_BOTTOM = 0.07  # nothing above this share of the screen height is a card


def tab_cards(nodes: list[Node]) -> list[Node]:
    """Clickable tab cards of the grid in reading order (row by row, left to right)."""
    width, height = uidump.screen_size(nodes)
    cards = [
        n
        for n in nodes
        if n.clickable
        and n.visible
        and CARD_MIN_WIDTH * width <= n.width <= CARD_MAX_WIDTH * width
        and n.height >= CARD_MIN_HEIGHT * height
        and n.bounds[1] >= BANNER_BOTTOM * height
    ]
    row = max(1, int(0.05 * height))
    return sorted(cards, key=lambda n: (n.bounds[1] // row, n.bounds[0]))


def tray_visible(s: Session) -> bool:
    return s.dev.visible(BANNER_NORMAL, BANNER_PRIVATE)


def open_tray(s: Session) -> None:
    """Tap the tab counter on the current page or homepage."""
    if tray_visible(s):
        return
    counter = s.dev.wait_for(t.TAB_COUNTER, t.TAB_COUNTER_DESC, timeout=10, label="tab-counter")
    if counter is None:
        raise StepError("tab counter not found in the toolbar")
    s.dev.tap_node(counter)
    if s.dev.wait_for(BANNER_NORMAL, BANNER_PRIVATE, timeout=15, label="tab-tray") is None:
        raise StepError("tab tray did not open")
    s.dev.sleep(1.5)


def close_tray(s: Session) -> None:
    for _ in range(3):
        if not tray_visible(s):
            return
        s.dev.back()


def show_page(s: Session, banner: Selector, what: str) -> None:
    node = s.dev.wait_for(banner, timeout=10, label=f"banner-{what}")
    if node is None:
        raise StepError(f"tab tray page button for {what} not found")
    s.dev.tap_node(node)
    s.dev.sleep(1.5)


def ensure_tray(s: Session, banner: Selector, what: str) -> None:
    """Get to a clean state of the given tray page: tray open, no selection, no menu."""
    if s.dev.visible(EXIT_SELECT_MODE):
        s.dev.tap(EXIT_SELECT_MODE)
    if not tray_visible(s):
        open_tray(s)
    show_page(s, banner, what)
    s.dev.try_tap(ONBOARDING_DISMISS, timeout=1.5)


def prepare_tabs(s: Session, wanted: int = 3) -> None:
    """A few normal tabs with different pages so the grid has several cards. Ends on a loaded page."""
    for n in range(wanted):
        load_page(s, f"{s.server}/page?tab={n}", "10.0.2.2", private=False)


def select_cards(s: Session, count: int) -> int:
    nodes = s.dev.dump("tab-grid", save=True)
    cards = tab_cards(nodes)[:count]
    if len(cards) < count:
        width, height = uidump.screen_size(nodes)
        s.log(f"only {len(cards)} tab cards found by size, tapping the first grid row by position")
        points = [(int(width * 0.27), int(height * 0.30)), (int(width * 0.73), int(height * 0.30))][:count]
    else:
        points = [c.center for c in cards]
    for x, y in points:
        s.dev.tap_xy(x, y)
        s.dev.sleep(1.0)
    return len(points)


def create_group_from_selection(s: Session) -> None:
    """Selection mode > Selected tabs menu > Add to group > New tab group > Save."""
    s.dev.tap(SELECTED_MENU, timeout=8)
    s.dev.tap(MENU_ADD_TO_GROUP, timeout=8, settle=1.5)
    # Without any group the "Add to" sheet may be skipped and the create sheet opens directly.
    first = s.dev.wait_for(NEW_GROUP_ROW, NEW_GROUP_TEXT, CREATE_GROUP_TITLE, SAVE_BUTTON, timeout=12, label="add-to-group-sheet")
    if first is not None and (NEW_GROUP_ROW.matches(first) or NEW_GROUP_TEXT.matches(first)):
        s.dev.tap_node(first)
        s.dev.sleep(1.5)
    if s.dev.wait_for(CREATE_GROUP_TITLE, SAVE_BUTTON, timeout=10) is None:
        s.dev.dump("create-group-sheet-missing", save=True)
        raise StepError("the create tab group sheet did not appear")
    s.dev.tap(SAVE_BUTTON, timeout=8, settle=2.5)


def require_group(s: Session, failure: str) -> None:
    if failure:
        raise StepError(f"no tab group to show: {failure}")
    if s.dev.wait_for(GROUP_CARD, timeout=8, label="group-card") is None:
        raise StepError("no tab group card on screen")


def tab_tray(s: Session) -> None:
    """Normal tabs: 12, 06, 07, then a group is created and shown in 02, 03, 08, the grid and 01."""
    group_failure = "the selection step before it failed"
    prepare_tabs(s)
    with s.capture("12-tab-tray-header", label="tab tray header (normal tabs)") as shot:
        open_tray(s)
        ensure_tray(s, BANNER_NORMAL, "normal tabs")
        s.dev.scroll_top(2)
        shot.take(settle=1.0)
    with s.capture("06-tab-tray-overflow-menu", label="tab tray overflow menu") as shot:
        ensure_tray(s, BANNER_NORMAL, "normal tabs")
        s.dev.tap(TRAY_MENU, timeout=8, settle=1.5)
        if s.dev.wait_for(MENU_SELECT_TABS, timeout=8) is None:
            raise StepError("the tab tray menu did not open")
        shot.take(settle=0.5)
        s.dev.back()
    with s.capture("07-tab-selection-mode", label="tab selection mode (two tabs selected)") as shot:
        ensure_tray(s, BANNER_NORMAL, "normal tabs")
        s.dev.tap(TRAY_MENU, timeout=8, settle=1.0)
        s.dev.tap(MENU_SELECT_TABS, timeout=8, settle=1.5)
        picked = select_cards(s, 2)
        if s.dev.wait_for(SELECTION_TITLE, timeout=6) is None:
            raise StepError("no 'N selected' title after tapping the tab cards")
        shot.take(settle=0.5, note=f"{picked} tab cards tapped")
        try:
            create_group_from_selection(s)
            group_failure = ""
        except Exception as exc:  # noqa: BLE001 - the later group captures report this reason
            group_failure = f"creating the group failed: {type(exc).__name__}: {exc}"
            s.log(group_failure)
    with s.capture("tab-grid-group-header", label="tab grid with a group card") as shot:
        ensure_tray(s, BANNER_NORMAL, "normal tabs")
        require_group(s, group_failure)
        shot.take(settle=1.0)
    with s.capture("08-tab-group-menu", label="tab group menu (three dots on the group card)") as shot:
        ensure_tray(s, BANNER_NORMAL, "normal tabs")
        require_group(s, group_failure)
        s.dev.tap(GROUP_MORE, timeout=8, settle=1.5)
        if s.dev.wait_for(GROUP_MENU_UNGROUP, timeout=8) is None:
            raise StepError("the tab group menu did not open")
        shot.take(settle=0.5)
        s.dev.back()
    with s.capture("02-tab-groups-list", label="tab groups list") as shot:
        ensure_tray(s, BANNER_GROUPS, "tab groups")
        require_group(s, group_failure)
        shot.take(settle=1.0)
    with s.capture("03-tab-group-sheet", label="tab group sheet (group opened)") as shot:
        ensure_tray(s, BANNER_GROUPS, "tab groups")
        require_group(s, group_failure)
        s.dev.tap(GROUP_CARD, timeout=8, settle=2.0)
        if s.dev.wait_for(SHEET_HANDLE, timeout=8) is None:
            raise StepError("the tab group sheet did not open")
        shot.take(settle=0.5)
        s.dev.back()
    with s.capture("01-synced-tabs", label="synced tabs page with its overflow menu") as shot:
        ensure_tray(s, BANNER_SYNCED, "synced tabs")
        s.dev.tap(TRAY_MENU, timeout=8, settle=1.5)
        s.dev.wait_for(SYNCED_MENU_ACCOUNT, timeout=6)
        shot.take(settle=0.5, note="signed out: no account on the emulator, so no synced devices or tabs")
        s.dev.back()
    close_tray(s)


def private_tab_tray(s: Session) -> None:
    with s.capture("12-tab-tray-header", private=True, label="tab tray header (private tabs)") as shot:
        load_page(s, f"{s.server}/page?private=1", "10.0.2.2", private=True)
        open_tray(s)
        show_page(s, BANNER_PRIVATE, "private tabs")
        s.dev.try_tap(LOCK_BANNER_DISMISS, timeout=2)
        shot.take(settle=1.0)
    close_tray(s)
