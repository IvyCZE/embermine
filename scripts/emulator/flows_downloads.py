"""The Downloads screen with a finished, an active and a paused download, and the download notification.

The files come from the walk's own server (testserver.py): the big one is streamed slowly, so it is still running
when the screen is photographed, and it honours Range requests like a real host.
"""
from __future__ import annotations

from scripts.emulator import targets as t
from scripts.emulator.device import StepError
from scripts.emulator.flows_browse import go_home
from scripts.emulator.session import Session
from scripts.emulator.uidump import Selector

DOWNLOAD_BUTTON = (Selector(text=r"Download", clickable=True), Selector(text=r"Download"), Selector(desc=r"Download"))
MENU_DOWNLOADS = Selector(label=r"Downloads")
PAUSE = Selector(desc=r"Pause")
RESUME = Selector(desc=r"Resume")
DOWNLOADS_TITLE = Selector(label=r"Downloads")


def start_download(s: Session, path: str) -> str:
    """Open the file URL and confirm the download prompt. Returns a note about what happened."""
    s.open_url(f"{s.server}{path}")
    button = s.dev.wait_for(*DOWNLOAD_BUTTON, timeout=20, label="download-prompt")
    if button is None:
        s.dev.sleep(3.0)
        return f"{path}: no download prompt appeared"
    s.dev.tap_node(button)
    s.dev.sleep(3.0)
    return f"{path}: download confirmed"


def open_downloads_from_menu(s: Session) -> None:
    go_home(s)
    s.dev.tap(t.MENU_BUTTON)
    s.dev.tap(MENU_DOWNLOADS, timeout=10, settle=2.5)
    if s.dev.wait_for(DOWNLOADS_TITLE, timeout=10) is None:
        raise StepError("the Downloads screen did not open")


def shade_capture(s: Session) -> None:
    with s.capture("download-notification", label="notification shade with the running download") as shot:
        s.dev.adb.shell("cmd statusbar expand-notifications")
        s.dev.sleep(2.5)
        try:
            shot.take(settle=1.0)
        finally:
            s.dev.adb.shell("cmd statusbar collapse")
            s.dev.sleep(1.5)


def downloads(s: Session) -> None:
    notes = [start_download(s, "/small.bin"), start_download(s, "/big.bin")]
    s.log("downloads: " + "; ".join(notes))
    s.dev.sleep(4.0)
    shade_capture(s)
    active = False
    with s.capture("15-downloads", label="downloads screen (one finished and one running download)") as shot:
        open_downloads_from_menu(s)
        active = s.dev.wait_for(PAUSE, timeout=15, label="download-pause") is not None
        shot.take(settle=1.5, note="; ".join(notes) + ("" if active else "; no running download row (no Pause button) on screen"))
    with s.capture("downloads-active", label="downloads screen, download in progress") as shot:
        if not active:
            raise StepError("no running download on the Downloads screen: " + "; ".join(notes))
        shot.take(settle=3.0)
    with s.capture("downloads-paused", label="downloads screen, download paused") as shot:
        if not active:
            raise StepError("no running download on the Downloads screen to pause: " + "; ".join(notes))
        s.dev.tap(PAUSE, timeout=8, settle=1.5)
        if s.dev.wait_for(RESUME, timeout=10, label="download-resume") is None:
            raise StepError("the download row never showed a Resume button after Pause was tapped")
        shot.take(settle=2.0)
    s.dev.back()
