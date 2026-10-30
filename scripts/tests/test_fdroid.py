import unittest

from scripts.emulator import fdroid


def version(code: int, abi: str, name: str = "158.0.2") -> dict:
    return {
        "manifest": {"versionCode": code, "versionName": name, "nativecode": [abi]},
        "file": {"name": f"/org.mozilla.fennec_fdroid_{code}.apk"},
    }


INDEX = {
    "packages": {
        "org.mozilla.fennec_fdroid": {
            "versions": {
                "a": version(1580220, "arm64-v8a"),
                "b": version(1580210, "x86_64"),
                "c": version(1580110, "x86_64", "158.0.1"),
                "d": version(1580200, "armeabi-v7a"),
            }
        }
    }
}


class FdroidTests(unittest.TestCase):
    def test_picks_highest_version_code_of_the_abi(self) -> None:
        url, code, name = fdroid.newest_apk(INDEX, "org.mozilla.fennec_fdroid", "x86_64")
        self.assertEqual((code, name), (1580210, "158.0.2"))
        self.assertEqual(url, "https://f-droid.org/repo/org.mozilla.fennec_fdroid_1580210.apk")

    def test_unknown_package_or_abi(self) -> None:
        with self.assertRaises(LookupError):
            fdroid.newest_apk(INDEX, "org.example.none", "x86_64")
        with self.assertRaises(LookupError):
            fdroid.newest_apk(INDEX, "org.mozilla.fennec_fdroid", "mips")
