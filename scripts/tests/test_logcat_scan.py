import unittest

from scripts.emulator import logcat_scan

LOG = """\
10-30 09:31:50.100  1111  1111 I ActivityManager: Start proc org.mozilla.firefox
10-30 09:31:51.000  2222  2222 E AndroidRuntime: FATAL EXCEPTION: main
10-30 09:31:51.000  2222  2222 E AndroidRuntime: Process: org.mozilla.firefox, PID: 2222
10-30 09:31:51.000  2222  2222 E AndroidRuntime: java.lang.IllegalStateException: boom
10-30 09:31:51.000  2222  2222 E AndroidRuntime: \tat org.mozilla.fenix.HomeActivity.onCreate(HomeActivity.kt:1)
10-30 09:31:51.050  3333  3333 I Other: unrelated line
10-30 09:32:00.000  4444  4444 E AndroidRuntime: FATAL EXCEPTION: main
10-30 09:32:00.000  4444  4444 E AndroidRuntime: Process: com.example.other, PID: 4444
10-30 09:32:00.000  4444  4444 E AndroidRuntime: java.lang.RuntimeException
10-30 09:33:00.000   500   500 E ActivityManager: ANR in org.mozilla.firefox (org.mozilla.firefox/org.mozilla.fenix.HomeActivity)
"""


class LogcatScanTests(unittest.TestCase):
    def test_finds_fatal_exceptions_with_their_process(self) -> None:
        fatal = [f for f in logcat_scan.scan(LOG) if f.kind == "FATAL EXCEPTION"]
        self.assertEqual([f.process for f in fatal], ["org.mozilla.firefox", "com.example.other"])

    def test_block_stops_at_a_different_pid(self) -> None:
        first = logcat_scan.scan(LOG)[0]
        self.assertEqual(len(first.lines), 4)
        self.assertNotIn("unrelated line", "\n".join(first.lines))

    def test_finds_anr(self) -> None:
        anr = [f for f in logcat_scan.scan(LOG) if f.kind == "ANR"]
        self.assertEqual([f.process for f in anr], ["org.mozilla.firefox"])

    def test_report_counts_only_the_package(self) -> None:
        text, ours = logcat_scan.report(LOG, "org.mozilla.firefox")
        self.assertEqual(ours, 2)
        self.assertIn("attributed to org.mozilla.firefox: 2", text)
        self.assertIn("(other process)", text)

    def test_clean_log(self) -> None:
        text, ours = logcat_scan.report("10-30 09:31:50.100  1  1 I Tag: all good\n", "yt.ivy.embermine")
        self.assertEqual(ours, 0)
        self.assertIn("No FATAL EXCEPTION", text)

    def test_package_match_includes_child_processes_only(self) -> None:
        self.assertTrue(logcat_scan.matches_package("yt.ivy.embermine:gpu", "yt.ivy.embermine"))
        self.assertFalse(logcat_scan.matches_package("yt.ivy.embermine2", "yt.ivy.embermine"))
