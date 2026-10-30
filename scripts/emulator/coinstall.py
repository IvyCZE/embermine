"""Install official Firefox and F-Droid Fennec next to the app under test and record what happens.

Every step is recorded, failures included: an install that Android refuses is a result, not an error.
"""
from __future__ import annotations

import json
from collections.abc import Callable
import time
import urllib.request
from pathlib import Path

from scripts.emulator import fdroid
from scripts.emulator.device import Adb

OFFICIAL_URL = (
    "https://archive.mozilla.org/pub/fenix/releases/{v}/android/fenix-{v}-android-x86_64/"
    "fenix-{v}.multi.android-x86_64.apk"
)
FENNEC_PACKAGE = "org.mozilla.fennec_fdroid"
PM_FILTER = "mozilla|fennec|embermine|fenix"


def download(url: str, dest: Path, attempts: int = 3) -> int:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=120) as response, dest.open("wb") as handle:  # noqa: S310
                while chunk := response.read(1 << 20):
                    handle.write(chunk)
            return dest.stat().st_size
        except OSError as exc:
            last = exc
            time.sleep(3 * (attempt + 1))
    raise OSError(f"download of {url} failed: {last}")


def install(adb: Adb, apk: Path) -> str:
    proc = adb.run("install", "-r", str(apk), timeout=600)
    return (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()


def package_summary(adb: Adb, package: str) -> str:
    out = adb.shell(f"dumpsys package {package} | grep -E 'versionName|versionCode|signatures|sharedUser|Signing|signing' | head -8")
    return out.strip() or "(not installed)"


def packages(adb: Adb) -> str:
    return adb.shell(f"pm list packages | grep -iE '{PM_FILTER}' | sort").strip() or "(none)"


def run(adb: Adb, package: str, firefox_version: str, work: Path, launch_check: Callable[[], str]) -> list[str]:
    work.mkdir(parents=True, exist_ok=True)
    out = [
        "# coinstall.txt: Embermine next to official Firefox and F-Droid Fennec (x86_64, API 34 emulator)",
        f"# app under test: {package}",
        "",
        "## pm list packages before",
        packages(adb),
        "",
        f"## Official Firefox {firefox_version} (x86_64) from archive.mozilla.org",
    ]
    official = work / "firefox-official.apk"
    url = OFFICIAL_URL.format(v=firefox_version)
    try:
        out.append(f"downloaded {download(url, official)} bytes from {url}")
        out.append("adb install -r: " + install(adb, official))
    except OSError as exc:
        out.append(f"SKIPPED: {exc}")
    out += ["", "## F-Droid Fennec (x86_64, latest in the F-Droid index)"]
    fennec = work / "fennec.apk"
    try:
        with urllib.request.urlopen(fdroid.INDEX_URL, timeout=300) as response:  # noqa: S310
            index = json.load(response)
        fennec_url, code, name = fdroid.newest_apk(index, FENNEC_PACKAGE, "x86_64")
        out.append(f"F-Droid index: {FENNEC_PACKAGE} {name} (versionCode {code})")
        out.append(f"downloaded {download(fennec_url, fennec)} bytes from {fennec_url}")
        out.append("adb install -r: " + install(adb, fennec))
    except (OSError, LookupError, ValueError) as exc:
        out.append(f"SKIPPED: {exc}")
    out += ["", "## pm list packages after", packages(adb), ""]
    for pkg in (package, FENNEC_PACKAGE):
        out += [f"## dumpsys package {pkg}", package_summary(adb, pkg), ""]
    out += ["## Embermine after the installs", launch_check()]
    return out
