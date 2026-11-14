#!/usr/bin/env python3
"""Build the body of the issue that reports a failed release run.

The issue names the Firefox version, the failing job and step, the patch that did not apply (when there is
one), an excerpt of the error and the run URL. Subcommands (used by report-failure.sh):
  failed-ids --jobs JOBS.json            print the ids of the failed jobs, one per line
  body --jobs JOBS.json --logs DIR --firefox V --run-url URL --out FILE
  find-issue --title T < issues.json     print the number of the open issue with exactly that title
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

EXCERPT_LIMIT = 6000
EXCERPT_WINDOW = 40

_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PATCH_RE = re.compile(r"patch (\S+\.patch) failed to apply")
_MARKER = "##[error]"


def issue_title(firefox: str) -> str:
    return f"Release run failed for Firefox {firefox or 'unknown'}"


def failed_jobs(jobs_payload: dict) -> list[dict]:
    return [job for job in jobs_payload.get("jobs", []) if job.get("conclusion") == "failure"]


def failed_step_names(job: dict) -> list[str]:
    return [step.get("name", "") for step in job.get("steps", []) if step.get("conclusion") == "failure"]


def _clean(line: str) -> str:
    return _ANSI_RE.sub("", _TIMESTAMP_RE.sub("", line)).replace(_MARKER, "")


def error_excerpt(log: str, window: int = EXCERPT_WINDOW) -> str:
    """The lines before the first error marker (the failing step's own output), or the log tail."""
    raw = log.splitlines()
    index = next((i for i, line in enumerate(raw) if _MARKER in line), None)
    lines = [_clean(line) for line in raw]
    chunk = lines[-window:] if index is None else lines[max(0, index - window) : index + 1]
    excerpt = "\n".join(chunk).strip("\n")
    if len(excerpt) > EXCERPT_LIMIT:
        excerpt = "...\n" + excerpt[-EXCERPT_LIMIT:]
    return excerpt


def failing_patch(log: str) -> Optional[str]:
    m = _PATCH_RE.search(log)
    return m.group(1) if m else None


def build_report(jobs_payload: dict, logs: dict[int, str], *, firefox: str, run_url: str) -> str:
    fx = firefox or "unknown"
    failed = failed_jobs(jobs_payload)
    lines = [
        f"A release run for Firefox {fx} failed. No GitHub Release was created.",
        "",
        f"- Firefox version: {fx}",
        f"- Run: {run_url}",
    ]
    if not failed:
        lines += ["", "No failed job was found in the run; open the run for the details."]
        return "\n".join(lines) + "\n"

    patch = next((p for p in (failing_patch(logs.get(job["id"], "")) for job in failed) if p), None)
    for job in failed:
        steps = failed_step_names(job)
        step_text = ", ".join(steps) if steps else "(job failed before its steps)"
        lines += [f"- Failing job: {job.get('name', job['id'])}", f"- Failing step: {step_text}"]
    if patch:
        lines.append(f"- Failing patch: {patch}")
    lines += ["", "### Error excerpt", ""]
    for job in failed:
        steps = failed_step_names(job)
        lines += [f"Job `{job.get('name', job['id'])}`, step `{', '.join(steps) or 'none'}`:", "", "```text"]
        lines.append(error_excerpt(logs.get(job["id"], "(no log was available)")))
        lines += ["```", ""]
    return "\n".join(lines) + "\n"


def find_issue(issues: list[dict], title: str) -> Optional[int]:
    for issue in issues:
        if issue.get("title") == title:
            return int(issue["number"])
    return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_ids = sub.add_parser("failed-ids")
    p_ids.add_argument("--jobs", type=Path, required=True)

    p_body = sub.add_parser("body")
    p_body.add_argument("--jobs", type=Path, required=True)
    p_body.add_argument("--logs", type=Path, required=True)
    p_body.add_argument("--firefox", default="")
    p_body.add_argument("--run-url", required=True)
    p_body.add_argument("--out", type=Path, required=True)

    p_find = sub.add_parser("find-issue")
    p_find.add_argument("--title", required=True)

    args = parser.parse_args(argv)
    if args.command == "failed-ids":
        jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
        for job in failed_jobs(jobs):
            print(job["id"])
        return 0
    if args.command == "find-issue":
        number = find_issue(json.load(sys.stdin), args.title)
        if number is not None:
            print(number)
        return 0

    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    logs: dict[int, str] = {}
    for job in failed_jobs(jobs):
        log_file = args.logs / f"{job['id']}.log"
        if log_file.exists():
            logs[job["id"]] = log_file.read_text(encoding="utf-8", errors="replace")
    args.out.write_text(
        build_report(jobs, logs, firefox=args.firefox, run_url=args.run_url), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
