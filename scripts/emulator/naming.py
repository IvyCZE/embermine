"""Screenshot file names and the screens-index.md report."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SCREEN = re.compile(r"^(\d{2}-)?[a-z0-9]+(-[a-z0-9]+)*$")
THEMES = ("light", "dark", "legacy")  # "legacy" is the API 30 job, which has no light/dark pair


def capture_name(screen: str, *, theme: str, dynamic: bool = False, private: bool = False) -> str:
    """`<NN>-<screen>_dynamic-<on|off>_<light|dark|legacy>[_private].png`; `screen` already carries NN when it has one."""
    if not _SCREEN.match(screen):
        raise ValueError(f"invalid screen name: {screen!r}")
    if theme not in THEMES:
        raise ValueError(f"invalid theme: {theme!r}")
    suffix = "_private" if private else ""
    return f"{screen}_dynamic-{'on' if dynamic else 'off'}_{theme}{suffix}.png"


@dataclass
class Entry:
    screen: str
    combination: str
    file: str
    status: str  # OK or MISSING
    detail: str = ""


@dataclass
class ScreenIndex:
    """Collects the outcome of every capture and renders screens-index.md."""

    title: str
    header: list[str] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    reports: list[tuple[str, str]] = field(default_factory=list)

    def ok(self, screen: str, combination: str, file: str, detail: str = "") -> None:
        self.entries.append(Entry(screen, combination, file, "OK", detail))

    def missing(self, screen: str, combination: str, file: str, reason: str) -> None:
        self.entries.append(Entry(screen, combination, file, "MISSING", " ".join(reason.split())))

    def add_report(self, file: str, description: str) -> None:
        self.reports.append((file, description))

    def render(self) -> str:
        lines = [f"# {self.title}", ""]
        lines += self.header
        if self.header:
            lines.append("")
        ok = sum(1 for e in self.entries if e.status == "OK")
        lines += [f"Captures: {ok} OK, {len(self.entries) - ok} MISSING of {len(self.entries)} expected.", ""]
        lines += ["| screen | combination | file | status | reason / note |", "|---|---|---|---|---|"]
        for e in self.entries:
            lines.append(f"| {e.screen} | {e.combination} | {e.file} | {e.status} | {e.detail} |")
        if self.reports:
            lines += ["", "## Reports", "", "| file | content |", "|---|---|"]
            lines += [f"| {f} | {d} |" for f, d in self.reports]
        lines.append("")
        return "\n".join(lines)

    def write(self, path: Path) -> None:
        path.write_text(self.render(), encoding="utf-8")


def check_index_matches_files(index_text: str, directory: Path, deferred: frozenset[str] = frozenset()) -> list[str]:
    """Problems between an index and the files next to it: unlisted files, OK entries without a file.
    `deferred` names reports that a later step of the job writes."""
    listed: dict[str, str] = {}
    for line in index_text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[2].endswith((".png", ".txt", ".md")) and cells[3] in ("OK", "MISSING"):
            listed[cells[2]] = cells[3]
        elif len(cells) == 2 and cells[0].endswith(".txt"):
            listed[cells[0]] = "REPORT"
    problems = []
    on_disk = {p.name for p in directory.iterdir() if p.is_file()} - {"screens-index.md"}
    for name in sorted(on_disk - set(listed)):
        problems.append(f"not in index: {name}")
    for name, status in sorted(listed.items()):
        if status in ("OK", "REPORT") and name not in on_disk and name not in deferred:
            problems.append(f"{status} entry without file: {name}")
        if status == "MISSING" and name in on_disk:
            problems.append(f"MISSING entry has a file: {name}")
    return problems
