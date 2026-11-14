import unittest

from scripts.release import naming as n
from scripts.version import VersionError


class NamingTests(unittest.TestCase):
    def test_release_tag_and_title(self) -> None:
        self.assertEqual(n.release_tag("159.0"), "v159.0")
        self.assertEqual(n.release_title("159.0"), "Embermine 159.0")

    def test_rebuild_tag_keeps_the_suffix(self) -> None:
        self.assertEqual(n.release_tag("159.0-r2"), "v159.0-r2")
        self.assertEqual(n.release_title("159.0-r2"), "Embermine 159.0-r2")

    def test_release_asset_names(self) -> None:
        self.assertEqual(n.apk_name("159.0", "arm64-v8a"), "embermine-159.0-arm64-v8a.apk")
        self.assertEqual(n.apk_name("159.0", "x86_64"), "embermine-159.0-x86_64.apk")

    def test_rebuild_asset_names(self) -> None:
        self.assertEqual(n.apk_name("159.0-r2", "arm64-v8a"), "embermine-159.0-r2-arm64-v8a.apk")
        self.assertEqual(n.apk_names("159.0-r2"), ["embermine-159.0-r2-arm64-v8a.apk", "embermine-159.0-r2-x86_64.apk"])

    def test_apk_names_are_the_release_assets_in_order(self) -> None:
        self.assertEqual(n.apk_names("159.0"), ["embermine-159.0-arm64-v8a.apk", "embermine-159.0-x86_64.apk"])

    def test_unknown_abi_is_rejected(self) -> None:
        with self.assertRaises(VersionError):
            n.apk_name("159.0", "armeabi-v7a")

    def test_rebuild_beyond_r9_is_rejected(self) -> None:
        with self.assertRaises(VersionError):
            n.release_tag("159.0-r10")
        with self.assertRaises(VersionError):
            n.apk_names("159.0-r10")

    def test_dev_versions_are_not_release_names(self) -> None:
        with self.assertRaises(VersionError):
            n.release_tag("159.0-dev.4")


if __name__ == "__main__":
    unittest.main()
