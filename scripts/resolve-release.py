#!/usr/bin/env python3
"""Resolve a Firefox version to its release tag, commit and GeckoView buildid.

Prints JSON on stdout; with --github-output also appends key=value lines to $GITHUB_OUTPUT.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Protocol

FIREFOX_REPO = "https://github.com/mozilla-firefox/firefox"
TASKCLUSTER = "https://firefox-ci-tc.services.mozilla.com/api"
TASKCLUSTER_INDEX = (
    TASKCLUSTER + "/index/v1/task/gecko.v2.mozilla-release.shippable.revision.{sha}"
    ".mobile.android-geckoview-fat-aar-opt"
)
TASKCLUSTER_TASK = TASKCLUSTER + "/queue/v1/task/{task_id}"
TASKCLUSTER_BUILDHUB = TASKCLUSTER + "/queue/v1/task/{task_id}/artifacts/public/build/buildhub.json"
MAVEN_GECKOVIEW = "https://maven.mozilla.org/maven2/org/mozilla/geckoview/geckoview-omni"

_VERSION_RE = re.compile(r"^\d{1,3}\.\d{1,2}(\.\d{1,2})?$")
_BUILDID_RE = re.compile(r"^\d{14}$")
_REPO_ROOT = Path(__file__).resolve().parents[1]


class ResolveError(RuntimeError):
    pass


class Http(Protocol):
    def get_json(self, url: str) -> dict: ...

    def head_ok(self, url: str) -> bool: ...


class UrllibHttp:
    def get_json(self, url: str) -> dict:
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            raise ResolveError(f"request failed for {url}: {e}") from e

    def head_ok(self, url: str) -> bool:
        req = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status == 200
        except urllib.error.HTTPError:
            return False
        except (urllib.error.URLError, TimeoutError) as e:
            raise ResolveError(f"request failed for {url}: {e}") from e


def tag_candidates(version: str) -> list[str]:
    """Android-only dot releases exist only as FIREFOX-ANDROID_ tags, so those go first."""
    suffix = version.replace(".", "_")
    return [f"FIREFOX-ANDROID_{suffix}_RELEASE", f"FIREFOX_{suffix}_RELEASE"]


def parse_ls_remote(output: str, tag: str) -> Optional[str]:
    """Returns the commit sha; the peeled entry wins for annotated tags."""
    plain = peeled = None
    for line in output.splitlines():
        sha, _, ref = line.partition("\t")
        if ref == f"refs/tags/{tag}":
            plain = sha
        elif ref == f"refs/tags/{tag}^{{}}":
            peeled = sha
    return peeled or plain


def git_ls_remote(tag: str, repo: str = FIREFOX_REPO) -> Optional[str]:
    proc = subprocess.run(
        ["git", "ls-remote", repo, f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ResolveError(f"git ls-remote failed for {tag}: {proc.stderr.strip()}")
    return parse_ls_remote(proc.stdout, tag)


def find_tag(version: str, ls_remote: Callable[[str], Optional[str]]) -> tuple[str, str]:
    for tag in tag_candidates(version):
        sha = ls_remote(tag)
        print(f"tag {tag}: {sha or 'not found'}", file=sys.stderr)
        if sha:
            return tag, sha
    raise ResolveError(f"no release tag found for Firefox {version} (tried {tag_candidates(version)})")


def is_buildid(value: object) -> bool:
    return isinstance(value, str) and bool(_BUILDID_RE.match(value))


def geckoview_buildid(sha: str, http: Http, cross_check: bool = False) -> str:
    """MOZ_BUILD_DATE of the shippable GeckoView task is the buildid in the Maven version.

    buildhub.json from the same task is the fallback (and, with cross_check, a consistency check).
    """
    task_id = http.get_json(TASKCLUSTER_INDEX.format(sha=sha)).get("taskId")
    if not task_id:
        raise ResolveError(f"Taskcluster index has no taskId for {sha}")

    task = http.get_json(TASKCLUSTER_TASK.format(task_id=task_id))
    from_task = (task.get("payload", {}).get("env", {}) or {}).get("MOZ_BUILD_DATE")
    if not is_buildid(from_task):
        from_task = None

    def from_buildhub() -> Optional[str]:
        try:
            value = http.get_json(TASKCLUSTER_BUILDHUB.format(task_id=task_id)).get("build", {}).get("id")
        except ResolveError:
            return None
        return value if is_buildid(value) else None

    if from_task is None:
        fallback = from_buildhub()
        if fallback is None:
            raise ResolveError(f"no GeckoView buildid in task {task_id} (MOZ_BUILD_DATE or buildhub.json)")
        return fallback
    if cross_check:
        other = from_buildhub()
        if other is not None and other != from_task:
            raise ResolveError(f"buildid mismatch: MOZ_BUILD_DATE={from_task} buildhub={other}")
    return from_task


def maven_pom_url(version: str, buildid: str) -> str:
    gv = f"{version}.{buildid}"
    return f"{MAVEN_GECKOVIEW}/{gv}/geckoview-omni-{gv}.pom"


def check_maven(version: str, buildid: str, http: Http) -> str:
    url = maven_pom_url(version, buildid)
    if not http.head_ok(url):
        raise ResolveError(f"Maven artifact not found: {url}")
    return url


def resolve(
    version: str,
    ls_remote: Callable[[str], Optional[str]],
    http: Http,
    cross_check: bool = False,
) -> dict[str, str]:
    if not _VERSION_RE.match(version):
        raise ResolveError(f"unsupported Firefox version {version!r}")
    tag, sha = find_tag(version, ls_remote)
    buildid = geckoview_buildid(sha, http, cross_check)
    check_maven(version, buildid, http)
    return {
        "version": version,
        "tag": tag,
        "sha": sha,
        "buildid": buildid,
        "geckoview_version": f"{version}.{buildid}",
    }


def read_version_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def write_github_output(result: dict[str, str], path: Optional[str]) -> None:
    path = path or os.environ.get("GITHUB_OUTPUT")
    if not path:
        raise ResolveError("GITHUB_OUTPUT is not set")
    with open(path, "a", encoding="utf-8") as f:
        f.writelines(f"{k}={v}\n" for k, v in result.items())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", help="Firefox version (default: firefox-version.txt)")
    parser.add_argument("--github-output", action="store_true", help="append to $GITHUB_OUTPUT")
    parser.add_argument(
        "--cross-check", action="store_true", help="fail if buildhub.json disagrees with MOZ_BUILD_DATE"
    )
    args = parser.parse_args(argv)
    try:
        version = args.version or read_version_file(_REPO_ROOT / "firefox-version.txt")
        result = resolve(version, git_ls_remote, UrllibHttp(), args.cross_check)
        print(json.dumps(result, indent=2))
        if args.github_output:
            write_github_output(result, None)
    except (ResolveError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
