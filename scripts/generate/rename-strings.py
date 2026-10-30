#!/usr/bin/env python3
"""Rename the app in Fenix's English strings: standalone "Firefox" -> "Embermine".

Only mobile/android/fenix/app/src/main/res/values/strings.xml is touched; the
localized values-*/strings.xml files are left alone. Strings that name a Mozilla
product or service (Sync and Firefox on other devices, Firefox Suggest, Firefox
Labs, Firefox Terms of Use, Firefox/Mozilla account, "based on Firefox") keep
"Firefox". Every replaced string name is printed.

    usage: rename-strings.py --tree <patched Firefox tree>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

STRINGS_REL = "mobile/android/fenix/app/src/main/res/values/strings.xml"
OLD, NEW = "Firefox", "Embermine"

KEEP_NAME_RE = re.compile(
    r"(^|_)(sync|synced|fxa|sign_in)(_|$)"
    r"|^firefox_(suggest|labs)"
    r"|_fx_suggest(_|$)"
)

KEEP_PHRASES = (
    "Firefox Suggest",
    "Firefox Labs",
    "Firefox Terms of Use",
    "Firefox account",
    "Firefox Account",
    "based on Firefox",
    "Based on Firefox",
    "Firefox on at least one other device",
    "Firefox on another device",
    "Firefox on your other devices",
    "Firefox on other devices",
    "other Firefox devices",
    "Firefox between devices",
    "open Firefox and go to",
)

ELEMENT_RE = re.compile(
    r'(<(string|plurals|string-array)\b[^>]*?\bname="(?P<name>[^"]+)"[^>]*>)(?P<body>.*?)(</\2>)',
    re.DOTALL,
)
COMMENT_RE = re.compile(r"(<!--.*?-->)", re.DOTALL)
WORD_RE = re.compile(r"\bFirefox\b")
ARTICLE_RE = re.compile(r"\b([Aa]) Firefox\b")


def rename_text(name: str, text: str) -> str:
    """Return text with the app name replaced, or unchanged for kept strings."""
    if KEEP_NAME_RE.search(name):
        return text
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\0{len(protected) - 1}\0"

    for phrase in KEEP_PHRASES:
        text = re.sub(re.escape(phrase), protect, text)
    text = ARTICLE_RE.sub(lambda m: f"{m.group(1)}n {NEW}", text)
    text = WORD_RE.sub(NEW, text)
    return re.sub(r"\0(\d+)\0", lambda m: protected[int(m.group(1))], text)


def rename_strings(xml: str) -> tuple[str, list[str]]:
    """Rename the app in a strings.xml document. Returns (new xml, replaced names)."""
    replaced: list[str] = []

    def element(match: re.Match[str]) -> str:
        name = match.group("name")
        body = match.group("body")
        new_body = rename_text(name, body)
        if new_body == body:
            return match.group(0)
        replaced.append(name)
        return match.group(1) + new_body + match.group(5)

    parts = COMMENT_RE.split(xml)
    for i in range(0, len(parts), 2):
        parts[i] = ELEMENT_RE.sub(element, parts[i])
    return "".join(parts), replaced


def run(tree: Path) -> list[str]:
    path = tree / STRINGS_REL
    if not path.is_file():
        raise SystemExit(f"error: {path} not found")
    new_xml, replaced = rename_strings(path.read_text(encoding="utf-8"))
    if not replaced:
        raise SystemExit(f"error: no '{OLD}' strings found to rename in {path}")
    path.write_text(new_xml, encoding="utf-8")
    for name in replaced:
        print(f"renamed {name}")
    print(f"rename-strings: replaced {OLD} with {NEW} in {len(replaced)} strings")
    return replaced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", required=True, type=Path, help="patched Firefox source tree")
    args = parser.parse_args(argv)
    run(args.tree)
    return 0


if __name__ == "__main__":
    sys.exit(main())
