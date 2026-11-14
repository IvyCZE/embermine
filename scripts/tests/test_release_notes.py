import tempfile
import unittest
from pathlib import Path

from scripts.release import notes as n
from scripts.tests.helpers import REPO_ROOT

PATCH_TEXT = """From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: IvyCZE <me@ivy.yt>
Date: Sat, 7 Nov 2026 20:10:30 +0000
Subject: [PATCH] Embermine: 0042-example

Add the first paragraph of the
example change in two lines.

A second paragraph that the notes must not use.

Co-authored-by: factory-droid[bot] <138933559+factory-droid[bot]@users.noreply.github.com>

diff --git a/file.txt b/file.txt
index 1111111..2222222 100644
--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-old
+new
--
2.50.0
"""


class NotesTests(unittest.TestCase):
    def test_mozilla_release_notes_url_is_the_form_that_returns_200_directly(self) -> None:
        self.assertEqual(
            n.mozilla_release_notes_url("159.0"),
            "https://www.firefox.com/en-US/firefox/android/159.0/releasenotes/",
        )
        self.assertEqual(
            n.mozilla_release_notes_url("159.0.1"),
            "https://www.firefox.com/en-US/firefox/android/159.0.1/releasenotes/",
        )

    def test_first_paragraph_is_the_description_without_trailers_or_diff(self) -> None:
        name, text = n.patch_description_from_text("0042-example.patch", PATCH_TEXT)
        self.assertEqual(name, "0042-example.patch")
        self.assertEqual(text, "Add the first paragraph of the example change in two lines.")

    def test_patch_without_a_message_is_described_by_the_files_it_changes(self) -> None:
        text = (
            "Subject: [PATCH] Embermine: 0099-bare\n\n\n"
            "diff --git a/x/A.kt b/x/A.kt\n--- a/x/A.kt\n+++ b/x/A.kt\n"
            "diff --git a/y/B.kt b/y/B.kt\n--- a/y/B.kt\n+++ b/y/B.kt\n"
        )
        _, description = n.patch_description_from_text("0099-bare.patch", text)
        self.assertEqual(description, "Changes 2 files: A.kt, B.kt.")

    def test_patch_without_a_message_or_diff_is_rejected(self) -> None:
        with self.assertRaises(n.NotesError):
            n.patch_description_from_text("0099-empty.patch", "Subject: [PATCH] x\n\n---\n")

    def test_release_notes_for_a_release(self) -> None:
        text = n.render_notes(
            firefox_version="159.0",
            embermine_version="159.0",
            tag="FIREFOX-ANDROID_159_0_RELEASE",
            sha="9a2dc53c369c7ae5172018b35988e1d2ffeff402",
            buildid="20261022150525",
            rebuild=None,
            changes=[("0042-example.patch", "Add the first paragraph.")],
        )
        self.assertIn("# Embermine 159.0", text)
        self.assertIn("Firefox 159.0", text)
        self.assertIn("https://www.firefox.com/en-US/firefox/android/159.0/releasenotes/", text)
        self.assertIn("## Embermine changes", text)
        self.assertIn("- **0042-example**: Add the first paragraph.", text)
        self.assertIn("embermine-159.0-arm64-v8a.apk", text)
        self.assertIn("embermine-159.0-x86_64.apk", text)
        self.assertNotIn("rebuild", text.lower())

    def test_release_notes_for_a_rebuild_say_it_is_the_same_firefox_version(self) -> None:
        text = n.render_notes(
            firefox_version="159.0",
            embermine_version="159.0-r2",
            tag="FIREFOX-ANDROID_159_0_RELEASE",
            sha="9a2dc53c369c7ae5172018b35988e1d2ffeff402",
            buildid="20261022150525",
            rebuild=2,
            changes=[("0042-example.patch", "Add the first paragraph.")],
        )
        self.assertIn("# Embermine 159.0-r2", text)
        self.assertIn("rebuild", text.lower())
        self.assertIn("-r2", text)
        self.assertIn("same Firefox", text)
        self.assertIn("embermine-159.0-r2-arm64-v8a.apk", text)

    def test_release_notes_need_at_least_one_change(self) -> None:
        with self.assertRaises(n.NotesError):
            n.render_notes(
                firefox_version="159.0",
                embermine_version="159.0",
                tag="FIREFOX-ANDROID_159_0_RELEASE",
                sha="abc",
                buildid="20261022150525",
                rebuild=None,
                changes=[],
            )

    def test_every_patch_in_the_repository_has_a_description(self) -> None:
        changes = n.read_changes(REPO_ROOT / "patches")
        self.assertGreaterEqual(len(changes), 1)
        names = [name for name, _ in changes]
        self.assertEqual(names, sorted(names))
        for name, text in changes:
            with self.subTest(patch=name):
                self.assertTrue(text, "empty description")
                self.assertNotRegex(text.lower(), r"placeholder|todo")

    def test_read_changes_reads_patch_files_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "0002-b.patch").write_text(PATCH_TEXT.replace("0042", "0002"), encoding="utf-8")
            (d / "0001-a.patch").write_text(PATCH_TEXT.replace("0042", "0001"), encoding="utf-8")
            (d / "notes.txt").write_text("ignored", encoding="utf-8")
            self.assertEqual([name for name, _ in n.read_changes(d)], ["0001-a.patch", "0002-b.patch"])


if __name__ == "__main__":
    unittest.main()
