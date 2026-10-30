"""Device preparation: night mode, forced system palette, network, APK install and app metadata."""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from scripts.emulator.device import Adb
from scripts.emulator.session import LaunchError

# A clearly green Material You palette: unmistakably different from Firefox violet.
GREEN_SEED = "2E9E4F"
PALETTE_SETTING = "theme_customization_overlay_packages"
NOTIFICATIONS_PERMISSION = "android.permission.POST_NOTIFICATIONS"


def palette_json(seed: str = GREEN_SEED) -> str:
    return json.dumps(
        {
            "android.theme.customization.system_palette": seed,
            "android.theme.customization.accent_color": seed,
            "android.theme.customization.theme_style": "TONAL_SPOT",
            "android.theme.customization.color_source": "preset",
        },
        separators=(",", ":"),
    )


ARGB_TOKEN = re.compile(r"0x(ff[0-9a-fA-F]{6})")


def is_greenish(argb_hex: str) -> bool:
    r, g, b = (int(argb_hex[i : i + 2], 16) for i in (2, 4, 6))
    return g > r and g > b


def accent_lines(adb: Adb) -> list[str]:
    return [ln.strip() for ln in adb.shell("cmd overlay dump").splitlines() if "system_accent1_500" in ln]


def resolved_accent(adb: Adb) -> str:
    """Opaque ARGB value of system_accent1_500 as resolved by the overlay manager, '' when unknown.
    Resource ids (0x0106....) also appear on these lines and are not colors, hence the ff alpha filter."""
    for line in accent_lines(adb):
        tokens = ARGB_TOKEN.findall(line)
        if tokens:
            return tokens[-1].lower()
    return ""


def force_palette(adb: Adb, log: Callable[[str], None], sleep: Callable[[float], None], seed: str = GREEN_SEED) -> list[str]:
    """Force a green palette and return evidence lines (setting read-back, accent overlays, resolved tone).

    The overlay manager applies the setting asynchronously and sometimes after a long delay on a busy
    emulator, so the setting is rewritten until the resolved accent tone is green."""
    value = palette_json(seed)
    accent = ""
    for attempt in range(1, 5):
        # adb joins its arguments into one remote command line, so the JSON gets its own layer of quoting.
        adb.shell(f"settings put secure {PALETTE_SETTING} '{value}'")
        for _ in range(8):
            sleep(4)
            accent = resolved_accent(adb)
            if accent and is_greenish(accent):
                break
        if accent and is_greenish(accent):
            break
        log(f"palette attempt {attempt}: accent tone {accent or 'unknown'}")
        if attempt < 4:
            adb.shell(f"settings delete secure {PALETTE_SETTING}")
            sleep(3)
    readback = adb.shell(f"settings get secure {PALETTE_SETTING}").strip()
    overlays = [
        line.strip()
        for line in adb.shell("cmd overlay list android").splitlines()
        if re.search(r"accent|palette|theme_customization|color", line, re.IGNORECASE)
    ]
    evidence = [
        f"forced palette seed #{seed} (system_palette + accent_color, color_source preset)",
        f"{PALETTE_SETTING} read back: {readback}",
        f"palette applied: {'yes' if seed.lower() in readback.lower() else 'NO (read-back differs)'}",
        f"resolved system_accent1_500: {('0x' + accent) if accent else 'not reported'}"
        + (" (green)" if accent and is_greenish(accent) else " (NOT green)"),
    ]
    if overlays:
        evidence.append("color overlays: " + "; ".join(overlays[:6]))
    for line in evidence:
        log(line)
    log("overlay dump accent lines: " + " | ".join(accent_lines(adb)[:3]))
    return evidence


def set_night_mode(adb: Adb, theme: str, log: Callable[[str], None]) -> str:
    adb.shell(f"cmd uimode night {'yes' if theme == 'dark' else 'no'}")
    state = adb.shell("cmd uimode night").strip()
    log(f"uimode night: {state}")
    return state


def wake_and_stay_on(adb: Adb) -> None:
    adb.shell("settings put system screen_off_timeout 1800000")
    adb.shell("svc power stayon true")
    adb.shell("input keyevent KEYCODE_WAKEUP")
    adb.shell("wm dismiss-keyguard")
    adb.shell("input keyevent KEYCODE_HOME")


def suppress_error_dialogs(adb: Adb) -> None:
    """The software-rendered emulator makes the stock launcher miss ANR deadlines; the modal
    'Pixel Launcher isn't responding' dialog then swallows every tap aimed at the app."""
    adb.shell("settings put global hide_error_dialogs 1")
    adb.shell("settings put secure anr_show_background 0")


def disable_wifi(adb: Adb, log: Callable[[str], None], sleep: Callable[[float], None]) -> str:
    """The emulator's -tcpdump only sees the cellular NIC; with Wi-Fi on, app traffic bypasses it."""
    adb.shell("svc wifi disable")
    sleep(5)
    line = adb.shell("dumpsys connectivity | grep -m1 -E 'Active default network|mDefaultNetwork'").strip()
    log(f"svc wifi disable done; default network: {line or 'unknown'}")
    return line


def install_apk(adb: Adb, apk: Path, log: Callable[[str], None]) -> None:
    if not apk.is_file():
        raise LaunchError(f"APK not found: {apk}")
    proc = adb.run("install", "-r", str(apk), timeout=600)
    out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    log(f"adb install -r {apk.name}: {out}")
    if proc.returncode != 0 or "Success" not in out:
        raise LaunchError(f"adb install failed: {out[:300]}")


def grant_notifications(adb: Adb, package: str, log: Callable[[str], None]) -> None:
    out = adb.shell(f"pm grant {package} {NOTIFICATIONS_PERMISSION}").strip()
    log(f"pm grant {NOTIFICATIONS_PERMISSION}: {out or 'ok'}")


def find_apk(directory: Path) -> Path:
    apks = sorted(directory.glob("embermine-*-x86_64.apk"))
    if len(apks) != 1:
        raise LaunchError(f"expected exactly one x86_64 APK in {directory}, found {[a.name for a in apks]}")
    return apks[0]


def apk_package_and_label(apk_info: Path, apk_name: str) -> tuple[str, str]:
    """Package name and application label of one APK from apk-info.txt (written by scripts/apk-info.sh)."""
    section = ""
    for block in apk_info.read_text(encoding="utf-8").split("=== ")[1:]:
        if block.startswith(apk_name):
            section = block
            break
    package = re.search(r"^package: name='([^']+)'", section, re.MULTILINE)
    label = re.search(r"^application-label:'([^']*)'", section, re.MULTILINE)
    if package is None:
        raise LaunchError(f"{apk_name} not found in {apk_info}")
    return package[1], (label[1] if label else "")
