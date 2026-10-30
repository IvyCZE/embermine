"""Themed launcher icon: enable themed icons in the Pixel launcher and put the app on the home screen."""
from __future__ import annotations

import re

from scripts.emulator import uidump
from scripts.emulator.device import StepError
from scripts.emulator.session import Session
from scripts.emulator.uidump import Selector


def launcher_package(s: Session) -> str:
    out = s.dev.adb.shell("cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME")
    line = out.strip().splitlines()[-1] if out.strip() else ""
    package = line.split("/", 1)[0]
    if not re.fullmatch(r"[\w.]+", package):
        raise StepError(f"cannot find the home launcher package (got {line!r})")
    return package


def enable_themed_icons(s: Session, launcher: str) -> None:
    """The Pixel launcher exposes its grid options through a content provider."""
    for path in ("set_icon_themed", "icon_themed"):
        uri = f"content://{launcher}.grid_control/{path}"
        result = s.dev.adb.shell(f"content update --uri {uri} --bind boolean_value:b:true").strip()
        s.log(f"update {path}: {result or 'ok'}")
    state = s.dev.adb.shell(f"content query --uri content://{launcher}.grid_control/icon_themed").strip()
    s.log(f"icon_themed after update: {state[:120]}")


def place_on_home_screen(s: Session, label_pattern: str) -> None:
    """Drag the app icon out of the app drawer onto the home screen."""
    width, height = s.dev.screen_size()
    s.dev.home()
    s.dev.swipe(width // 2, int(height * 0.85), width // 2, int(height * 0.25), 300)
    s.dev.sleep(2.0)
    icon = s.dev.wait_for(Selector(label=label_pattern), timeout=8, label="drawer")
    if icon is None:
        # The drawer search finds the app even when it is below the fold.
        s.dev.tap(Selector(label=r"Search.*"), timeout=5)
        s.dev.type_text(label_pattern.split("|")[0])
        icon = s.dev.wait_for(Selector(label=label_pattern), timeout=8, label="drawer-search")
    if icon is None:
        raise StepError(f"app icon {label_pattern!r} not found in the app drawer")
    x, y = icon.center
    s.log(f"dragging {icon.label!r} from {x},{y} to the home screen")
    s.dev.adb.shell(f"input draganddrop {x} {y} {int(width * 0.25)} {int(height * 0.54)} 2500")
    s.dev.sleep(1.5)
    s.dev.home()
    s.dev.sleep(2.0)


def themed_icon_capture(s: Session, label_pattern: str) -> None:
    label = "launcher themed icon (home screen, themed icons on)"
    with s.capture("launcher-themed-icon", label=label, file=f"launcher-themed-icon_{s.theme}.png", combination=s.theme) as shot:
        launcher = launcher_package(s)
        enable_themed_icons(s, launcher)
        s.dev.home()
        s.dev.sleep(2.0)
        place_on_home_screen(s, label_pattern)
        s.dev.sleep(3.0)
        placed = uidump.find_first(s.dev.dump("home-with-icon"), Selector(label=label_pattern))
        shot.take(settle=0.5, note="app icon found in the home screen dump" if placed else "app icon not found in the home screen dump")
