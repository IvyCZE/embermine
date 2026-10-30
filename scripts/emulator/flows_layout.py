"""Layout options in Settings > Customize that change what the browser screen looks like."""
from __future__ import annotations

from scripts.emulator.device import StepError
from scripts.emulator.flows_browse import go_home, load_page
from scripts.emulator.flows_settings import open_row, open_settings
from scripts.emulator.session import Session
from scripts.emulator.uidump import Selector


def set_toolbar_layout(s: Session, option: str) -> None:
    """Settings > Customize > Toolbar layout: Simple or Expanded (the expanded one adds the bottom navigation bar)."""
    open_settings(s)
    open_row(s, r"Customize")
    row = s.dev.scroll_to(Selector(text=option), max_swipes=8)
    s.dev.tap_node(row)
    s.dev.sleep(1.5)
    s.log(f"toolbar layout set to {option}")
    s.dev.back()
    s.dev.back()
    s.dev.sleep(1.0)


def bottom_navigation_bar(s: Session) -> None:
    """Turn the expanded toolbar on, photograph a loaded page with its navigation bar, then restore the simple layout."""
    switched = False
    try:
        with s.capture("bottom-navigation-bar", label="bottom navigation bar (expanded toolbar layout)") as shot:
            set_toolbar_layout(s, "Expanded")
            switched = True
            go_home(s)
            load_page(s, f"{s.server}/page", "10.0.2.2", private=False)
            shot.take(settle=1.0, note="Settings > Customize > Toolbar layout > Expanded; restored to Simple afterwards")
    finally:
        # The layout is a persistent preference: leaving it on would change every later capture.
        try:
            set_toolbar_layout(s, "Simple")
        except StepError as exc:
            s.log(f"restoring the simple toolbar layout failed: {exc}")
        except Exception as exc:  # noqa: BLE001
            s.log(f"restoring the simple toolbar layout failed: {type(exc).__name__}: {exc}")
