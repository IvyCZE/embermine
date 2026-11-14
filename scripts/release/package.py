#!/usr/bin/env python3
"""Check the artifacts of a release build and write its release notes.

Runs before anything can be published, in dry runs too. A failed check fails the run, so a broken or unsigned
build never reaches the publish job.
  usage: python3 -m scripts.release.package --dist dist --version 159.0 --patch-dir patches \
           --out release-notes.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from scripts import version as ver
from scripts.release import naming, notes


def read_apk_info(text: str) -> dict[str, dict[str, str]]:
    """Per-APK facts from apk-info.txt: versionCode, versionName and the signer digest."""
    entries: dict[str, dict[str, str]] = {}
    current: Optional[dict[str, str]] = None
    for line in text.splitlines():
        m = re.match(r"^=== (\S+\.apk) ", line)
        if m:
            current = entries.setdefault(m.group(1), {})
            continue
        if current is None:
            continue
        key, sep, value = line.partition(": ")
        if sep and key in ("versionCode", "versionName", "signer-sha256-hex"):
            current[key] = value.strip()
    return entries


def check_release_artifacts(
    *,
    dist_files: list[str],
    embermine_version: str,
    build_info: dict[str, object],
    apk_info: dict[str, dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    expected = naming.apk_names(embermine_version)
    apks = sorted(name for name in dist_files if name.endswith(".apk"))
    if apks != sorted(expected):
        errors.append(f"APK files are {apks}, expected {sorted(expected)}")

    if build_info.get("signing") != "owner":
        errors.append(f"build-info signing is {build_info.get('signing')!r}; a release needs the owner key")
    if build_info.get("embermine_version") != embermine_version:
        errors.append(
            f"build-info embermine_version is {build_info.get('embermine_version')!r}, expected {embermine_version!r}"
        )
    firefox, _, _ = ver.parse_embermine_version(embermine_version)
    if build_info.get("version") != firefox:
        errors.append(f"build-info version is {build_info.get('version')!r}, expected Firefox {firefox!r}")
    if not build_info.get("patches"):
        errors.append("build-info lists no applied patches")

    signers: set[str] = set()
    for abi in naming.ABIS:
        name = naming.apk_name(embermine_version, abi)
        facts = apk_info.get(name)
        if facts is None:
            errors.append(f"apk-info.txt has no entry for {name}")
            continue
        if facts.get("versionName") != embermine_version:
            errors.append(f"{name} versionName is {facts.get('versionName')!r}, expected {embermine_version!r}")
        want_code = str(ver.version_code(embermine_version, abi))
        if facts.get("versionCode") != want_code:
            errors.append(f"{name} versionCode is {facts.get('versionCode')!r}, expected {want_code}")
        digest = facts.get("signer-sha256-hex", "")
        if not digest:
            errors.append(f"{name} has no signer digest")
        signers.add(digest)
    if len(signers) > 1:
        errors.append(f"the APKs have different signers: {sorted(signers)}")
    return errors


def http_status(url: str) -> int:
    """Final HTTP status after redirects; 0 when the host cannot be reached."""
    last = 0
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as response:
                return response.status
        except urllib.error.HTTPError as e:
            last = e.code
            if e.code < 500:
                return e.code
        except urllib.error.URLError:
            last = 0
        time.sleep(5 * attempt)
    return last


def check_notes_url(url: str, status: Callable[[str], int]) -> list[str]:
    code = status(url)
    if code == 200:
        return []
    return [f"Mozilla release notes {url} answered HTTP {code}, expected 200"]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", type=Path, required=True, help="directory with the build artifacts")
    parser.add_argument("--version", required=True, help="Embermine release version, e.g. 159.0 or 159.0-r2")
    parser.add_argument("--patch-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="release notes file to write")
    args = parser.parse_args(argv)

    try:
        build_info = json.loads((args.dist / "build-info.json").read_text(encoding="utf-8"))
        apk_info = read_apk_info((args.dist / "apk-info.txt").read_text(encoding="utf-8"))
        dist_files = [p.name for p in args.dist.iterdir() if p.is_file()]
        errors = check_release_artifacts(
            dist_files=dist_files,
            embermine_version=args.version,
            build_info=build_info,
            apk_info=apk_info,
        )
        firefox, _, _ = ver.parse_embermine_version(args.version)
        url = notes.mozilla_release_notes_url(firefox)
        errors += check_notes_url(url, http_status)
        if errors:
            for e in errors:
                print(f"error: {e}", file=sys.stderr)
            return 1
        text = notes.render_notes(
            firefox_version=firefox,
            embermine_version=args.version,
            tag=build_info["tag"],
            sha=build_info["sha"],
            buildid=build_info["buildid"],
            rebuild=notes.rebuild_number(args.version),
            changes=notes.read_changes(args.patch_dir),
        )
    except (ver.VersionError, notes.NotesError, KeyError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"artifacts OK for {args.version}; release notes written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
