"""Read-only checks that the owner-repo .gitignore covers every local-only path.

The tests never write to the repository: they only run `git check-ignore` and
`git ls-files`, one path per subprocess, so a multi-path match cannot hide a miss.
"""
from __future__ import annotations

import os
import re
import subprocess
import unittest

from scripts.tests.helpers import REPO_ROOT

BUILD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build.yml"

# build.yml writes this file into the Firefox tree; the name is what .gitignore must match.
SAFE_BROWSING_KEY_NAME = ".safe_browsing_api_key"

LOCAL_ONLY_PATHS = (
    "EMBERMINE.md",
    "docs/reference/04-homepage.png",
    "docs/readme-notes.md",
    "docs/spinners.md",
    "assets/icon/original/embermine-export.svg",
    "assets/icon/preview.png",
    "assets/wallpapers/original/x.svg",
    "AGENTS.md",
    ".factory/x",
    "build/x",
    "x.apk",
    "x.aab",
    "x.keystore",
    "x.jks",
    "x.p12",
    "x.pfx",
    "mobile/android/fenix/" + SAFE_BROWSING_KEY_NAME,
    SAFE_BROWSING_KEY_NAME,
)


def git_env() -> dict[str, str]:
    """Environment that ignores the developer's global and system git config."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        env=git_env(),
        check=False,
    )


def extract_safe_browsing_write_target() -> str:
    """Return the path build.yml writes the Safe Browsing key to."""
    body = BUILD_WORKFLOW.read_text(encoding="utf-8")
    matches = re.findall(r">\s*([^\s)'\"]*" + re.escape(SAFE_BROWSING_KEY_NAME) + r")", body)
    if len(matches) != 1:
        raise AssertionError(f"expected one Safe Browsing key write in build.yml, found {matches!r}")
    return matches[0]


class RepoHygieneTests(unittest.TestCase):
    def test_build_writes_safe_browsing_key_under_firefox_tree(self) -> None:
        target = extract_safe_browsing_write_target()
        self.assertEqual(target, "fx/mobile/android/fenix/" + SAFE_BROWSING_KEY_NAME)

    def test_local_only_paths_are_ignored_by_gitignore(self) -> None:
        paths = (*LOCAL_ONLY_PATHS, extract_safe_browsing_write_target())
        for path in paths:
            with self.subTest(path=path):
                proc = git("check-ignore", "-v", "--", path)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(
                    proc.stdout.startswith(".gitignore:"),
                    f"{path} is not ignored by .gitignore: {proc.stdout!r}",
                )

    def test_no_tracked_file_matches_an_ignore_rule(self) -> None:
        proc = git("ls-files", "-ci", "--exclude-standard")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "", f"tracked files match ignore rules:\n{proc.stdout}")


if __name__ == "__main__":
    unittest.main()
