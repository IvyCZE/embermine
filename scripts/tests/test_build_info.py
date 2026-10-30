import json
import subprocess
import sys

from scripts import build_info
from scripts.tests.helpers import SCRIPTS, TempDirTestCase


class BuildInfoTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.patches = self.tmp / "patches"
        self.patches.mkdir()
        for name in ("0001-branding.patch", "0000-build-infra.patch"):
            subject = "Embermine: " + name[:-6]
            (self.patches / name).write_text(f"From 0\nSubject: [PATCH] {subject}\n\ndiff\n")

    def info(self, applied: list[str]) -> dict[str, object]:
        return build_info.build_info(
            firefox_version="159.0",
            embermine_version="159.0-dev.7",
            version_code_base="15900000",
            tag="FIREFOX-ANDROID_159_0_RELEASE",
            sha="9a2dc53c",
            buildid="20261022150525",
            signing="owner",
            applied=applied,
            patch_dir=self.patches,
        )

    def test_lists_patches_in_order_with_subjects(self) -> None:
        info = self.info(["0000-build-infra.patch", "0001-branding.patch"])
        self.assertEqual(info["patches"], ["0000-build-infra.patch", "0001-branding.patch"])
        self.assertEqual(info["patch_subjects"], ["Embermine: 0000-build-infra", "Embermine: 0001-branding"])
        self.assertEqual(info["version"], "159.0")
        self.assertEqual(info["embermine_version"], "159.0-dev.7")
        self.assertEqual(info["geckoview_version"], "159.0.20261022150525")

    def test_rejects_applied_list_that_differs_from_patch_dir(self) -> None:
        for applied in (["0000-build-infra.patch"], ["0001-branding.patch", "0000-build-infra.patch"]):
            with self.subTest(applied=applied), self.assertRaises(build_info.BuildInfoError):
                self.info(applied)

    def test_cli_writes_json(self) -> None:
        applied = self.tmp / "applied.txt"
        applied.write_text("0000-build-infra.patch\n0001-branding.patch\n")
        out = self.tmp / "build-info.json"
        proc = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "build_info.py"),
                "--firefox-version", "159.0", "--embermine-version", "159.0-dev.7",
                "--version-code-base", "15900000", "--tag", "FIREFOX_159_0_RELEASE", "--sha", "abc",
                "--buildid", "20261022150525", "--signing", "throwaway", "--applied", str(applied),
                "--patch-dir", str(self.patches), "--out", str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(out.read_text())
        self.assertEqual(data["signing"], "throwaway")
        self.assertEqual(data["patches"], ["0000-build-infra.patch", "0001-branding.patch"])
