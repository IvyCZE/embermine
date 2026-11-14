"""Release notes for a GitHub Release: base Firefox version, Mozilla's release notes, Embermine changes.

The Embermine changes come from the patch series itself: each patch's first commit-message paragraph.
A rebuild says that it rebuilds the same Firefox version.
  usage: python3 -m scripts.release.notes --patch-dir patches --build-info dist/build-info.json \
           --embermine-version 159.0 --out release-notes.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

from scripts.release import naming
from scripts import version as ver

FIREFOX_RELEASE_NOTES_URL = "https://www.firefox.com/en-US/firefox/android/{version}/releasenotes/"


class NotesError(RuntimeError):
    pass


def mozilla_release_notes_url(firefox_version: str) -> str:
    """The en-US path answers 200 directly; the bare mozilla.org path only redirects to it."""
    return FIREFOX_RELEASE_NOTES_URL.format(version=firefox_version)


_DIFF_RE = re.compile(r"^diff --git a/(\S+) b/")


def patch_description_from_text(name: str, text: str) -> tuple[str, str]:
    """First paragraph of the commit message of a format-patch file, joined onto one line.

    A patch without a commit message (patch 0008 has none) is described by the files it changes.
    """
    lines = text.splitlines()
    subject = next((i for i, line in enumerate(lines) if line.startswith("Subject:")), None)
    if subject is None:
        raise NotesError(f"{name} has no Subject header")
    i = subject + 1
    while i < len(lines) and lines[i].startswith((" ", "\t")):
        i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    paragraph: list[str] = []
    while i < len(lines):
        line = lines[i].strip()
        if not line or line == "---" or line.startswith(("Co-authored-by:", "diff --git")):
            break
        paragraph.append(line)
        i += 1
    if paragraph:
        return name, " ".join(paragraph)

    files: list[str] = []
    for line in lines:
        m = _DIFF_RE.match(line)
        if m and Path(m.group(1)).name not in files:
            files.append(Path(m.group(1)).name)
    if not files:
        raise NotesError(f"{name} has neither a commit message nor a diff to describe")
    shown = ", ".join(files[:5]) + (", ..." if len(files) > 5 else "")
    plural = "s" if len(files) != 1 else ""
    return name, f"Changes {len(files)} file{plural}: {shown}."


def read_changes(patch_dir: Path) -> list[tuple[str, str]]:
    return [
        patch_description_from_text(path.name, path.read_text(encoding="utf-8"))
        for path in sorted(patch_dir.glob("*.patch"))
    ]


def render_notes(
    *,
    firefox_version: str,
    embermine_version: str,
    tag: str,
    sha: str,
    buildid: str,
    rebuild: Optional[int],
    changes: list[tuple[str, str]],
) -> str:
    if not changes:
        raise NotesError("release notes need at least one Embermine change")
    ver.parse_firefox_version(firefox_version)
    release_tag = naming.release_tag(embermine_version)
    lines = [
        f"# {naming.release_title(embermine_version)}",
        "",
        f"Based on Firefox {firefox_version} for Android. Mozilla tag `{tag}`, commit `{sha[:12]}`, "
        f"GeckoView `{firefox_version}.{buildid}`.",
        "",
        f"Mozilla release notes for Firefox {firefox_version}: {mozilla_release_notes_url(firefox_version)}",
        "",
    ]
    if rebuild is not None:
        lines += [
            f"This is rebuild `-r{rebuild}` of Firefox {firefox_version}. It uses the same Firefox source and the "
            "same Embermine patches; only the build changed, so the Firefox version stays the same.",
            "",
        ]
    lines += ["## Embermine changes", ""]
    lines += [f"- **{name.removesuffix('.patch')}**: {text}" for name, text in changes]
    lines += ["", "## Files", ""]
    lines += [f"- `{apk}`" for apk in naming.apk_names(embermine_version)]
    lines += [
        "",
        f"Release tag `{release_tag}`. arm64-v8a suits most phones; x86_64 is for emulators and x86 devices.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--patch-dir", type=Path, required=True)
    parser.add_argument("--build-info", type=Path, required=True)
    parser.add_argument("--embermine-version", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        info = json.loads(args.build_info.read_text(encoding="utf-8"))
        text = render_notes(
            firefox_version=info["version"],
            embermine_version=args.embermine_version,
            tag=info["tag"],
            sha=info["sha"],
            buildid=info["buildid"],
            rebuild=rebuild_number(args.embermine_version),
            changes=read_changes(args.patch_dir),
        )
    except (NotesError, ver.VersionError, KeyError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


def rebuild_number(embermine_version: str) -> Optional[int]:
    """N of a -rN version, None for a base release."""
    _, kind, number = ver.parse_embermine_version(embermine_version)
    return number if kind == "rebuild" else None


if __name__ == "__main__":
    sys.exit(main())
