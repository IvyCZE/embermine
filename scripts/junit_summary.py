#!/usr/bin/env python3
"""Summarise JUnit XML results and fail unless tests really ran.

A green Gradle run with a test filter that matched nothing must not count as passing tests.
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


class SuiteResult:
    def __init__(self, name: str, tests: int, failures: int, errors: int, skipped: int) -> None:
        self.name = name
        self.tests = tests
        self.failures = failures
        self.errors = errors
        self.skipped = skipped


def read_suites(results_dir: Path) -> list[SuiteResult]:
    suites = []
    for xml_file in sorted(results_dir.rglob("TEST-*.xml")):
        root = ET.parse(xml_file).getroot()
        for suite in [root] if root.tag == "testsuite" else root.iter("testsuite"):
            suites.append(
                SuiteResult(
                    suite.get("name", xml_file.stem),
                    int(suite.get("tests", 0)),
                    int(suite.get("failures", 0)),
                    int(suite.get("errors", 0)),
                    int(suite.get("skipped", 0)),
                )
            )
    return suites


def check(suites: list[SuiteResult], required: list[str]) -> list[str]:
    problems = []
    if sum(s.tests for s in suites) == 0:
        problems.append("no tests were executed")
    bad = [s.name for s in suites if s.failures or s.errors]
    if bad:
        problems.append(f"failing suites: {', '.join(bad)}")
    for name in required:
        executed = sum(s.tests - s.skipped for s in suites if s.name == name)
        if executed == 0:
            problems.append(f"required test class {name} did not execute any test")
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--require-class", action="append", default=[], help="fully qualified test class")
    args = parser.parse_args(argv)

    suites = read_suites(args.results_dir)
    tests = sum(s.tests for s in suites)
    failures = sum(s.failures for s in suites)
    errors = sum(s.errors for s in suites)
    skipped = sum(s.skipped for s in suites)
    for s in suites:
        print(f"  {s.name}: {s.tests} tests, {s.failures} failures, {s.errors} errors, {s.skipped} skipped")
    print(f"Unit tests executed: {tests} (failures: {failures}, errors: {errors}, skipped: {skipped})")
    problems = check(suites, args.require_class)
    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
