"""adb driver: UI dumps, taps by selector, swipes, screenshots and system dialog cleanup."""
from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from pathlib import Path

from scripts.emulator import uidump
from scripts.emulator.uidump import Node, Selector

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# A real 1080x2400 capture compresses to far more than this; a black or blank frame does not.
MIN_PNG_BYTES = 30_000


class StepError(RuntimeError):
    """A scripted step failed (element not found, bad screenshot). Captures turn this into MISSING."""


class Adb:
    """Thin subprocess wrapper so tests can replace it with a fake."""

    def __init__(self, serial: str | None = None) -> None:
        self.prefix = ["adb", *(["-s", serial] if serial else [])]

    def run(self, *args: str, timeout: float = 60) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run([*self.prefix, *args], capture_output=True, timeout=timeout, check=False)

    def shell(self, command: str, timeout: float = 60) -> str:
        # adb joins its arguments into a single remote command line, so quoting is the caller's job.
        proc = self.run("shell", command, timeout=timeout)
        return proc.stdout.decode("utf-8", errors="replace").replace("\r", "")


# Dialogs that Android or other apps can put over the app under test: (title pattern, buttons in preference order).
SYSTEM_DIALOGS: Sequence[tuple[str, Sequence[str]]] = (
    (r".*(isn.t responding|keeps stopping|has stopped|not responding).*", ("Wait", "Close app", "OK")),
    (r".*(Set .* as your default browser|Choose default browser).*", ("Cancel", "Not now", "No thanks")),
    (r".*(Allow .* to send you notifications|send you notifications).*", ("Don.t allow", "Allow")),
    (r".*Turn on .*(Wi-?Fi|location).*", ("No thanks", "Cancel")),
)


class Device:
    def __init__(
        self,
        adb: Adb,
        *,
        dump_dir: Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = print,
    ) -> None:
        self.adb = adb
        self.dump_dir = dump_dir
        self.sleep = sleep
        self.clock = clock
        self.log = log
        self._dump_counter = 0

    # ---- UI hierarchy -------------------------------------------------------------------------

    def dump(self, label: str = "", retries: int = 5, save: bool = False) -> list[Node]:
        """Current hierarchy. uiautomator fails with "could not get idle state" while the screen animates."""
        last_error = "no output"
        for attempt in range(retries):
            raw = self.adb.run("exec-out", "uiautomator", "dump", "/dev/tty", timeout=60).stdout.decode(
                "utf-8", errors="replace"
            )
            try:
                nodes = uidump.parse(raw)
            except (ValueError, ET.ParseError) as exc:
                last_error = f"{type(exc).__name__}: {exc}; output starts {raw[:120]!r}"
                self.sleep(1.0 + attempt)
                continue
            if save:
                self._save_dump(label, raw)
            return nodes
        raise StepError(f"uiautomator dump failed {retries} times ({last_error})")

    def _save_dump(self, label: str, raw: str) -> None:
        if self.dump_dir is None:
            return
        self.dump_dir.mkdir(parents=True, exist_ok=True)
        self._dump_counter += 1
        slug = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-") or "dump"
        (self.dump_dir / f"{self._dump_counter:03d}-{slug}.xml").write_text(uidump.extract_xml(raw), encoding="utf-8")

    def wait_for(self, *selectors: Selector, timeout: float = 10, label: str = "") -> Node | None:
        """Poll until one of the selectors matches (earlier selectors win); None on timeout."""
        deadline = self.clock() + timeout
        while True:
            try:
                node = uidump.find_first(self.dump(label or str(selectors[0])), *selectors)
            except StepError:
                node = None
            if node is not None:
                return node
            if self.clock() >= deadline:
                return None
            self.sleep(1.0)

    def visible(self, *selectors: Selector) -> bool:
        try:
            return uidump.find_first(self.dump("visible"), *selectors) is not None
        except StepError:
            return False

    # ---- input --------------------------------------------------------------------------------

    def tap_xy(self, x: int, y: int) -> None:
        self.adb.shell(f"input tap {x} {y}")

    def tap_node(self, node: Node) -> None:
        x, y = node.center
        self.log(f"tap {node.label or node.id_name or node.cls!r} at {x},{y}")
        self.tap_xy(x, y)

    def tap(self, *selectors: Selector, timeout: float = 10, settle: float = 1.0) -> Node:
        node = self.wait_for(*selectors, timeout=timeout, label="tap")
        if node is None:
            raise StepError("not found: " + " | ".join(str(s) for s in selectors))
        self.tap_node(node)
        self.sleep(settle)
        return node

    def try_tap(self, *selectors: Selector, timeout: float = 3, settle: float = 1.0) -> bool:
        try:
            self.tap(*selectors, timeout=timeout, settle=settle)
        except StepError:
            return False
        return True

    def type_text(self, text: str) -> None:
        self.adb.shell("input text " + re.sub(r"[^A-Za-z0-9._-]", "", text))

    def key(self, name: str) -> None:
        self.adb.shell(f"input keyevent {name}")

    def back(self, settle: float = 1.0) -> None:
        self.key("KEYCODE_BACK")
        self.sleep(settle)

    def home(self, settle: float = 1.5) -> None:
        self.key("KEYCODE_HOME")
        self.sleep(settle)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.adb.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def screen_size(self) -> tuple[int, int]:
        lines = self.adb.shell("wm size").strip().splitlines()
        match = re.search(r"(\d+)x(\d+)", lines[-1]) if lines else None
        if match is None:
            raise StepError("cannot read the screen size from `wm size`")
        return int(match[1]), int(match[2])

    def scroll_down(self, steps: int = 1) -> None:
        w, h = self.screen_size()
        for _ in range(steps):
            self.swipe(w // 2, int(h * 0.75), w // 2, int(h * 0.30), 400)
            self.sleep(0.6)

    def scroll_top(self, steps: int = 4) -> None:
        w, h = self.screen_size()
        for _ in range(steps):
            self.swipe(w // 2, int(h * 0.30), w // 2, int(h * 0.80), 250)
            self.sleep(0.4)

    def scroll_to(self, *selectors: Selector, max_swipes: int = 8) -> Node:
        """Swipe up until one of the selectors is on screen, then return it."""
        for attempt in range(max_swipes + 1):
            node = uidump.find_first(self.dump("scroll"), *selectors)
            if node is not None:
                return node
            if attempt < max_swipes:
                self.scroll_down()
        raise StepError("not found after scrolling: " + " | ".join(str(s) for s in selectors))

    # ---- screenshots --------------------------------------------------------------------------

    def screenshot(self, path: Path) -> None:
        proc = self.adb.run("exec-out", "screencap", "-p", timeout=60)
        data = proc.stdout
        if not data.startswith(PNG_MAGIC):
            raise StepError(f"screencap did not return a PNG ({len(data)} bytes)")
        if len(data) < MIN_PNG_BYTES:
            raise StepError(f"screenshot is only {len(data)} bytes, the screen looks blank")
        path.write_bytes(data)

    # ---- dialogs ------------------------------------------------------------------------------

    def sweep_dialogs(self, rounds: int = 3) -> list[str]:
        """Dismiss ANR, crash and permission dialogs that cover the app. Returns what was dismissed."""
        dismissed: list[str] = []
        for _ in range(rounds):
            try:
                nodes = self.dump("sweep")
            except StepError:
                break
            hit = self._find_dialog(nodes)
            if hit is None:
                break
            title, button = hit
            dismissed.append(f"{title.strip()[:60]} -> {button.label}")
            self.log(f"dialog sweep: {dismissed[-1]}")
            self.tap_node(button)
            self.sleep(1.5)
        return dismissed

    @staticmethod
    def _find_dialog(nodes: list[Node]) -> tuple[str, Node] | None:
        for title_pattern, buttons in SYSTEM_DIALOGS:
            title_re = re.compile(title_pattern, re.IGNORECASE | re.DOTALL)
            title = next((n for n in nodes if n.text and title_re.fullmatch(n.text.strip())), None)
            if title is None:
                continue
            for label in buttons:
                sel = Selector(text=label, clickable=True)
                button = uidump.find_first(nodes, sel, Selector(text=label))
                if button is not None:
                    return title.text, button
        return None
