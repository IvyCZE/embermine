"""Entry point of the emulator job: install the APK, walk the app and write screenshots and reports.

usage: python3 -m scripts.emulator.run --variant light|dark --apk-dir DIR --out DIR --debug DIR

Install and launch failures end the run with a non-zero exit code. Every capture after that is fail-soft:
a screen that cannot be reached is listed as MISSING (with the reason) in screens-index.md.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts.emulator import coinstall, devsetup, flows_browse, flows_motion, flows_settings, launcher, logcat_scan
from scripts.emulator.device import Adb, Device
from scripts.emulator.naming import ScreenIndex, capture_name, check_index_matches_files
from scripts.emulator.session import LaunchError, Session
from scripts.emulator.testserver import WalkServer

SERVER_PORT = 8765
FLOW_BUDGET_SECONDS = 28 * 60
Expected = tuple[str, str, bool]  # file stem, index label, private


@dataclass
class Flow:
    name: str
    run: Callable[[Session], None]
    expected: list[Expected]
    private: bool = False


def flow_list() -> list[Flow]:
    f_browse, f_set, f_motion = flows_browse, flows_settings, flows_motion

    def motion(s: Session, position: str) -> None:
        f_motion.page_load(s, position)
        f_motion.pull_to_refresh(s, position)

    page_stems = ["10-toolbar", "14-main-menu", "13-site-protection-panel", "13-site-protection-panel-http"]
    motion_expected = [
        (f"{kind}-{pos}-{state}", f"{kind}, {pos} toolbar, {state}", False)
        for pos in ("top", "bottom")
        for kind, states in (("page-load", ("loading", "loaded")), ("pull-to-refresh", ("pulling", "reloading")))
        for state in states
    ]
    return [
        Flow("homepage", f_browse.homepage, [("04-homepage", "homepage", False)]),
        Flow("search", f_browse.search_bar_and_selector, [("search-bar", "search bar", False), ("11-search-selector", "search engine selector", False)]),
        Flow("pages", lambda s: f_browse.page_captures(s, private=False), [(p, p, False) for p in page_stems]),
        Flow("private homepage", lambda s: f_browse.homepage(s, private=True), [("04-homepage", "homepage", True)], private=True),
        Flow("private pages", lambda s: f_browse.page_captures(s, private=True), [(p, p, True) for p in page_stems], private=True),
        Flow("history", f_set.history, [("09-history", "history", False)]),
        Flow(
            "settings",
            f_set.settings_pages,
            [("05-settings", "settings root", False)]
            + [(stem, label, False) for stem, _, label in f_set.SUBPAGES]
            + [
                ("customize", "customize screen", False),
                ("settings-data-collection", "settings data collection page", False),
                ("settings-homepage", "homepage settings page", False),
                ("wallpaper-picker", "wallpaper picker", False),
                ("about", "about screen", False),
            ],
        ),
        Flow("about:config", f_set.about_config, [("about-config", "about:config page", False)]),
        Flow("motion", lambda s: f_motion.both_positions(s, motion), motion_expected),
    ]


def run_flow(s: Session, flow: Flow, deadline: float) -> None:
    s.log(f"=== flow: {flow.name}")
    reason = "flow did not reach this capture"
    if time.monotonic() > deadline:
        reason = "run time budget exhausted before this flow started"
        s.log(reason)
    else:
        try:
            if flow.private:
                if not s.private_screenshots:
                    flows_settings.allow_private_screenshots(s)
                    s.private_screenshots = True
            else:
                s.ensure_normal()
            flow.run(s)
        except LaunchError:
            raise
        except Exception as exc:  # noqa: BLE001 - a broken flow must not stop the other flows
            reason = f"flow '{flow.name}' aborted: {type(exc).__name__}: {exc}"
            s.log(reason)
    recorded = {e.file for e in s.index.entries}
    for stem, label, private in flow.expected:
        file = capture_name(stem, theme=s.theme, dynamic=s.dynamic, private=private)
        if file not in recorded:
            combination = f"dynamic-off {s.theme}{' private' if private else ''}"
            s.index.missing(label, combination, file, reason)
    try:
        s.dev.sweep_dialogs()
    except Exception:  # noqa: BLE001
        pass


def write_logcat_report(s: Session, out: Path) -> int:
    raw = s.dev.adb.run("logcat", "-d", "-v", "threadtime", timeout=120).stdout.decode("utf-8", errors="replace")
    (s.debug / "logcat-full.txt").write_text(raw, encoding="utf-8")
    text, ours = logcat_scan.report(raw, s.package)
    (out / "logcat-crash.txt").write_text(text, encoding="utf-8")
    s.index.add_report("logcat-crash.txt", f"FATAL EXCEPTION / ANR scan of the whole session: {ours} finding(s) for {s.package}")
    s.log(f"logcat scan: {ours} finding(s) for {s.package}")
    return ours


def write_coinstall(s: Session, out: Path, firefox_version: str, work: Path) -> None:
    def launch_check() -> str:
        s.force_stop()
        s.dev.adb.shell(f"monkey -p {s.package} -c android.intent.category.LAUNCHER 1")
        focused = s.wait_focus(20)
        return f"launch via monkey: window focus {'yes' if focused else 'NO'}; process {'running' if s.is_running() else 'NOT running'}"

    try:
        lines = coinstall.run(s.dev.adb, s.package, firefox_version, work, launch_check)
    except Exception as exc:  # noqa: BLE001
        lines = [f"co-install check failed: {type(exc).__name__}: {exc}"]
    (out / "coinstall.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    s.index.add_report("coinstall.txt", "official Firefox and F-Droid Fennec installed next to the app, pm list packages")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("light", "dark"), required=True)
    parser.add_argument("--apk-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--debug", type=Path, required=True)
    parser.add_argument("--firefox-version-file", type=Path, default=Path("firefox-version.txt"))
    parser.add_argument("--serial")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    args.debug.mkdir(parents=True, exist_ok=True)
    adb = Adb(args.serial)
    firefox_version = args.firefox_version_file.read_text(encoding="utf-8").strip()
    started = time.monotonic()

    def log(message: str) -> None:
        print(f"[{time.monotonic() - started:7.1f}s] {message}", flush=True)

    dev = Device(adb, dump_dir=args.debug / "ui", log=log)
    index = ScreenIndex(title=f"screens-index ({args.variant})")
    server = WalkServer(SERVER_PORT)
    session: Session | None = None
    exit_code = 0
    try:
        apk = devsetup.find_apk(args.apk_dir)
        package, label = devsetup.apk_package_and_label(args.apk_dir / "apk-info.txt", apk.name)
        app_label = r"Embermine|Firefox" if not label else rf"{label}|Embermine|Firefox"
        session = Session(dev, package, args.variant, args.out, args.debug, index, server=f"http://10.0.2.2:{SERVER_PORT}")
        index.header = [
            f"Variant: {args.variant} theme, API 34 google_apis x86_64 emulator, Pixel 6 profile",
            f"App under test: {apk.name} (package {package}, label {label!r})",
            "Combination naming: dynamic-off means the 'Use wallpaper colors' switch does not exist yet; the green system palette is forced.",
        ]
        devsetup.wake_and_stay_on(adb)
        devsetup.suppress_error_dialogs(adb)
        night = devsetup.set_night_mode(adb, args.variant, log)
        index.header.append(f"uimode night: {night}")
        index.header += ["Palette: " + line for line in devsetup.force_palette(adb, log, time.sleep)]
        devsetup.install_apk(adb, apk, log)
        devsetup.grant_notifications(adb, package, log)
        index.header.append("Wi-Fi: " + (devsetup.disable_wifi(adb, log, time.sleep) or "disabled with svc wifi disable"))
        server.start()

        session.launch_from_launcher()
        flows_browse.onboarding_first_screen(session)
        flows_browse.complete_onboarding(session)
        deadline = time.monotonic() + FLOW_BUDGET_SECONDS
        for flow in flow_list():
            run_flow(session, flow, deadline)
        launcher.themed_icon_capture(session, app_label)
    except LaunchError as exc:
        log(f"FATAL: {exc}")
        index.header.append(f"RUN ABORTED: {exc}")
        exit_code = 1
    finally:
        server.close()
        if session is not None:
            try:
                write_logcat_report(session, args.out)
            except Exception as exc:  # noqa: BLE001
                log(f"logcat report failed: {exc}")
            if exit_code == 0:
                write_coinstall(session, args.out, firefox_version, args.debug / "coinstall-work")
            (args.debug / "visited-urls.txt").write_text("\n".join(session.visited) + "\n", encoding="utf-8")
        index.add_report("network-hosts.txt", "DNS and TLS SNI host names of the scripted session, written by the workflow from the packet capture")
        index.write(args.out / "screens-index.md")
        text = (args.out / "screens-index.md").read_text(encoding="utf-8")
        for problem in check_index_matches_files(text, args.out, deferred=frozenset({"network-hosts.txt"})):
            log(f"index check: {problem}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
