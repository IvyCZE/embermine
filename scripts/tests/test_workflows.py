import re
import unittest

from scripts.tests.helpers import REPO_ROOT

WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class CiWorkflowTests(unittest.TestCase):
    def test_triggers_cover_all_branches_prs_and_manual_runs(self) -> None:
        ci = text("ci.yml")
        for trigger in ("push:", "pull_request:", "workflow_dispatch:"):
            self.assertIn(trigger, ci)
        self.assertIn("cancel-in-progress: true", ci)
        self.assertRegex(ci, r"group: .*github\.ref")

    def test_ci_and_build_never_publish_or_write_contents(self) -> None:
        for name in ("ci.yml", "build.yml"):
            body = text(name)
            with self.subTest(workflow=name):
                self.assertNotRegex(body, r"contents:\s*write")
                self.assertNotRegex(body, r"gh release|action-gh-release|git push|create-release|git tag")

    def test_legacy_emulator_job_runs_the_api_30_walk_after_the_build(self) -> None:
        ci = text("ci.yml")
        job = ci[ci.index("  emulator-legacy:") : ci.index("  unit-tests:")]
        self.assertIn("needs: build", job)
        self.assertIn("api-level: 30", job)
        self.assertIn("target: google_apis", job)
        self.assertIn("arch: x86_64", job)
        self.assertIn("--variant legacy", job)
        self.assertIn("name: screenshots-legacy", job)

    def test_build_steps_cannot_be_skipped_after_a_failure(self) -> None:
        for name in ("ci.yml", "build.yml"):
            body = text(name)
            with self.subTest(workflow=name):
                self.assertNotIn("continue-on-error", body)
        self.assertNotIn("always()", text("build.yml"))

    def test_build_has_the_mandatory_memory_settings_and_caches(self) -> None:
        build = text("build.yml")
        for needle in ("fallocate -l 8G", "-Xmx6g", "kotlin.daemon.jvmargs=-Xmx3g", "--max-workers=3", "oom_score_adj"):
            self.assertIn(needle, build)
        self.assertIn("~/.mozbuild", build)
        self.assertIn("setup-gradle", build)

    def test_unit_tests_job_has_the_same_memory_settings(self) -> None:
        ci = text("ci.yml")
        self.assertRegex(ci, r"(?m)^  unit-tests:")
        for needle in ("fallocate -l 8G", "-Xmx6g", "kotlin.daemon.jvmargs=-Xmx3g", "--max-workers=3", "oom_score_adj"):
            self.assertIn(needle, ci)
        self.assertIn("org.mozilla.fenix.embermine.EmbermineVersionTest", ci)

    def test_signing_secrets_are_only_exposed_to_the_signing_step(self) -> None:
        build = text("build.yml")
        occurrences = [m.start() for m in re.finditer(r"secrets\.KEYSTORE_PASSWORD", build)]
        self.assertEqual(len(occurrences), 1)
        self.assertIn("scripts/sign.sh", build[occurrences[0] :])

    def test_release_mode_requires_the_owner_key(self) -> None:
        self.assertIn("--require-owner-key", text("build.yml"))
