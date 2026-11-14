import os
import stat
import subprocess
import unittest

from scripts.tests.helpers import SCRIPTS, TempDirTestCase, clean_env

# Fails FAILS times with MSG and exit code RC, then succeeds. Counts its calls in COUNT.
FLAKY = """#!/usr/bin/env bash
n=$(cat "$COUNT" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" >"$COUNT"
if [ "$n" -le "$FAILS" ]; then
  echo "$MSG"
  exit "$RC"
fi
echo "done after $n call(s)"
"""


class RetryTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.count = self.tmp / "count"
        self.flaky = self.tmp / "flaky.sh"
        self.flaky.write_text(FLAKY, encoding="utf-8")
        self.flaky.chmod(self.flaky.stat().st_mode | stat.S_IXUSR)

    def run_retry(self, *args: str, fails: int, msg: str = "", rc: int = 1) -> subprocess.CompletedProcess[str]:
        env = clean_env(HOME=str(self.home), COUNT=str(self.count), FAILS=str(fails), MSG=msg, RC=str(rc))
        return subprocess.run(
            ["bash", str(SCRIPTS / "retry.sh"), *args, "--", str(self.flaky)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def calls(self) -> int:
        return int(self.count.read_text()) if self.count.exists() else 0

    def test_success_runs_the_command_once(self) -> None:
        proc = self.run_retry("--backoff", "0", fails=0)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.calls(), 1)

    def test_transient_gateway_error_is_retried_until_it_succeeds(self) -> None:
        proc = self.run_retry(
            "--attempts", "3", "--backoff", "0", "--transient-only",
            fails=2, msg="HTTP Error 504: Gateway Time-out",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.calls(), 3)
        self.assertIn("attempt 3/3 succeeded", proc.stdout)

    def test_gives_up_after_the_last_attempt_and_keeps_its_exit_status(self) -> None:
        proc = self.run_retry("--attempts", "3", "--backoff", "0", fails=10, msg="boom", rc=7)
        self.assertEqual(proc.returncode, 7)
        self.assertEqual(self.calls(), 3)
        self.assertIn("no attempts left", proc.stderr)
        self.assertIn("boom", proc.stderr)

    def test_transient_only_does_not_repeat_a_test_failure(self) -> None:
        proc = self.run_retry(
            "--attempts", "3", "--backoff", "0", "--transient-only",
            fails=10, msg="3 tests completed, 1 failed", rc=1,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.calls(), 1)
        self.assertIn("not retrying", proc.stderr)

    def test_transient_only_retries_a_gradle_resolution_error(self) -> None:
        proc = self.run_retry(
            "--attempts", "2", "--backoff", "0", "--transient-only",
            fails=1, msg="Could not resolve org.mozilla.geckoview:geckoview-omni:159.0", rc=1,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.calls(), 2)

    def test_transient_only_retries_a_gradle_504_on_a_jar_download(self) -> None:
        proc = self.run_retry(
            "--attempts", "2", "--backoff", "0", "--transient-only",
            fails=1, msg="Could not GET 'https://example.invalid/bundletool-all-1.18.3.jar'. Received status code 504 from server: Gateway Time-out", rc=1,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.calls(), 2)

    def test_without_transient_only_every_failure_is_retried(self) -> None:
        proc = self.run_retry("--attempts", "3", "--backoff", "0", fails=10, msg="anything", rc=3)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(self.calls(), 3)

    def test_log_file_keeps_the_output_of_the_last_attempt(self) -> None:
        log = self.tmp / "attempt.log"
        proc = self.run_retry("--attempts", "2", "--backoff", "0", "--log", str(log), fails=1, msg="HTTP 504 first")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(log.read_text(encoding="utf-8").strip(), "done after 2 call(s)")

    def test_stream_echoes_output_and_keeps_the_exit_status(self) -> None:
        proc = self.run_retry("--attempts", "1", "--stream", fails=1, msg="streamed failure", rc=5)
        self.assertEqual(proc.returncode, 5)
        self.assertIn("streamed failure", proc.stdout)

    def test_rejects_bad_arguments(self) -> None:
        for args in (("--attempts", "0"), ("--attempts", "x"), ("--backoff", "-1"), ("--bogus",)):
            with self.subTest(args=args):
                env = clean_env(HOME=str(self.home))
                proc = subprocess.run(
                    ["bash", str(SCRIPTS / "retry.sh"), *args, "--", "true"],
                    capture_output=True,
                    text=True,
                    env=env,
                    check=False,
                )
                self.assertEqual(proc.returncode, 2)

    def test_script_is_executable(self) -> None:
        self.assertTrue(os.access(SCRIPTS / "retry.sh", os.X_OK))


if __name__ == "__main__":
    unittest.main()
