#!/usr/bin/env python3
"""Embermine version name and versionCode scheme.

versionCode = MMM mm pp R A
  MMM/mm/pp  Firefox major (3 digits), minor (2), patch (2)
  R          rebuild digit: dev 0, release 1, -rN N (2..9)
  A          ABI digit: arm64-v8a 1, x86_64 2

Gradle receives the code without the ABI digit (-PembermineVersionCode) and appends
the digit per split, so both APKs stay ordered and no ABI sorts below another build.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional

ABI_DIGITS = {"arm64-v8a": 1, "x86_64": 2}
MIN_REBUILD = 2
MAX_REBUILD = 9

_FIREFOX_RE = re.compile(r"^(\d{1,3})\.(\d{1,2})(?:\.(\d{1,2}))?$")
_SUFFIX_RE = re.compile(r"^(?P<fx>[^-]+)(?:-(?P<suffix>.*))?$")


class VersionError(ValueError):
    pass


def parse_firefox_version(text: str) -> tuple[int, int, int]:
    m = _FIREFOX_RE.match(text)
    if not m:
        raise VersionError(
            f"unsupported Firefox version {text!r}: expected MAJOR.MINOR[.PATCH] "
            "(major <= 999, minor/patch <= 99)"
        )
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def _check_rebuild(n: int) -> int:
    if not MIN_REBUILD <= n <= MAX_REBUILD:
        raise VersionError(
            f"rebuild number r{n} is out of range: only -r{MIN_REBUILD}..-r{MAX_REBUILD} "
            "fit the versionCode rebuild digit"
        )
    return n


def embermine_version(
    firefox_version: str, rebuild: Optional[int] = None, dev_run: Optional[int] = None
) -> str:
    parse_firefox_version(firefox_version)
    if rebuild is not None and dev_run is not None:
        raise VersionError("a build is either a rebuild or a dev build, not both")
    if rebuild is not None:
        return f"{firefox_version}-r{_check_rebuild(rebuild)}"
    if dev_run is not None:
        if dev_run < 0:
            raise VersionError("dev run number must not be negative")
        return f"{firefox_version}-dev.{dev_run}"
    return firefox_version


def parse_embermine_version(text: str) -> tuple[str, str, Optional[int]]:
    """Returns (firefox_version, kind, number); kind is release, rebuild or dev."""
    m = _SUFFIX_RE.match(text)
    if not m:
        raise VersionError(f"unsupported version {text!r}")
    fx, suffix = m.group("fx"), m.group("suffix")
    parse_firefox_version(fx)
    if suffix is None:
        return fx, "release", None
    rebuild = re.fullmatch(r"r(\d+)", suffix)
    if rebuild:
        return fx, "rebuild", _check_rebuild(int(rebuild.group(1)))
    dev = re.fullmatch(r"dev\.(\d+)", suffix)
    if dev:
        return fx, "dev", int(dev.group(1))
    raise VersionError(f"unsupported version suffix -{suffix} in {text!r}")


def _rebuild_digit(kind: str, number: Optional[int]) -> int:
    if kind == "dev":
        return 0
    if kind == "release":
        return 1
    assert number is not None
    return number


def version_code_base(version: str) -> int:
    fx, kind, number = parse_embermine_version(version)
    major, minor, patch = parse_firefox_version(fx)
    return (major * 100 + minor) * 100 * 10 + patch * 10 + _rebuild_digit(kind, number)


def version_code(version: str, abi: str) -> int:
    if abi not in ABI_DIGITS:
        raise VersionError(f"unsupported ABI {abi!r}: expected one of {sorted(ABI_DIGITS)}")
    return version_code_base(version) * 10 + ABI_DIGITS[abi]


def build_info(
    firefox_version: str, rebuild: Optional[int] = None, dev_run: Optional[int] = None
) -> dict[str, str]:
    version = embermine_version(firefox_version, rebuild, dev_run)
    info = {
        "version": version,
        "firefox_version": firefox_version,
        "version_code_base": str(version_code_base(version)),
    }
    for abi in ABI_DIGITS:
        info[f"version_code_{abi.replace('-', '_')}"] = str(version_code(version, abi))
    return info


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--firefox", required=True, help="Firefox version, e.g. 159.0.2")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--rebuild", type=int, help="rebuild number (2..9)")
    group.add_argument("--dev-run", type=int, help="CI run number for a dev build")
    parser.add_argument("--github-output", action="store_true", help="append to $GITHUB_OUTPUT")
    args = parser.parse_args(argv)
    try:
        info = build_info(args.firefox, args.rebuild, args.dev_run)
    except VersionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(info, indent=2))
    if args.github_output:
        path = os.environ.get("GITHUB_OUTPUT")
        if not path:
            print("error: GITHUB_OUTPUT is not set", file=sys.stderr)
            return 1
        with open(path, "a", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in info.items())
    return 0


if __name__ == "__main__":
    sys.exit(main())
