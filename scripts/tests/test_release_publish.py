import stat
import subprocess
import unittest

from scripts.tests.helpers import SCRIPTS, REPO_ROOT, TempDirTestCase, clean_env, git

STUB_GH = """#!/usr/bin/env bash
echo "gh $*" >>"$STUB_LOG"
if [ "$1 $2" = "release view" ]; then
  [ "${RELEASE_EXISTS:-0}" = 1 ] && exit 0
  exit 1
fi
exit 0
"""

SHA = "9a2dc53c369c7ae5172018b35988e1d2ffeff402"


class PublishTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(STUB_GH, encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        self.log = self.tmp / "gh.log"
        self.log.write_text("", encoding="utf-8")
        self.dist = self.tmp / "dist"
        self.dist.mkdir()
        self.notes = self.tmp / "release-notes.md"
        self.notes.write_text("# Embermine\n", encoding="utf-8")
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True, env=clean_env(HOME=str(self.home)))

    def add_apks(self, version: str) -> None:
        for abi in ("arm64-v8a", "x86_64"):
            (self.dist / f"embermine-{version}-{abi}.apk").write_text(abi, encoding="utf-8")

    def publish(self, *, version: str = "159.0", tag: str = "v159.0", **env: str) -> subprocess.CompletedProcess[str]:
        merged = clean_env(
            HOME=str(self.home),
            PATH=f"{self.bin}:/usr/bin:/bin",
            STUB_LOG=str(self.log),
            REPO="IvyCZE/embermine",
            VERSION=version,
            TAG=tag,
            SHA=SHA,
            DIST=str(self.dist),
            NOTES=str(self.notes),
            REMOTE=str(self.remote),
        )
        merged.update(env)
        return subprocess.run(
            ["bash", str(SCRIPTS / "release" / "publish.sh")],
            capture_output=True,
            text=True,
            env=merged,
            check=False,
            cwd=REPO_ROOT,
        )

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def test_creates_the_release_with_its_apks_and_notes(self) -> None:
        self.add_apks("159.0")
        proc = self.publish()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        create = [c for c in self.calls() if c.startswith("gh release create")]
        self.assertEqual(len(create), 1, self.calls())
        self.assertIn("v159.0", create[0])
        self.assertIn(f"--target {SHA}", create[0])
        self.assertIn("--title Embermine 159.0", create[0])
        self.assertIn(f"--notes-file {self.notes}", create[0])
        self.assertIn("embermine-159.0-arm64-v8a.apk", create[0])
        self.assertIn("embermine-159.0-x86_64.apk", create[0])

    def test_rebuild_release_uses_the_rebuild_tag_and_names(self) -> None:
        self.add_apks("159.0-r2")
        proc = self.publish(version="159.0-r2", tag="v159.0-r2")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        create = [c for c in self.calls() if c.startswith("gh release create")][0]
        self.assertIn("v159.0-r2", create)
        self.assertIn("--title Embermine 159.0-r2", create)
        self.assertIn("embermine-159.0-r2-arm64-v8a.apk", create)

    def test_an_existing_release_is_never_overwritten(self) -> None:
        self.add_apks("159.0")
        proc = self.publish(RELEASE_EXISTS="1")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("already exists", proc.stderr)
        self.assertFalse(any(c.startswith("gh release create") for c in self.calls()))

    def test_an_existing_tag_is_never_overwritten(self) -> None:
        self.add_apks("159.0")
        work = self.tmp / "work"
        work.mkdir()
        git(work, "init", "-q")
        git(work, "commit", "-q", "--allow-empty", "-m", "x")
        git(work, "tag", "v159.0")
        git(work, "push", "-q", str(self.remote), "v159.0")
        proc = self.publish()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("already exists on", proc.stderr)
        self.assertFalse(any(c.startswith("gh release create") for c in self.calls()))

    def test_a_tag_that_does_not_match_the_version_is_refused(self) -> None:
        self.add_apks("159.0")
        proc = self.publish(tag="v160.0")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("does not match", proc.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_dev_version_is_never_published(self) -> None:
        proc = self.publish(version="159.0-dev.4", tag="v159.0-dev.4")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_a_missing_apk_stops_before_anything_is_created(self) -> None:
        (self.dist / "embermine-159.0-arm64-v8a.apk").write_text("arm", encoding="utf-8")
        proc = self.publish()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("embermine-159.0-x86_64.apk", proc.stderr)
        self.assertFalse(any(c.startswith("gh release create") for c in self.calls()))

    def test_missing_notes_stop_the_publish(self) -> None:
        self.add_apks("159.0")
        self.notes.unlink()
        proc = self.publish()
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(any(c.startswith("gh release create") for c in self.calls()))


if __name__ == "__main__":
    unittest.main()
