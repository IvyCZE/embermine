"""Fake adb and uiautomator XML builders for the emulator harness tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def node(text: str = "", desc: str = "", rid: str = "", bounds: str = "[0,0][100,100]", clickable: bool = False, package: str = "org.mozilla.firefox", cls: str = "android.view.View") -> str:
    def esc(v: str) -> str:
        return v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

    return (
        f'<node index="0" text="{esc(text)}" resource-id="{rid}" class="{cls}" package="{package}" '
        f'content-desc="{esc(desc)}" checkable="false" checked="false" clickable="{str(clickable).lower()}" '
        f'enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" '
        f'password="false" selected="false" bounds="{bounds}" />'
    )


def hierarchy(*nodes: str, size: str = "[0,0][1080,2400]") -> str:
    root = f'<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="android" bounds="{size}">'
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
        f'<hierarchy rotation="0">{root}{"".join(nodes)}</node></hierarchy>'
    )


def tty_output(xml: str) -> str:
    return xml + "UI hierchary dumped to: /dev/tty\n"


class FakeAdb:
    """Plays back queued uiautomator dumps and records the input commands."""

    prefix = ["adb"]

    def __init__(self, dumps: list[str] | None = None, shell_answers: dict[str, str] | None = None, png: bytes = b"") -> None:
        self.dumps = list(dumps or [])
        self.last_dump = ""
        self.shell_answers = shell_answers or {}
        self.commands: list[str] = []
        self.png = png

    def run(self, *args: str, timeout: float = 60) -> subprocess.CompletedProcess[bytes]:
        if args[:3] == ("exec-out", "uiautomator", "dump"):
            if self.dumps:
                self.last_dump = self.dumps.pop(0)
            return subprocess.CompletedProcess(args, 0, self.last_dump.encode(), b"")
        if args[:2] == ("exec-out", "screencap"):
            return subprocess.CompletedProcess(args, 0, self.png, b"")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    def shell(self, command: str, timeout: float = 60) -> str:
        self.commands.append(command)
        for needle, answer in self.shell_answers.items():
            if needle in command:
                return answer
        return ""
