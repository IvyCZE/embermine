"""Shared fixtures for script tests: throwaway git repos and stub Android tools."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"

_GIT = ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false"]


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run([*_GIT, *args], cwd=cwd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def clean_env(**extra: str) -> dict[str, str]:
    """Environment without the developer's git identity or any CI variables."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITHUB_", "RUNNER_", "KEY"))}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env.update(extra)
    return env


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()

    def run_script(self, script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged = clean_env(HOME=str(self.home), TMPDIR=str(self.tmp))
        merged.update(env or {})
        return subprocess.run(
            ["bash", str(SCRIPTS / script), *args], capture_output=True, text=True, env=merged, check=False
        )


STUB_ZIPALIGN = """#!/usr/bin/env bash
echo "zipalign $*" >>"$STUB_LOG"
cp "${@: -2:1}" "${@: -1}"
"""

STUB_KEYTOOL = """#!/usr/bin/env bash
echo "keytool $*" >>"$STUB_LOG"
while [ $# -gt 0 ]; do
  [ "$1" = "-keystore" ] && : >"$2"
  shift
done
"""

STUB_APKSIGNER = """#!/usr/bin/env bash
echo "apksigner $*" >>"$STUB_LOG"
case "$1" in
  sign)
    ks=""; out=""; in=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --ks) ks="$2"; shift 2 ;;
        --out) out="$2"; shift 2 ;;
        --*) shift ;;
        *) in="$1"; shift ;;
      esac
    done
    [ -f "$ks" ] || { echo "stub apksigner: no keystore" >&2; exit 1; }
    echo "keystore-dir $(dirname "$ks")" >>"$STUB_LOG"
    cp "$in" "$out"
    ;;
  verify)
    echo "Verifies"
    echo "Verified using v2 scheme (APK Signature Scheme v2): true"
    echo "Signer #1 certificate DN: CN=Embermine"
    echo "Signer #1 certificate SHA-256 digest: ${STUB_DIGEST:-f76f699374d50bb5cf6ac6754ec59faa3eb17774adffbec973b9ddd264bdc2a0}"
    ;;
esac
"""

STUB_AAPT2 = """#!/usr/bin/env bash
if [ "$2" = badging ]; then
  cat "$STUB_BADGING"
elif [ "$2" = xmltree ]; then
  cat "$STUB_MANIFEST"
fi
"""


def make_stub_tools(directory: Path) -> Path:
    """Fake zipalign, keytool, apksigner and aapt2 that log to $STUB_LOG."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in {
        "zipalign": STUB_ZIPALIGN,
        "keytool": STUB_KEYTOOL,
        "apksigner": STUB_APKSIGNER,
        "aapt2": STUB_AAPT2,
    }.items():
        path = directory / name
        path.write_text(body)
        path.chmod(0o755)
    return directory
