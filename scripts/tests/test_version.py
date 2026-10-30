import unittest

from scripts import version as v


class ParseFirefoxVersionTests(unittest.TestCase):
    def test_two_and_three_components(self) -> None:
        self.assertEqual(v.parse_firefox_version("159.0"), (159, 0, 0))
        self.assertEqual(v.parse_firefox_version("159.0.2"), (159, 0, 2))
        self.assertEqual(v.parse_firefox_version("160.12.34"), (160, 12, 34))

    def test_rejects_malformed(self) -> None:
        for bad in ("", "159", "159.0.2.1", "a.b", "159.0b1", "159.-1", " 159.0"):
            with self.subTest(bad=bad), self.assertRaises(v.VersionError):
                v.parse_firefox_version(bad)

    def test_rejects_components_that_do_not_fit(self) -> None:
        for bad in ("1000.0", "159.100", "159.0.100"):
            with self.subTest(bad=bad), self.assertRaises(v.VersionError):
                v.parse_firefox_version(bad)


class EmbermineVersionTests(unittest.TestCase):
    def test_release(self) -> None:
        self.assertEqual(v.embermine_version("159.0.2"), "159.0.2")

    def test_rebuild_suffix(self) -> None:
        self.assertEqual(v.embermine_version("159.0.2", rebuild=2), "159.0.2-r2")
        self.assertEqual(v.embermine_version("159.0", rebuild=9), "159.0-r9")

    def test_dev_suffix(self) -> None:
        self.assertEqual(v.embermine_version("159.0", dev_run=42), "159.0-dev.42")

    def test_rebuild_range(self) -> None:
        for bad in (0, 1, 10, 11, -3):
            with self.subTest(bad=bad), self.assertRaises(v.VersionError):
                v.embermine_version("159.0", rebuild=bad)

    def test_rebuild_and_dev_are_exclusive(self) -> None:
        with self.assertRaises(v.VersionError):
            v.embermine_version("159.0", rebuild=2, dev_run=1)


class ParseEmbermineVersionTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        self.assertEqual(v.parse_embermine_version("159.0.2"), ("159.0.2", "release", None))
        self.assertEqual(v.parse_embermine_version("159.0.2-r2"), ("159.0.2", "rebuild", 2))
        self.assertEqual(v.parse_embermine_version("159.0-r9"), ("159.0", "rebuild", 9))
        self.assertEqual(v.parse_embermine_version("159.0-dev.7"), ("159.0", "dev", 7))

    def test_r10_rejected(self) -> None:
        with self.assertRaisesRegex(v.VersionError, "r10"):
            v.parse_embermine_version("159.0-r10")

    def test_other_suffixes_rejected(self) -> None:
        for bad in ("159.0-r1", "159.0-r0", "159.0-r", "159.0-rc1", "159.0-dev", "159.0-dev.x", "159.0-"):
            with self.subTest(bad=bad), self.assertRaises(v.VersionError):
                v.parse_embermine_version(bad)


class VersionCodeTests(unittest.TestCase):
    def test_documented_examples(self) -> None:
        self.assertEqual(v.version_code("159.0.2", "arm64-v8a"), 159000211)
        self.assertEqual(v.version_code("159.0.2", "x86_64"), 159000212)
        self.assertEqual(v.version_code("159.0-dev.3", "arm64-v8a"), 159000001)
        self.assertEqual(v.version_code("159.0.2-r2", "arm64-v8a"), 159000221)

    def test_dev_run_number_does_not_change_code(self) -> None:
        self.assertEqual(
            v.version_code("159.0-dev.1", "x86_64"), v.version_code("159.0-dev.99", "x86_64")
        )

    def test_base_code(self) -> None:
        self.assertEqual(v.version_code_base("159.0.2"), 15900021)
        self.assertEqual(v.version_code_base("159.0.2-r9"), 15900029)
        self.assertEqual(v.version_code_base("159.0-dev.5"), 15900000)

    def test_unknown_abi(self) -> None:
        for bad in ("armeabi-v7a", "universal", ""):
            with self.subTest(bad=bad), self.assertRaises(v.VersionError):
                v.version_code("159.0", bad)

    def test_ordering_within_a_version(self) -> None:
        names = ["159.0-dev.1", "159.0"] + [f"159.0-r{n}" for n in range(2, 10)]
        for abi in v.ABI_DIGITS:
            codes = [v.version_code(n, abi) for n in names]
            self.assertEqual(codes, sorted(set(codes)))

    def test_abi_digit_orders_x86_above_arm64_for_same_build(self) -> None:
        self.assertLess(v.version_code("159.0", "arm64-v8a"), v.version_code("159.0", "x86_64"))

    def test_every_build_of_lower_version_below_next_version(self) -> None:
        lower = ["159.0-dev.1", "159.0"] + [f"159.0-r{n}" for n in range(2, 10)]
        higher = ["159.0.1-dev.1", "159.0.1", "159.1", "160.0-dev.1"]
        for abi_a in v.ABI_DIGITS:
            for abi_b in v.ABI_DIGITS:
                self.assertLess(
                    max(v.version_code(n, abi_a) for n in lower),
                    min(v.version_code(n, abi_b) for n in higher),
                )

    def test_r9_below_next_patch_dev(self) -> None:
        self.assertLess(v.version_code("159.0-r9", "x86_64"), v.version_code("159.0.1-dev.1", "arm64-v8a"))

    def test_fits_int32(self) -> None:
        self.assertLess(v.version_code("999.99.99-r9", "x86_64"), 2**31)


class InfoTests(unittest.TestCase):
    def test_info_for_release(self) -> None:
        info = v.build_info("159.0.2")
        self.assertEqual(
            info,
            {
                "version": "159.0.2",
                "firefox_version": "159.0.2",
                "version_code_base": "15900021",
                "version_code_arm64_v8a": "159000211",
                "version_code_x86_64": "159000212",
            },
        )

    def test_info_for_dev(self) -> None:
        info = v.build_info("159.0", dev_run=12)
        self.assertEqual(info["version"], "159.0-dev.12")
        self.assertEqual(info["firefox_version"], "159.0")
        self.assertEqual(info["version_code_arm64_v8a"], "159000001")


if __name__ == "__main__":
    unittest.main()
