"""Scan a logcat dump for crashes and ANRs and attribute them to a package."""
from __future__ import annotations

import re
from dataclasses import dataclass

_FATAL = re.compile(r"FATAL EXCEPTION")
_PROCESS = re.compile(r"Process:\s*([\w.:]+),\s*PID:\s*(\d+)")
_ANR = re.compile(r"ANR in ([\w.:]+)")
_NATIVE = re.compile(r">>>\s*([\w.:]+)\s*<<<")
_LOG_LINE = re.compile(r"^\S+\s+\S+\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+(\S+)\s*:")


@dataclass
class Finding:
    kind: str  # FATAL EXCEPTION, ANR or NATIVE CRASH
    process: str
    lines: list[str]


def scan(logcat: str) -> list[Finding]:
    lines = logcat.splitlines()
    findings: list[Finding] = []
    for i, line in enumerate(lines):
        if _FATAL.search(line):
            block = _block(lines, i)
            process = next((m[1] for m in map(_PROCESS.search, block) if m), "unknown")
            findings.append(Finding("FATAL EXCEPTION", process, block))
        elif match := _ANR.search(line):
            findings.append(Finding("ANR", match[1].rstrip(":"), _block(lines, i, 12)))
        elif "Fatal signal" in line:
            nearby = lines[i : i + 40]
            tombstone = next((m[1] for m in map(_NATIVE.search, nearby) if m), "unknown")
            findings.append(Finding("NATIVE CRASH", tombstone, [line]))
    return findings


def _block(lines: list[str], start: int, limit: int = 30) -> list[str]:
    """The log lines of one crash: same pid and tag as the starting line, up to `limit` lines."""
    head = _LOG_LINE.match(lines[start])
    block = [lines[start]]
    for line in lines[start + 1 : start + 1 + limit]:
        parsed = _LOG_LINE.match(line)
        if head and parsed and (parsed[1], parsed[4]) != (head[1], head[4]):
            break
        block.append(line)
    return block


def matches_package(process: str, package: str) -> bool:
    return process == package or process.startswith(package + ":")


def report(logcat: str, package: str) -> tuple[str, int]:
    """Text of logcat-crash.txt and the number of findings attributed to `package`."""
    findings = scan(logcat)
    ours = [f for f in findings if matches_package(f.process, package)]
    out = [
        f"# logcat crash scan for package {package}",
        f"# FATAL EXCEPTION / ANR / native crash findings attributed to {package}: {len(ours)}",
        f"# findings for other processes (not attributed): {len(findings) - len(ours)}",
        f"# logcat lines scanned: {len(logcat.splitlines())}",
        "",
    ]
    if not findings:
        out.append("No FATAL EXCEPTION, ANR or native crash found in the log.")
    for finding in findings:
        owner = "THIS APP" if matches_package(finding.process, package) else "other process"
        out.append(f"## {finding.kind} in {finding.process} ({owner})")
        out.extend(finding.lines)
        out.append("")
    return "\n".join(out) + "\n", len(ours)
