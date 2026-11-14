import unittest

from scripts.release import package as p

DIGEST_HEX = "aabbccdd"


def apk_info_text(
    version_name: str,
    arm_code: str,
    x86_code: str,
    *,
    digest_hex: str = DIGEST_HEX,
    x86_digest_hex: str = DIGEST_HEX,
    x86_version_name: str | None = None,
) -> str:
    """Text in the format apk-info.sh writes (only the lines the checks read, plus the aapt2 package line)."""
    x86_version_name = x86_version_name or version_name
    return (
        f"=== embermine-{version_name}-arm64-v8a.apk (1 bytes)\n"
        f"package: name='yt.ivy.embermine' versionCode='{arm_code}' versionName='{version_name}'\n"
        f"versionCode: {arm_code}\n"
        f"versionName: {version_name}\n"
        "signature-verified: yes\n"
        "signer-sha256: AA:BB:CC:DD\n"
        f"signer-sha256-hex: {digest_hex}\n"
        "\n"
        f"=== embermine-{version_name}-x86_64.apk (1 bytes)\n"
        f"versionCode: {x86_code}\n"
        f"versionName: {x86_version_name}\n"
        "signature-verified: yes\n"
        "signer-sha256: AA:BB:CC:DD\n"
        f"signer-sha256-hex: {x86_digest_hex}\n"
    )


def build_info(**overrides: object) -> dict[str, object]:
    info: dict[str, object] = {
        "version": "159.0",
        "embermine_version": "159.0",
        "tag": "FIREFOX-ANDROID_159_0_RELEASE",
        "sha": "9a2dc53c369c7ae5172018b35988e1d2ffeff402",
        "buildid": "20261022150525",
        "signing": "owner",
        "patches": ["0000-build-infra.patch"],
        "patch_subjects": ["Embermine: 0000-build-infra"],
    }
    info.update(overrides)
    return info


FILES = ["embermine-159.0-arm64-v8a.apk", "embermine-159.0-x86_64.apk", "apk-info.txt", "build-info.json"]


class ArtifactCheckTests(unittest.TestCase):
    def check(self, *, version: str = "159.0", files=FILES, info=None, apk_text=None) -> list[str]:
        if apk_text is None:
            apk_text = apk_info_text("159.0", "159000011", "159000012")
        return p.check_release_artifacts(
            dist_files=list(files),
            embermine_version=version,
            build_info=info if info is not None else build_info(),
            apk_info=p.read_apk_info(apk_text),
        )

    def test_release_artifacts_pass(self) -> None:
        self.assertEqual(self.check(), [])

    def test_rebuild_artifacts_pass_with_the_rebuild_digit_in_versioncode(self) -> None:
        files = ["embermine-159.0-r2-arm64-v8a.apk", "embermine-159.0-r2-x86_64.apk"]
        info = build_info(embermine_version="159.0-r2")
        apk_text = apk_info_text("159.0-r2", "159000021", "159000022")
        self.assertEqual(self.check(version="159.0-r2", files=files, info=info, apk_text=apk_text), [])

    def test_wrong_file_names_fail(self) -> None:
        errors = self.check(files=["embermine-159.0-arm64-v8a.apk", "app-x86_64-release.apk"])
        self.assertTrue(any("APK files" in e for e in errors), errors)

    def test_throwaway_signing_fails(self) -> None:
        errors = self.check(info=build_info(signing="throwaway"))
        self.assertTrue(any("owner" in e for e in errors), errors)

    def test_version_name_must_be_exact(self) -> None:
        text = apk_info_text("159.0", "159000011", "159000012", x86_version_name="159.0-dev.4")
        errors = self.check(apk_text=text)
        self.assertTrue(any("versionName" in e for e in errors), errors)

    def test_base_release_needs_rebuild_digit_one(self) -> None:
        errors = self.check(apk_text=apk_info_text("159.0", "159000001", "159000002"))
        self.assertTrue(any("versionCode" in e for e in errors), errors)

    def test_both_apks_must_share_one_signer(self) -> None:
        text = apk_info_text("159.0", "159000011", "159000012", x86_digest_hex="11223344")
        errors = self.check(apk_text=text)
        self.assertTrue(any("signer" in e for e in errors), errors)

    def test_build_info_must_match_the_version(self) -> None:
        errors = self.check(info=build_info(embermine_version="159.0-r2"))
        self.assertTrue(any("embermine_version" in e for e in errors), errors)

    def test_missing_patch_list_fails(self) -> None:
        errors = self.check(info=build_info(patches=[]))
        self.assertTrue(any("patches" in e for e in errors), errors)

    def test_missing_apk_info_entry_fails(self) -> None:
        text = apk_info_text("159.0", "159000011", "159000012").split("=== embermine-159.0-x86_64")[0]
        errors = self.check(apk_text=text)
        self.assertTrue(any("x86_64" in e for e in errors), errors)


class UrlCheckTests(unittest.TestCase):
    def test_a_200_answer_passes(self) -> None:
        self.assertEqual(p.check_notes_url("https://example.invalid/x", lambda url: 200), [])

    def test_any_other_answer_fails_with_the_url(self) -> None:
        errors = p.check_notes_url("https://example.invalid/x", lambda url: 404)
        self.assertEqual(len(errors), 1)
        self.assertIn("404", errors[0])
        self.assertIn("https://example.invalid/x", errors[0])


class ApkInfoTests(unittest.TestCase):
    def test_read_apk_info_splits_entries_by_file(self) -> None:
        info = p.read_apk_info(apk_info_text("159.0", "159000011", "159000012"))
        self.assertEqual(info["embermine-159.0-arm64-v8a.apk"]["versionCode"], "159000011")
        self.assertEqual(info["embermine-159.0-x86_64.apk"]["versionCode"], "159000012")
        self.assertEqual(info["embermine-159.0-x86_64.apk"]["versionName"], "159.0")


if __name__ == "__main__":
    unittest.main()
