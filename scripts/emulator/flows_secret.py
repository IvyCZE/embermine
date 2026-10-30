"""Secret settings: the Settings list before the unlock, after five taps on the About logo, and after a restart."""
from __future__ import annotations

from scripts.emulator import uidump
from scripts.emulator.device import StepError
from scripts.emulator.flows_settings import ensure_settings_list, open_row, open_settings
from scripts.emulator.session import Session
from scripts.emulator.uidump import Selector

LOGO = Selector(id="wordmark")
SECRET_ROW = Selector(label=r"Secret [Ss]ettings")
ABOUT_ROW = r"About (Firefox|Embermine)"
LOGO_TAPS = 5
# Where the About logo is drawn when its resource id is missing from the dump: centred, near the top.
LOGO_FALLBACK = (0.5, 0.17)


def scroll_settings_to_end(s: Session) -> None:
    for _ in range(10):
        s.dev.scroll_down()


def secret_row_note(s: Session) -> str:
    present = uidump.find_first(s.dev.dump("secret-row-check", save=True), SECRET_ROW) is not None
    return "'Secret Settings' row on screen" if present else "no 'Secret Settings' row on screen"


def tap_about_logo(s: Session) -> None:
    open_row(s, ABOUT_ROW)
    nodes = s.dev.dump("about-for-logo", save=True)
    logo = uidump.find_first(nodes, LOGO)
    if logo is not None:
        x, y = logo.center
    else:
        width, height = uidump.screen_size(nodes)
        x, y = int(width * LOGO_FALLBACK[0]), int(height * LOGO_FALLBACK[1])
        s.log("About logo not found by id, tapping its usual position")
    for _ in range(LOGO_TAPS):
        s.dev.tap_xy(x, y)
        s.dev.sleep(0.6)
    s.dev.back()
    s.dev.sleep(1.0)


def secret_settings(s: Session) -> None:
    with s.capture("secret-settings-before", label="Settings list end, before the About logo was tapped") as shot:
        open_settings(s)
        scroll_settings_to_end(s)
        shot.take(settle=1.0, note=secret_row_note(s))
    ensure_settings_list(s)
    unlocked = False
    with s.capture("secret-settings-unlocked", label="Settings list end, after five taps on the About logo") as shot:
        s.dev.scroll_top()
        tap_about_logo(s)
        ensure_settings_list(s)
        scroll_settings_to_end(s)
        shot.take(settle=1.0, note=secret_row_note(s))
        unlocked = s.dev.visible(SECRET_ROW)
    with s.capture("secret-settings-screen", label="Secret settings screen") as shot:
        if not unlocked:
            raise StepError("the Secret Settings row did not appear after five logo taps")
        s.dev.tap(SECRET_ROW, timeout=8, settle=2.5)
        shot.take(settle=1.0)
        s.dev.back()
    with s.capture("secret-settings-after-restart", label="Settings list end, after force-stop and relaunch") as shot:
        s.force_stop()
        s.deep_link("settings")
        if s.dev.wait_for(Selector(label=r"Settings"), timeout=30) is None:
            raise StepError("Settings did not open after the relaunch")
        scroll_settings_to_end(s)
        shot.take(settle=1.0, note=secret_row_note(s))
