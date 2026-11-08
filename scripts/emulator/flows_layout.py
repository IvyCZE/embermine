"""Layout options in Settings > Customize that change what the browser screen looks like."""
from __future__ import annotations

from scripts.emulator.flows_browse import go_home, load_page
from scripts.emulator.flows_settings import open_row, open_settings
from scripts.emulator.session import Session
from scripts.emulator.uidump import Selector

DEFAULT_SHORTCUT = "Add bookmark"
# (file stem, shortcut radio option, label for the index), in the order they are captured
SHORTCUT_CAPTURES = (
    ("bottom-navigation-bar-back", "Back", "bottom navigation bar, Back shortcut"),
    ("bottom-navigation-bar-home", "Homepage", "bottom navigation bar, Homepage shortcut"),
)


def set_customize_option(s: Session, option: str) -> None:
    """Settings > Customize: taps one radio option, a toolbar layout or a bottom navigation shortcut."""
    open_settings(s)
    open_row(s, r"Customize")
    row = s.dev.scroll_to(Selector(text=option), max_swipes=8)
    s.dev.tap_node(row)
    s.dev.sleep(1.5)
    s.log(f"customize option set to {option}")
    s.dev.back()
    s.dev.back()
    s.dev.sleep(1.0)


def _restore(s: Session, option: str) -> None:
    try:
        set_customize_option(s, option)
    except Exception as exc:  # noqa: BLE001 - a failed restore must not stop the other restore or the walk
        s.log(f"restoring {option!r} failed: {type(exc).__name__}: {exc}")


def bottom_navigation_bar(s: Session) -> None:
    """Expanded toolbar: photograph the default shortcut, then the Back and Homepage shortcuts, then restore the defaults."""
    shortcut_changed = False
    try:
        set_customize_option(s, "Expanded")
        with s.capture("bottom-navigation-bar", label="bottom navigation bar (expanded toolbar layout)") as shot:
            go_home(s)
            load_page(s, f"{s.server}/page", "10.0.2.2", private=False)
            shot.take(settle=1.0, note="Settings > Customize > Toolbar layout > Expanded, default Add bookmark shortcut")
        for stem, option, label in SHORTCUT_CAPTURES:
            with s.capture(stem, label=label) as shot:
                shortcut_changed = True
                set_customize_option(s, option)
                go_home(s)
                load_page(s, f"{s.server}/page", "10.0.2.2", private=False)
                shot.take(settle=1.0, note=f"Settings > Customize > Choose shortcut > {option}")
    finally:
        # Both are persistent preferences: leaving them changed would change every later capture.
        # The shortcut goes back first because its options are only listed while Expanded is on.
        if shortcut_changed:
            _restore(s, DEFAULT_SHORTCUT)
        _restore(s, "Simple")
