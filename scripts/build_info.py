#!/usr/bin/env python3
"""Write build-info.json: the inputs and the applied patches of a build."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SUBJECT_RE = re.compile(r"^Subject: \[PATCH\] (.*)$", re.MULTILINE)


class BuildInfoError(RuntimeError):
    pass


def list_patch_files(patch_dir: Path) -> list[str]:
    return sorted(p.name for p in patch_dir.glob("*.patch"))


def patch_subject(path: Path) -> str:
    m = _SUBJECT_RE.search(path.read_text(encoding="utf-8"))
    if not m:
        raise BuildInfoError(f"{path.name} has no Subject header")
    return m.group(1).strip()


def read_applied(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_info(
    *,
    firefox_version: str,
    embermine_version: str,
    version_code_base: str,
    tag: str,
    sha: str,
    buildid: str,
    signing: str,
    applied: list[str],
    patch_dir: Path,
    embermine_commit: str = "",
    run_number: str = "",
) -> dict[str, object]:
    available = list_patch_files(patch_dir)
    if applied != available:
        raise BuildInfoError(
            f"applied patches {applied} differ from patches in {patch_dir} {available}"
        )
    return {
        "version": firefox_version,
        "embermine_version": embermine_version,
        "version_code_base": version_code_base,
        "tag": tag,
        "sha": sha,
        "buildid": buildid,
        "geckoview_version": f"{firefox_version}.{buildid}",
        "signing": signing,
        "embermine_commit": embermine_commit,
        "run_number": run_number,
        "patches": applied,
        "patch_subjects": [patch_subject(patch_dir / name) for name in applied],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firefox-version", required=True)
    parser.add_argument("--embermine-version", required=True)
    parser.add_argument("--version-code-base", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--buildid", required=True)
    parser.add_argument("--signing", required=True, choices=["owner", "throwaway"])
    parser.add_argument("--applied", required=True, type=Path, help="file written by apply-patches.sh --list")
    parser.add_argument("--patch-dir", type=Path, default=_REPO_ROOT / "patches")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        info = build_info(
            firefox_version=args.firefox_version,
            embermine_version=args.embermine_version,
            version_code_base=args.version_code_base,
            tag=args.tag,
            sha=args.sha,
            buildid=args.buildid,
            signing=args.signing,
            applied=read_applied(args.applied),
            patch_dir=args.patch_dir,
            embermine_commit=os.environ.get("GITHUB_SHA", ""),
            run_number=os.environ.get("GITHUB_RUN_NUMBER", ""),
        )
    except (BuildInfoError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    args.out.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
