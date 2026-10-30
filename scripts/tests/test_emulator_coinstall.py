import unittest

from scripts.emulator import coinstall

WANTED = ("yt.ivy.embermine", coinstall.OFFICIAL_PACKAGE, coinstall.FENNEC_PACKAGE)
PM_ALL = "package:org.mozilla.fennec_fdroid\npackage:org.mozilla.firefox\npackage:yt.ivy.embermine\n"


class ResultLinesTests(unittest.TestCase):
    def test_all_three_installed_passes(self) -> None:
        lines = coinstall.result_lines(PM_ALL, WANTED, ["Success", "Success"])
        self.assertEqual(
            lines,
            [
                "yt.ivy.embermine: installed",
                "org.mozilla.firefox: installed",
                "org.mozilla.fennec_fdroid: installed",
                "co-install verdict: PASS",
            ],
        )

    def test_missing_package_fails(self) -> None:
        lines = coinstall.result_lines("package:yt.ivy.embermine\n", WANTED, ["Success"])
        self.assertIn("org.mozilla.firefox: MISSING", lines)
        self.assertEqual(lines[-1], "co-install verdict: FAIL")

    def test_install_failure_is_recorded_and_fails(self) -> None:
        failure = "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]"
        lines = coinstall.result_lines(PM_ALL, WANTED, ["Success", failure])
        self.assertIn(f"install failure: {failure}", lines)
        self.assertEqual(lines[-1], "co-install verdict: FAIL")

    def test_package_prefix_is_not_enough(self) -> None:
        lines = coinstall.result_lines("package:yt.ivy.embermine.debug\n", ("yt.ivy.embermine",), [])
        self.assertEqual(lines[0], "yt.ivy.embermine: MISSING")


if __name__ == "__main__":
    unittest.main()
