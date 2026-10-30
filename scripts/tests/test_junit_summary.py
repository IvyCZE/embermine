import contextlib
import io

from scripts import junit_summary
from scripts.tests.helpers import TempDirTestCase

CLASS = "org.mozilla.fenix.embermine.EmbermineVersionTest"


def suite_xml(name: str, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="{name}" tests="{tests}" '
        f'skipped="{skipped}" failures="{failures}" errors="{errors}"></testsuite>\n'
    )


class JunitSummaryTests(TempDirTestCase):
    def write(self, name: str, xml: str) -> None:
        path = self.tmp / "results" / f"TEST-{name}.xml"
        path.parent.mkdir(exist_ok=True)
        path.write_text(xml)

    def run_main(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = junit_summary.main([str(self.tmp / "results"), *args])
        return rc, out.getvalue(), err.getvalue()

    def test_counts_tests_and_requires_class(self) -> None:
        self.write(CLASS, suite_xml(CLASS, 3))
        self.write("Other", suite_xml("other.Test", 2))
        rc, out, _ = self.run_main("--require-class", CLASS)
        self.assertEqual(rc, 0)
        self.assertIn("Unit tests executed: 5 (failures: 0, errors: 0, skipped: 0)", out)
        self.assertIn(f"{CLASS}: 3 tests", out)

    def test_zero_tests_fail(self) -> None:
        self.write("Empty", suite_xml("empty.Test", 0))
        rc, _, err = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("no tests were executed", err)

    def test_missing_results_fail(self) -> None:
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("Unit tests executed: 0", out)

    def test_failures_and_errors_fail(self) -> None:
        self.write("A", suite_xml("a.Test", 2, failures=1))
        self.write("B", suite_xml("b.Test", 2, errors=1))
        rc, _, err = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("a.Test", err)
        self.assertIn("b.Test", err)

    def test_required_class_must_have_run(self) -> None:
        self.write("Other", suite_xml("other.Test", 4))
        rc, _, err = self.run_main("--require-class", CLASS)
        self.assertEqual(rc, 1)
        self.assertIn(CLASS, err)

    def test_required_class_that_is_fully_skipped_fails(self) -> None:
        self.write(CLASS, suite_xml(CLASS, 3, skipped=3))
        rc, _, _ = self.run_main("--require-class", CLASS)
        self.assertEqual(rc, 1)
