from scripts.tests.helpers import TempDirTestCase, git


class FetchSourceTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.origin = self.tmp / "origin"
        self.origin.mkdir()
        git(self.origin, "init", "-q")
        for i in range(3):
            (self.origin / "f.txt").write_text(f"{i}\n")
            git(self.origin, "add", "f.txt")
            git(self.origin, "commit", "-q", "-m", f"commit {i}")
            if i == 1:
                git(self.origin, "tag", "-a", "-m", "annotated", "REL_1")
        self.sha = git(self.origin, "rev-parse", "REL_1^{commit}")

    def fetch(self, sha: str):
        return self.run_script("fetch-source.sh", "REL_1", sha, str(self.tmp / "dest"), f"file://{self.origin}")

    def test_shallow_fetch_checks_out_the_tag_commit(self) -> None:
        proc = self.fetch(self.sha)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("git fetch --depth 1 origin refs/tags/REL_1", proc.stdout)
        dest = self.tmp / "dest"
        self.assertEqual(git(dest, "rev-parse", "HEAD"), self.sha)
        self.assertEqual(git(dest, "rev-list", "--count", "HEAD"), "1")
        self.assertEqual((dest / "f.txt").read_text(), "1\n")

    def test_sha_mismatch_fails(self) -> None:
        proc = self.fetch("0" * 40)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("resolver reported", proc.stderr)

    def test_unknown_tag_fails(self) -> None:
        proc = self.run_script("fetch-source.sh", "NOPE", self.sha, str(self.tmp / "dest"), f"file://{self.origin}")
        self.assertNotEqual(proc.returncode, 0)
