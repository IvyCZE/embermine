import json
import os
import stat
import subprocess
import unittest

from scripts.release import failure_report as fr
from scripts.tests.helpers import SCRIPTS, TempDirTestCase, clean_env

RUN_URL = "https://github.com/IvyCZE/embermine/actions/runs/123456789"

JOBS = {
    "jobs": [
        {
            "id": 11,
            "name": "detect",
            "conclusion": "success",
            "steps": [{"name": "Detect and decide", "conclusion": "success"}],
        },
        {
            "id": 22,
            "name": "build / build",
            "conclusion": "failure",
            "steps": [
                {"name": "Apply patches", "conclusion": "failure"},
                {"name": "Run generators", "conclusion": "skipped"},
            ],
        },
        {"id": 33, "name": "publish", "conclusion": "skipped", "steps": []},
        {"id": 44, "name": "report-failure", "conclusion": None, "steps": []},
    ]
}

PATCH_LOG = """2026-11-14T08:00:01.0000000Z ##[group]Run bash scripts/apply-patches.sh fx --list x
2026-11-14T08:00:02.0000000Z applying 0000-build-infra.patch: Pin material3
2026-11-14T08:00:03.0000000Z applying 0003-about-config-and-secret-settings.patch: Enable about:config
2026-11-14T08:00:04.0000000Z Applying: Embermine: 0003-about-config-and-secret-settings
2026-11-14T08:00:04.5000000Z error: patch failed: mobile/android/fenix/app/src/main/Foo.kt:12
2026-11-14T08:00:04.6000000Z error: mobile/android/fenix/app/src/main/Foo.kt: patch does not apply
2026-11-14T08:00:05.0000000Z error: patch 0003-about-config-and-secret-settings.patch failed to apply; stopping
2026-11-14T08:00:05.1000000Z ##[error]Process completed with exit code 1.
2026-11-14T08:00:05.2000000Z ##[group]Post job cleanup.
2026-11-14T08:00:06.0000000Z Post job cleanup done
"""


class JobParsingTests(unittest.TestCase):
    def test_failed_jobs_are_the_ones_with_failure_conclusion(self) -> None:
        self.assertEqual([j["id"] for j in fr.failed_jobs(JOBS)], [22])

    def test_failed_step_names(self) -> None:
        self.assertEqual(fr.failed_step_names(JOBS["jobs"][1]), ["Apply patches"])
        self.assertEqual(fr.failed_step_names(JOBS["jobs"][0]), [])


class LogParsingTests(unittest.TestCase):
    def test_excerpt_is_the_output_before_the_error_marker_without_timestamps(self) -> None:
        excerpt = fr.error_excerpt(PATCH_LOG)
        self.assertIn("error: patch 0003-about-config-and-secret-settings.patch failed to apply; stopping", excerpt)
        self.assertIn("Process completed with exit code 1.", excerpt)
        self.assertNotIn("2026-11-14T", excerpt)
        self.assertNotIn("Post job cleanup", excerpt)
        self.assertNotIn("##[error]", excerpt)

    def test_excerpt_without_a_marker_is_the_tail_of_the_log(self) -> None:
        log = "\n".join(f"line {i}" for i in range(100))
        excerpt = fr.error_excerpt(log, window=5)
        self.assertEqual(excerpt.splitlines(), [f"line {i}" for i in range(95, 100)])

    def test_excerpt_is_capped_in_size(self) -> None:
        excerpt = fr.error_excerpt("x" * 50_000 + "\n##[error]boom")
        self.assertLessEqual(len(excerpt), fr.EXCERPT_LIMIT + 200)
        self.assertIn("boom", excerpt)

    def test_failing_patch_is_named_from_the_apply_message(self) -> None:
        self.assertEqual(fr.failing_patch(PATCH_LOG), "0003-about-config-and-secret-settings.patch")
        self.assertIsNone(fr.failing_patch("Gradle BUILD FAILED"))

    def test_ansi_colours_are_removed(self) -> None:
        self.assertEqual(fr.error_excerpt("\x1b[31mred\x1b[0m\n##[error]bad"), "red\nbad")


class BodyTests(unittest.TestCase):
    def test_body_names_version_step_patch_excerpt_and_run(self) -> None:
        body = fr.build_report(JOBS, {22: PATCH_LOG}, firefox="150.0", run_url=RUN_URL)
        self.assertIn("Firefox 150.0", body)
        self.assertIn(RUN_URL, body)
        self.assertIn("build / build", body)
        self.assertIn("Apply patches", body)
        self.assertIn("0003-about-config-and-secret-settings.patch", body)
        self.assertIn("patch 0003-about-config-and-secret-settings.patch failed to apply", body)
        self.assertIn("No GitHub Release was created.", body)

    def test_body_without_a_failed_job_still_links_the_run(self) -> None:
        body = fr.build_report({"jobs": []}, {}, firefox="159.0", run_url=RUN_URL)
        self.assertIn(RUN_URL, body)
        self.assertIn("Firefox 159.0", body)
        self.assertIn("No failed job was found", body)

    def test_unknown_version_is_named_as_unknown(self) -> None:
        body = fr.build_report(JOBS, {22: PATCH_LOG}, firefox="", run_url=RUN_URL)
        self.assertIn("Firefox unknown", body)

    def test_title_names_the_firefox_version(self) -> None:
        self.assertEqual(fr.issue_title("150.0"), "Release run failed for Firefox 150.0")


class IssueLookupTests(unittest.TestCase):
    def test_finds_the_open_issue_with_the_exact_title(self) -> None:
        issues = [{"number": 3, "title": "Release run failed for Firefox 15.0"}, {"number": 9, "title": "Release run failed for Firefox 150.0"}]
        self.assertEqual(fr.find_issue(issues, "Release run failed for Firefox 150.0"), 9)

    def test_no_match_returns_none(self) -> None:
        self.assertIsNone(fr.find_issue([{"number": 3, "title": "other"}], "Release run failed for Firefox 150.0"))


STUB_GH = """#!/usr/bin/env bash
echo "gh $*" >>"$STUB_LOG"
case "$1 $2" in
  "api repos/"*/actions/runs/*/jobs*) cat "$JOBS_FILE" ;;
  "api repos/"*/actions/jobs/*/logs) cat "$LOG_FILE" ;;
  "issue list") cat "$ISSUES_FILE" ;;
  "issue create"|"issue comment")
    while [ $# -gt 0 ]; do
      if [ "$1" = "--body-file" ]; then cp "$2" "$BODY_OUT"; fi
      shift
    done
    echo "https://github.com/IvyCZE/embermine/issues/77"
    ;;
esac
"""


class ReportScriptTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(STUB_GH, encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        self.log = self.tmp / "gh.log"
        self.log.write_text("", encoding="utf-8")
        self.jobs = self.tmp / "jobs.json"
        self.jobs.write_text(json.dumps(JOBS), encoding="utf-8")
        self.job_log = self.tmp / "job.log"
        self.job_log.write_text(PATCH_LOG, encoding="utf-8")
        self.issues = self.tmp / "issues.json"
        self.body = self.tmp / "body.md"

    def run_report(self, issues: list[dict[str, object]]) -> subprocess.CompletedProcess[str]:
        self.issues.write_text(json.dumps(issues), encoding="utf-8")
        env = clean_env(
            HOME=str(self.home),
            PATH=f"{self.bin}:/usr/bin:/bin",
            STUB_LOG=str(self.log),
            JOBS_FILE=str(self.jobs),
            LOG_FILE=str(self.job_log),
            ISSUES_FILE=str(self.issues),
            BODY_OUT=str(self.body),
            GH_TOKEN="x",
            REPO="IvyCZE/embermine",
            RUN_ID="123456789",
            RUN_URL=RUN_URL,
            FIREFOX_VERSION="150.0",
        )
        return subprocess.run(
            ["bash", str(SCRIPTS / "release" / "report-failure.sh")],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def gh_calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def test_opens_an_issue_when_none_is_open_for_the_version(self) -> None:
        proc = self.run_report([])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        calls = self.gh_calls()
        self.assertTrue(any("issue create" in c for c in calls), calls)
        self.assertFalse(any("issue comment" in c for c in calls), calls)
        body = self.body.read_text(encoding="utf-8")
        self.assertIn("Firefox 150.0", body)
        self.assertIn(RUN_URL, body)
        self.assertIn("0003-about-config-and-secret-settings.patch", body)

    def test_comments_on_the_open_issue_for_the_same_version(self) -> None:
        proc = self.run_report([{"number": 12, "title": "Release run failed for Firefox 150.0"}])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        calls = self.gh_calls()
        self.assertTrue(any("issue comment 12" in c for c in calls), calls)
        self.assertFalse(any("issue create" in c for c in calls), calls)

    def test_a_different_version_gets_its_own_issue(self) -> None:
        self.run_report([{"number": 12, "title": "Release run failed for Firefox 159.0"}])
        calls = self.gh_calls()
        self.assertTrue(any("issue create" in c for c in calls), calls)


if __name__ == "__main__":
    unittest.main()
