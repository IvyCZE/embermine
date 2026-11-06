"""Secret settings: the About logo before and after five taps, the Settings list around the unlock, and after a restart."""
from __future__ import annotations

from scripts.emulator import uidump
from scripts.emulator.device import StepError
from scripts.emulator.flows_settings import ABOUT_FIRST_ROW, ensure_settings_list, open_row, open_settings
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


def logo_position(s: Session) -> tuple[int, int]:
    nodes = s.dev.dump("about-for-logo", save=True)
    logo = uidump.find_first(nodes, LOGO)
    if logo is not None:
        return logo.center
    width, height = uidump.screen_size(nodes)
    s.log("About logo not found by id, tapping its usual position")
    return int(width * LOGO_FALLBACK[0]), int(height * LOGO_FALLBACK[1])


def tap_logo_five_times(s: Session) -> None:
    if not s.dev.visible(ABOUT_FIRST_ROW):
        raise StepError("the About screen is not open, so the logo taps were not sent")
    x, y = logo_position(s)
    for _ in range(LOGO_TAPS):
        s.dev.tap_xy(x, y)
        s.dev.sleep(0.6)


def secret_settings(s: Session) -> None:
    with s.capture("secret-settings-before", label="Settings list end, before the About logo was tapped") as shot:
        open_settings(s)
        scroll_settings_to_end(s)
        shot.take(settle=1.0, note=secret_row_note(s))
        if s.dev.visible(SECRET_ROW):
            raise StepError("the Secret Settings row was there before the About logo was tapped")
    ensure_settings_list(s)
    with s.capture("about-before-logo-taps", label="About screen before the logo taps") as shot:
        open_row(s, ABOUT_ROW, wait=ABOUT_FIRST_ROW)
        shot.take(settle=1.0, note="no logo taps yet")
    with s.capture("about-after-logo-taps", label="About screen after five logo taps") as shot:
        tap_logo_five_times(s)
        shot.take(settle=0.5, note="five taps sent to the About logo")
    ensure_settings_list(s)
    unlocked = False
    with s.capture("secret-settings-unlocked", label="Settings list end, after five taps on the About logo") as shot:
        s.dev.scroll_top()
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
        if not s.dev.visible(SECRET_ROW):
            raise StepError("the Secret Settings row was gone after force-stop and relaunch")
