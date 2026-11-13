"""Device preparation: night mode, forced system palette, network, APK install and app metadata."""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
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
OVERLAY_LINE = re.compile(r"^\s*\[(.)\]\s+(\S+)")
# ThemeOverlayController maps system_palette -> neutral, dynamic_color -> dynamic and accent_color -> accent.
ACCENT_OVERLAY = "com.android.systemui:accent"
PALETTE_OVERLAY = "com.android.systemui:neutral"
# Compose dynamicLightColorScheme reads android.R.color.system_primary_light from this overlay on API 34,
# and idmap2d applies it last, so it must be enabled and idmapped before the palette counts as applied.
DYNAMIC_OVERLAY = "com.android.systemui:dynamic"
REQUIRED_OVERLAYS = (ACCENT_OVERLAY, PALETTE_OVERLAY, DYNAMIC_OVERLAY)
ACCENT_TONE = "system_accent1_500"
PRIMARY_TONE = "system_primary_light"
IDMAP_PROPERTY = "init.svc.idmap2d"
PALETTE_ATTEMPTS = 5
PALETTE_POLLS = 8
POLL_SECONDS = 4
# From this attempt on, overlays that stay disabled are also enabled directly.
ENABLE_FROM_ATTEMPT = 3
BOOT_POLL_SECONDS = 2
BOOT_TIMEOUT_SECONDS = 180
BOOT_FINISHED_LINE = "Finished processing BOOT_COMPLETED for u0"


class PaletteError(LaunchError):
    """The forced palette is not active; the evidence lines belong in screens-index.md."""

    def __init__(self, message: str, evidence: list[str]) -> None:
        super().__init__(message)
        self.evidence = evidence


def is_greenish(argb_hex: str) -> bool:
    r, g, b = (int(argb_hex[i : i + 2], 16) for i in (2, 4, 6))
    return g > r and g > b


def dump_value(dump: str, tone: str) -> str:
    """Opaque ARGB value of one color resource in a `cmd overlay dump` output, '' when the dump lacks it.
    The dump reports the value of a disabled overlay too, so it never proves the palette is active.
    Resource ids (0x0106....) also appear on these lines and are not colors, hence the ff alpha filter."""
    for line in dump.splitlines():
        if tone in line:
            tokens = ARGB_TOKEN.findall(line)
            if tokens:
                return tokens[-1].lower()
    return ""


def overlay_states(listing: str) -> dict[str, bool]:
    """Overlay name -> enabled, from `cmd overlay list` lines like '[x] name' (enabled) and '[ ] name'."""
    states: dict[str, bool] = {}
    for line in listing.splitlines():
        match = OVERLAY_LINE.match(line)
        if match:
            states[match[2]] = match[1].lower() == "x"
    return states


@dataclass
class PaletteState:
    readback_ok: bool
    overlays: dict[str, bool]
    accent: str
    # '' when the overlay dump does not report system_primary_light (then it does not block)
    primary_light: str = ""
    # value of init.svc.idmap2d: 'running' while an idmap transaction is in flight, '' when unset
    idmap2d: str = ""

    @property
    def overlays_enabled(self) -> bool:
        return all(self.overlays.get(name, False) for name in REQUIRED_OVERLAYS)

    @property
    def green(self) -> bool:
        return bool(self.accent) and is_greenish(self.accent)

    @property
    def primary_green(self) -> bool:
        return not self.primary_light or is_greenish(self.primary_light)

    @property
    def idmap_idle(self) -> bool:
        return self.idmap2d != "running"

    @property
    def applied(self) -> bool:
        """Only enabled overlays, a green accent and primary, and an idle idmap2d count; the green dump value alone does not."""
        return self.readback_ok and self.overlays_enabled and self.green and self.primary_green and self.idmap_idle

    def overlay_lines(self) -> list[str]:
        lines = []
        for name in REQUIRED_OVERLAYS:
            marker = "[x]" if self.overlays.get(name) else "[ ]" if name in self.overlays else "(not listed)"
            lines.append(f"{marker} {name}")
        return lines

    def problems(self) -> list[str]:
        found = []
        if not self.readback_ok:
            found.append("setting read-back differs")
        found += [f"{name} {'is disabled' if name in self.overlays else 'is not listed'}" for name in REQUIRED_OVERLAYS if not self.overlays.get(name)]
        if not self.green:
            found.append(f"accent tone {('0x' + self.accent) if self.accent else 'unknown'} is not green")
        if not self.primary_green:
            found.append(f"{PRIMARY_TONE} tone 0x{self.primary_light} is not green")
        if not self.idmap_idle:
            found.append("idmap2d is running (overlay transaction in flight)")
        return found


def read_palette_state(adb: Adb, seed: str = GREEN_SEED) -> PaletteState:
    readback = adb.shell(f"settings get secure {PALETTE_SETTING}").strip()
    dump = adb.shell("cmd overlay dump")
    return PaletteState(
        readback_ok=seed.lower() in readback.lower(),
        overlays=overlay_states(adb.shell("cmd overlay list android")),
        accent=dump_value(dump, ACCENT_TONE),
        primary_light=dump_value(dump, PRIMARY_TONE),
        idmap2d=adb.shell(f"getprop {IDMAP_PROPERTY}").strip(),
    )


def describe_state(state: PaletteState) -> str:
    return "applied" if state.applied else "NOT applied (" + "; ".join(state.problems()) + ")"


def force_palette(adb: Adb, log: Callable[[str], None], sleep: Callable[[float], None], seed: str = GREEN_SEED) -> list[str]:
    """Force a green palette and return evidence lines; raise PaletteError when it never becomes active.

    The overlay manager applies the setting asynchronously, sometimes after a long delay on a busy
    emulator, and sometimes leaves the accent overlay disabled although the dump already shows the green
    value. The palette therefore counts as applied only when `cmd overlay list` shows the accent and
    palette overlays enabled, and the setting is rewritten (after a delete) until that holds."""
    value = palette_json(seed)
    state = PaletteState(False, {}, "")
    for attempt in range(1, PALETTE_ATTEMPTS + 1):
        # adb joins its arguments into one remote command line, so the JSON gets its own layer of quoting.
        adb.shell(f"settings put secure {PALETTE_SETTING} '{value}'")
        for _ in range(PALETTE_POLLS):
            sleep(POLL_SECONDS)
            state = read_palette_state(adb, seed)
            if state.applied:
                break
        if state.applied:
            break
        log(f"palette attempt {attempt}: {describe_state(state)}")
        if attempt < PALETTE_ATTEMPTS:
            if attempt >= ENABLE_FROM_ATTEMPT:
                for name in REQUIRED_OVERLAYS:
                    if not state.overlays.get(name):
                        log(f"cmd overlay enable {name}: {adb.shell(f'cmd overlay enable --user current {name}').strip() or 'ok'}")
            adb.shell(f"settings delete secure {PALETTE_SETTING}")
            sleep(3)
    evidence = palette_evidence(adb, state, seed)
    for line in evidence:
        log(line)
    if not state.applied:
        raise PaletteError(f"forced palette is not active after {PALETTE_ATTEMPTS} attempts: " + "; ".join(state.problems()), evidence)
    return evidence


def palette_evidence(adb: Adb, state: PaletteState, seed: str = GREEN_SEED) -> list[str]:
    readback = adb.shell(f"settings get secure {PALETTE_SETTING}").strip()
    accent = state.accent
    primary = state.primary_light
    return [
        f"forced palette seed #{seed} (system_palette + accent_color, color_source preset)",
        f"{PALETTE_SETTING} read back: {readback}",
        "overlays from cmd overlay list android: " + "; ".join(state.overlay_lines()),
        f"{ACCENT_TONE} reported by cmd overlay dump (also shown for a disabled overlay): {('0x' + accent) if accent else 'not reported'}"
        + (" (green)" if state.green else " (NOT green)"),
        f"{PRIMARY_TONE} reported by cmd overlay dump: {('0x' + primary) if primary else 'not reported (not checked)'}"
        + ("" if not primary else " (green)" if state.primary_green else " (NOT green)"),
        f"idmap2d service: {state.idmap2d or 'unset'} ({'idle' if state.idmap_idle else 'running'})",
        f"palette applied: {'yes' if state.applied else 'NO (' + '; '.join(state.problems()) + ')'}",
    ]


def confirm_palette(adb: Adb, log: Callable[[str], None], sleep: Callable[[float], None], seed: str = GREEN_SEED) -> list[str]:
    """Check that the forced palette is still active and force it again when it was lost; returns evidence lines."""
    state = read_palette_state(adb, seed)
    if state.applied:
        return palette_evidence(adb, state, seed)
    log(f"palette lost: {describe_state(state)}")
    return force_palette(adb, log, sleep, seed)


def user_unlocked(adb: Adb) -> bool:
    if "RUNNING_UNLOCKED" in adb.shell("am get-started-user-state 0"):
        return True
    return "mIsUserUnlocked=true" in adb.shell("dumpsys user")


def wait_for_boot_settled(
    adb: Adb, log: Callable[[str], None], sleep: Callable[[float], None], timeout: float = BOOT_TIMEOUT_SECONDS
) -> str:
    """Wait until user 0 is RUNNING_UNLOCKED and the ActivityManager has finished BOOT_COMPLETED for it.

    Starting the palette or the app earlier races the overlay manager: SystemUI's dynamic overlay can still be
    idmapping when the first window is drawn, so the first capture shows Android's default colors.
    The elapsed time is the sleep time between polls (shell calls are not counted). A timeout is logged as a
    warning and does not stop the run. Returns the note for screens-index.md."""
    waited = 0.0
    while True:
        unlocked = user_unlocked(adb)
        finished = BOOT_FINISHED_LINE in adb.shell("logcat -d -b system -s ActivityManager:I")
        if unlocked and finished:
            note = f"user 0 RUNNING_UNLOCKED and BOOT_COMPLETED finished after about {waited:.0f} s of polling"
            log(note)
            return note
        if waited >= timeout:
            note = (
                f"WARNING: boot did not settle within {timeout:.0f} s "
                f"(user 0 unlocked: {unlocked}, BOOT_COMPLETED finished: {finished}); continuing"
            )
            log(note)
            return note
        sleep(BOOT_POLL_SECONDS)
        waited += BOOT_POLL_SECONDS


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


def prepare_fresh_install(adb: Adb, package: str, log: Callable[[str], None]) -> str:
    """The walk starts with a fresh install: an earlier install of the app on this device loses its data first.

    The emulator is created for each job, so this normally finds nothing. Returns the note for screens-index.md."""
    installed = adb.shell(f"pm path {package}").strip().startswith("package:")
    if installed:
        cleared = adb.shell(f"pm clear {package}").strip()
        note = f"an earlier install was found, its app data was cleared ({cleared or 'ok'})"
    else:
        note = "the app was not installed before this run, so the first launch shows onboarding"
    log(f"fresh install check: {note}")
    return note


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
