"""Names of a GitHub Release and its APK assets.

A release version is the Firefox version, plus -rN for a rebuild: 159.0 or 159.0-r2. The tag is v<version>
and each APK is embermine-<version>-<abi>.apk, so the names of a rebuild stay distinct from the base release.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from scripts import version as ver

ABIS = ("arm64-v8a", "x86_64")


def _release_version(embermine_version: str) -> str:
    """Accepts a release or rebuild version; dev versions are never published."""
    _, kind, _ = ver.parse_embermine_version(embermine_version)
    if kind not in ("release", "rebuild"):
        raise ver.VersionError(f"{embermine_version!r} is not a release version (dev builds are never published)")
    return embermine_version


def release_tag(embermine_version: str) -> str:
    return f"v{_release_version(embermine_version)}"


def release_title(embermine_version: str) -> str:
    return f"Embermine {_release_version(embermine_version)}"


def apk_name(embermine_version: str, abi: str) -> str:
    version = _release_version(embermine_version)
    if abi not in ABIS:
        raise ver.VersionError(f"unsupported ABI {abi!r}: expected one of {list(ABIS)}")
    return f"embermine-{version}-{abi}.apk"


def apk_names(embermine_version: str) -> list[str]:
    return [apk_name(embermine_version, abi) for abi in ABIS]


def main(argv: Optional[list[str]] = None) -> int:
    """CLI for the shell scripts: naming.py tag|title|apks VERSION (prints the result, exits 1 on error)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["tag", "title", "apks"])
    parser.add_argument("version")
    args = parser.parse_args(argv)
    try:
        if args.command == "tag":
            print(release_tag(args.version))
        elif args.command == "title":
            print(release_title(args.version))
        else:
            print("\n".join(apk_names(args.version)))
    except ver.VersionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
