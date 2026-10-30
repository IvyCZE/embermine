import subprocess
from pathlib import Path

from scripts.tests.helpers import TempDirTestCase, git

CI_ENV = {"GITHUB_ACTIONS": "true"}


class ApplyPatchesTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.src = self.tmp / "src"
        self.src.mkdir()
        git(self.src, "init", "-q")
        (self.src / "a.txt").write_text("base\n")
        git(self.src, "add", "a.txt")
        git(self.src, "commit", "-q", "-m", "base")
        self.base = git(self.src, "rev-parse", "HEAD")

        self.patches = self.tmp / "patches"
        self.patches.mkdir()
        for number, name in enumerate(["first", "second", "third"]):
            (self.src / "a.txt").write_text(f"{name}\n")
            git(self.src, "commit", "-q", "-am", f"Embermine: {number:04d}-{name}")
            out = git(self.src, "format-patch", "-1", "--stdout", "--subject-prefix=PATCH")
            (self.patches / f"{number:04d}-{name}.patch").write_text(out + "\n")

        self.tree = self.tmp / "tree"
        subprocess.run(["git", "clone", "-q", str(self.src), str(self.tree)], check=True)
        git(self.tree, "checkout", "-q", "--detach", self.base)

    def apply(self, list_file: Path | None = None) -> subprocess.CompletedProcess[str]:
        args = [str(self.tree), "--patch-dir", str(self.patches)]
        if list_file:
            args += ["--list", str(list_file)]
        return self.run_script("apply-patches.sh", *args, env=CI_ENV)

    def test_applies_all_patches_in_order_and_lists_them(self) -> None:
        listing = self.tmp / "applied.txt"
        proc = self.apply(listing)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            listing.read_text().split(),
            ["0000-first.patch", "0001-second.patch", "0002-third.patch"],
        )
        subjects = git(self.tree, "log", "--reverse", "--format=%s", f"{self.base}..HEAD").splitlines()
        self.assertEqual(subjects, ["Embermine: 0000-first", "Embermine: 0001-second", "Embermine: 0002-third"])
        self.assertEqual((self.tree / "a.txt").read_text(), "third\n")

    def test_failing_patch_stops_the_run_and_is_named(self) -> None:
        # Without the first patch the second one has nothing to apply to.
        (self.patches / "0000-first.patch").unlink()
        listing = self.tmp / "applied.txt"
        proc = self.apply(listing)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("0001-second.patch", proc.stderr)
        self.assertEqual(listing.read_text(), "")
        self.assertFalse((self.tree / ".git" / "rebase-apply").exists(), "git am left half-applied state")
        self.assertEqual(git(self.tree, "rev-parse", "HEAD"), self.base)

    def test_later_failure_keeps_earlier_patches_listed_but_not_the_failing_one(self) -> None:
        (self.patches / "0002-third.patch").write_text(
            (self.patches / "0002-third.patch").read_text().replace("-second", "-nonexistent")
        )
        listing = self.tmp / "applied.txt"
        proc = self.apply(listing)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("0002-third.patch", proc.stderr)
        self.assertEqual(listing.read_text().split(), ["0000-first.patch", "0001-second.patch"])

    def test_no_patches_is_an_error(self) -> None:
        for p in Path(self.patches).glob("*.patch"):
            p.unlink()
        proc = self.apply()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no patches", proc.stderr)

    def test_non_checkout_is_an_error(self) -> None:
        proc = self.run_script("apply-patches.sh", str(self.tmp / "missing"), "--patch-dir", str(self.patches))
        self.assertNotEqual(proc.returncode, 0)
