#!/usr/bin/env python3
"""Detect the newest Firefox for Android release and decide what the release run does.

The upstream version is the larger of product-details `version` (mobile_versions.json) and the highest
stable FIREFOX-ANDROID_<v>_RELEASE or FIREFOX_<v>_RELEASE tag, so an Android-only dot release counts even
when product-details lags. It is compared with the newest Embermine GitHub Release (base Firefox version;
rebuild suffixes do not make a version new).

A scheduled run while the EMBERMINE_PUBLISH variable is not exactly 'true' only detects and logs. A manual
run builds as a dry run unless dry_run is false and the gate is open. Only an open gate publishes.
  usage (CI): python3 -m scripts.release.detect --event NAME --gate-open true|false --requested V
              --rebuild true|false --dry-run true|false --repo OWNER/REPO [--github-output]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, TypeVar

from scripts import version as ver

PRODUCT_DETAILS_URL = "https://product-details.mozilla.org/1.0/mobile_versions.json"
FIREFOX_REPO = "https://github.com/mozilla-firefox/firefox"

_ANDROID_TAG_RE = re.compile(r"^FIREFOX-ANDROID_(\d+)_(\d+)(?:_(\d+))?_RELEASE$")
_DESKTOP_TAG_RE = re.compile(r"^FIREFOX_(\d+)_(\d+)(?:_(\d+))?_RELEASE$")
_EMBERMINE_TAG_RE = re.compile(r"^v(\d+\.\d+(?:\.\d+)?)(?:-r(\d+))?$")

T = TypeVar("T")


class DetectError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    """A GitHub Release tag v<firefox>[-rN]; number is 1 for the base release."""

    tag: str
    firefox: str
    number: int


@dataclass(frozen=True)
class Choice:
    firefox: str
    rebuild: Optional[int]
    build: bool
    reason: str

    @property
    def embermine_version(self) -> str:
        return ver.embermine_version(self.firefox, rebuild=self.rebuild)

    @property
    def tag(self) -> str:
        return f"v{self.embermine_version}"


@dataclass(frozen=True)
class Outcome:
    build: bool
    publish: bool
    reason: str


def version_key(text: str) -> tuple[int, int, int]:
    return ver.parse_firefox_version(text)


def tag_to_version(tag: str) -> Optional[str]:
    """Stable release tags only: betas, BUILD tags, ESR and RC tags return None."""
    for pattern in (_ANDROID_TAG_RE, _DESKTOP_TAG_RE):
        m = pattern.match(tag)
        if m:
            parts = [int(p) for p in m.groups() if p is not None]
            return ".".join(str(p) for p in parts)
    return None


def parse_ls_remote_tags(output: str) -> list[str]:
    names: set[str] = set()
    for line in output.splitlines():
        _, _, ref = line.partition("\t")
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/") :]
        if name.endswith("^{}"):
            name = name[:-3]
        names.add(name)
    return sorted(names)


def highest_tag_version(tags: Iterable[str]) -> Optional[str]:
    versions = [v for v in (tag_to_version(t) for t in tags) if v is not None]
    return max(versions, key=version_key, default=None)


def upstream_version(product_details_version: str, tags: Iterable[str]) -> str:
    ver.parse_firefox_version(product_details_version)
    from_tags = highest_tag_version(tags)
    if from_tags is None or version_key(from_tags) <= version_key(product_details_version):
        return product_details_version
    return from_tags


def parse_release_tags(names: Iterable[str]) -> list[Release]:
    releases = []
    for name in names:
        m = _EMBERMINE_TAG_RE.match(name)
        if m:
            releases.append(Release(tag=name, firefox=m.group(1), number=int(m.group(2) or 1)))
    return releases


def choose(
    *, upstream: str, releases: list[Release], requested: Optional[str], rebuild: bool
) -> Choice:
    """Pick the Firefox version and the -rN number of this run, and whether it builds at all."""
    if requested:
        ver.parse_firefox_version(requested)
        target = requested
    else:
        target = upstream
    existing = sorted(r.number for r in releases if version_key(r.firefox) == version_key(target))

    if rebuild:
        if not existing:
            return Choice(target, None, True, f"rebuild requested but Firefox {target} has no release yet: plain release")
        next_number = max(existing) + 1
        if next_number > ver.MAX_REBUILD:
            raise DetectError(
                f"a rebuild of Firefox {target} would be -r{next_number}, which is out of range: "
                f"only -r{ver.MIN_REBUILD}..-r{ver.MAX_REBUILD} fit the versionCode digit"
            )
        return Choice(target, next_number, True, f"rebuild -r{next_number} of Firefox {target}")

    if requested:
        if existing:
            return Choice(
                target, None, False,
                f"requested Firefox {target} already has release v{target}; request a rebuild to publish -rN",
            )
        return Choice(target, None, True, f"requested Firefox {target} has no release yet")

    if not releases:
        return Choice(target, None, True, f"no Embermine GitHub Release yet: Firefox {target} is new")
    latest = max(releases, key=lambda r: (version_key(r.firefox), r.number))
    if version_key(upstream) > version_key(latest.firefox):
        return Choice(upstream, None, True, f"Firefox {upstream} is newer than the latest release {latest.tag}")
    return Choice(upstream, None, False, f"nothing new: the latest release {latest.tag} already covers Firefox {upstream}")


def is_gate_open(value: str) -> bool:
    return value == "true"


def is_dry_run(value: str) -> bool:
    """dry_run defaults to true; only an explicit 'false' turns it off."""
    return value.strip().lower() != "false"


def apply_gate(choice: Choice, *, event: str, gate_open: bool, dry_run_input: str) -> Outcome:
    if not choice.build:
        return Outcome(False, False, choice.reason)
    if event != "workflow_dispatch":
        if not gate_open:
            return Outcome(
                False, False,
                f"{choice.reason}; publishing is gated (EMBERMINE_PUBLISH is not 'true'): "
                "detection only, build skipped",
            )
        return Outcome(True, True, choice.reason)
    if not gate_open:
        return Outcome(True, False, f"{choice.reason}; publishing is gated (EMBERMINE_PUBLISH is not 'true'): dry run")
    if is_dry_run(dry_run_input):
        return Outcome(True, False, f"{choice.reason}; dry run: artifacts and notes only")
    return Outcome(True, True, choice.reason)


def retry(fn: Callable[[], T], what: str, attempts: int = 3, backoff: float = 20.0) -> T:
    last: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except (OSError, DetectError, subprocess.SubprocessError) as e:
            last = e
            print(f"{what}: attempt {attempt}/{attempts} failed: {e}", file=sys.stderr)
            if attempt < attempts:
                time.sleep(backoff * attempt)
    raise DetectError(f"{what} failed after {attempts} attempts: {last}")


def fetch_product_details() -> str:
    def get() -> str:
        with urllib.request.urlopen(PRODUCT_DETAILS_URL, timeout=60) as response:
            payload = json.load(response)
        version = payload.get("version", "")
        if not isinstance(version, str):
            raise DetectError("product-details has no string 'version'")
        return version

    return retry(get, "product-details")


def fetch_firefox_tags() -> list[str]:
    def ls_remote() -> list[str]:
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", FIREFOX_REPO], capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            raise DetectError(f"git ls-remote failed: {proc.stderr.strip()}")
        return parse_ls_remote_tags(proc.stdout)

    return retry(ls_remote, "Firefox tags")


def fetch_release_tags(repo: str) -> list[str]:
    def gh_list() -> list[str]:
        proc = subprocess.run(
            ["gh", "release", "list", "--repo", repo, "--limit", "1000", "--json", "tagName"],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            raise DetectError(f"gh release list failed: {proc.stderr.strip()}")
        return [item["tagName"] for item in json.loads(proc.stdout)]

    return retry(gh_list, "GitHub releases")


def write_outputs(values: dict[str, str], path: Optional[str]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.writelines(f"{k}={v}\n" for k, v in values.items())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--event", required=True, help="GitHub event name: schedule or workflow_dispatch")
    parser.add_argument("--gate-open", default="", help="value of vars.EMBERMINE_PUBLISH")
    parser.add_argument("--requested", default="", help="Firefox version input (empty = detect)")
    parser.add_argument("--rebuild", default="false", help="true to build the next -rN of the version")
    parser.add_argument("--dry-run", default="", help="dry_run input (only read for workflow_dispatch)")
    parser.add_argument("--repo", required=True, help="OWNER/REPO whose GitHub Releases are checked")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)

    try:
        product_details = fetch_product_details()
        tags = fetch_firefox_tags()
        upstream = upstream_version(product_details, tags)
        releases = parse_release_tags(fetch_release_tags(args.repo))
        choice = choose(
            upstream=upstream,
            releases=releases,
            requested=args.requested.strip() or None,
            rebuild=args.rebuild.strip().lower() == "true",
        )
        outcome = apply_gate(
            choice,
            event=args.event,
            gate_open=is_gate_open(args.gate_open),
            dry_run_input=args.dry_run,
        )
    except (DetectError, ver.VersionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    latest = max(releases, key=lambda r: (version_key(r.firefox), r.number), default=None)
    lines = [
        f"product-details version: {product_details}",
        f"highest Firefox release tag: {highest_tag_version(tags) or 'none'}",
        f"upstream Firefox for Android version: {upstream}",
        f"latest Embermine GitHub Release: {latest.tag if latest else 'none'}",
        f"requested version: {args.requested or 'none (detected)'}; rebuild requested: {args.rebuild}",
        f"decision: build={str(outcome.build).lower()} publish={str(outcome.publish).lower()}",
        f"reason: {outcome.reason}",
    ]
    print("\n".join(lines))

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("## Release detection\n\n" + "\n".join(f"- {line}" for line in lines) + "\n")

    values = {
        "build": str(outcome.build).lower(),
        "publish": str(outcome.publish).lower(),
        "fx_version": choice.firefox,
        "rebuild": str(choice.rebuild or ""),
        "version": choice.embermine_version,
        "tag": choice.tag,
        "upstream": upstream,
        "latest_release": latest.tag if latest else "",
        "reason": outcome.reason,
    }
    if args.github_output:
        path = os.environ.get("GITHUB_OUTPUT")
        if not path:
            print("error: GITHUB_OUTPUT is not set", file=sys.stderr)
            return 1
        write_outputs(values, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
