import re
import unittest

from scripts.tests.helpers import REPO_ROOT

WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def job(body: str, name: str) -> str:
    """The text of one top-level job of a workflow (from its key to the next job key)."""
    start = re.search(rf"(?m)^  {re.escape(name)}:\n", body)
    if not start:
        raise AssertionError(f"no job {name}")
    nxt = re.search(r"(?m)^  [a-z][a-z-]*:\n", body[start.end() :])
    end = start.end() + nxt.start() if nxt else len(body)
    return body[start.start() : end]


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.release = text("release.yml")

    def test_triggers_are_a_daily_cron_and_manual_dispatch_only(self) -> None:
        self.assertRegex(self.release, r'(?m)^  schedule:\n    - cron: "\d{1,2} \d{1,2} \* \* \*"$')
        self.assertRegex(self.release, r"(?m)^  workflow_dispatch:\n")
        self.assertNotRegex(self.release, r"(?m)^  (push|pull_request):")

    def test_dispatch_inputs_version_rebuild_and_dry_run_with_dry_run_default_true(self) -> None:
        dispatch = self.release[self.release.index("  workflow_dispatch:") : self.release.index("permissions:")]
        self.assertIn("version:", dispatch)
        self.assertIn("rebuild:", dispatch)
        self.assertRegex(dispatch, r"dry_run:\n\s+description: [^\n]+\n\s+type: boolean\n\s+default: true")

    def test_permissions_allow_releases_and_issues(self) -> None:
        self.assertIn("  contents: write", self.release)
        self.assertIn("  issues: write", self.release)

    def test_build_reuses_build_yml_in_release_mode_and_inherits_secrets(self) -> None:
        build = job(self.release, "build")
        self.assertIn("uses: ./.github/workflows/build.yml", build)
        self.assertIn("release: true", build)
        self.assertIn("secrets: inherit", build)

    def test_no_workflow_or_script_references_the_key_alias_secret(self) -> None:
        shipped = [
            *WORKFLOWS.glob("*.yml"),
            *(p for p in (REPO_ROOT / "scripts").rglob("*") if p.suffix in (".sh", ".py") and "tests" not in p.parts),
        ]
        self.assertGreater(len(shipped), 10)
        for path in shipped:
            with self.subTest(file=str(path.relative_to(REPO_ROOT))):
                self.assertNotIn("secrets.KEY_ALIAS", path.read_text(encoding="utf-8"))

    def test_publish_is_gated_by_a_strict_variable_comparison(self) -> None:
        publish = job(self.release, "publish")
        self.assertIn("vars.EMBERMINE_PUBLISH == 'true'", publish)
        self.assertIn("needs.detect.outputs.publish == 'true'", publish)

    def test_publish_needs_detect_build_and_package_with_no_override(self) -> None:
        publish = job(self.release, "publish")
        self.assertRegex(publish, r"needs: \[detect, build, package\]")
        self.assertNotIn("always()", publish)
        self.assertNotIn("cancelled()", publish)
        self.assertNotIn("continue-on-error", self.release)

    def test_release_is_created_only_by_the_publish_script(self) -> None:
        self.assertNotIn("gh release create", self.release)
        self.assertIn("bash scripts/release/publish.sh", job(self.release, "publish"))

    def test_failure_report_runs_on_failure_of_any_stage_and_never_publishes(self) -> None:
        report = job(self.release, "report-failure")
        self.assertIn("if: failure()", report)
        self.assertRegex(report, r"needs: \[detect, build, package, publish\]")
        self.assertIn("bash scripts/release/report-failure.sh", report)
        self.assertNotIn("publish.sh", report)

    def test_build_is_skipped_when_the_detection_says_so(self) -> None:
        self.assertIn("if: needs.detect.outputs.build == 'true'", job(self.release, "build"))
        self.assertIn("if: needs.detect.outputs.build == 'true'", job(self.release, "package"))

    def test_detection_runs_the_python_module_with_the_gate_and_inputs(self) -> None:
        detect = job(self.release, "detect")
        self.assertIn("python3 -m scripts.release.detect", detect)
        self.assertIn("GATE: ${{ vars.EMBERMINE_PUBLISH }}", detect)
        self.assertIn("--github-output", detect)

    def test_packaging_checks_the_build_before_notes_and_upload(self) -> None:
        package = job(self.release, "package")
        self.assertIn("python3 -m scripts.release.package", package)
        self.assertIn("name: embermine-build", package)
        self.assertIn("name: release-notes", package)


class RetryWiringTests(unittest.TestCase):
    def test_ci_gradle_unit_tests_retry_only_transient_failures(self) -> None:
        ci = text("ci.yml")
        step = ci[ci.index("- name: Gradle unit tests") : ci.index("- name: Check that the tests really ran")]
        self.assertIn('bash "$GITHUB_WORKSPACE/scripts/retry.sh" --attempts 3 --backoff 60 --transient-only', step)
        self.assertIn("./gradlew --no-daemon", step)

    def test_mach_bootstrap_is_retried_in_the_shared_configure_script(self) -> None:
        configure = (REPO_ROOT / "scripts" / "configure-tree.sh").read_text(encoding="utf-8")
        self.assertRegex(configure, r"retry\.sh\" --attempts 3 --backoff 60 --log \"\$bootstrap_log\" -- \\\n\s+\./mach --no-interactive bootstrap")
        for name in ("build.yml", "ci.yml"):
            with self.subTest(workflow=name):
                self.assertIn("scripts/configure-tree.sh fx", text(name))

    def test_release_build_still_requires_the_owner_key(self) -> None:
        build = text("build.yml")
        self.assertIn("if [ \"$RELEASE_INPUT\" = true ]; then args+=(--require-owner-key); fi", build)


if __name__ == "__main__":
    unittest.main()
