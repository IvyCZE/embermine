"""Parse `uiautomator dump` XML and find nodes by resource-id, content-desc or text."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
_XML_START = re.compile(r"<\?xml|<hierarchy")


@dataclass(frozen=True)
class Node:
    rid: str
    text: str
    desc: str
    cls: str
    package: str
    clickable: bool
    scrollable: bool
    checked: bool
    bounds: tuple[int, int, int, int]

    @property
    def id_name(self) -> str:
        """Resource id without the package part ("org.mozilla.firefox:id/toolbar" -> "toolbar")."""
        return self.rid.split("/", 1)[1] if "/" in self.rid else self.rid

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    @property
    def visible(self) -> bool:
        return self.width > 0 and self.height > 0

    @property
    def label(self) -> str:
        return self.text or self.desc


@dataclass(frozen=True)
class Selector:
    """All given criteria must match. `id` is compared with the resource id without package,
    `text` and `desc` are case-insensitive regular expressions that must match the whole value."""

    id: str | None = None
    text: str | None = None
    desc: str | None = None
    label: str | None = None  # text or content-desc
    cls: str | None = None
    package: str | None = None
    clickable: bool | None = None
    _compiled: dict[str, re.Pattern[str]] = field(default_factory=dict, compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        for name in ("text", "desc", "label"):
            pattern = getattr(self, name)
            if pattern is not None:
                self._compiled[name] = re.compile(pattern, re.IGNORECASE | re.DOTALL)

    def matches(self, node: Node) -> bool:
        if self.id is not None and node.id_name != self.id:
            return False
        if self.cls is not None and node.cls != self.cls:
            return False
        if self.package is not None and node.package != self.package:
            return False
        if self.clickable is not None and node.clickable != self.clickable:
            return False
        for name, value in (("text", node.text), ("desc", node.desc), ("label", node.label)):
            compiled = self._compiled.get(name)
            if compiled is not None and not compiled.fullmatch(value.strip()):
                return False
        return True

    def __str__(self) -> str:
        parts = [f"{k}={getattr(self, k)!r}" for k in ("id", "text", "desc", "label", "cls", "package") if getattr(self, k)]
        return "Selector(" + ", ".join(parts) + ")"


def by_id(name: str) -> Selector:
    return Selector(id=name)


def by_text(pattern: str) -> Selector:
    return Selector(text=pattern)


def by_desc(pattern: str) -> Selector:
    return Selector(desc=pattern)


def by_label(pattern: str) -> Selector:
    return Selector(label=pattern)


def extract_xml(raw: str) -> str:
    """The text printed by `uiautomator dump /dev/tty` has a trailing status line after the XML."""
    match = _XML_START.search(raw)
    if match is None:
        raise ValueError("no XML in uiautomator output")
    xml = raw[match.start() :]
    end = xml.rfind("</hierarchy>")
    if end == -1:
        raise ValueError("uiautomator output has no closing </hierarchy>")
    return xml[: end + len("</hierarchy>")]


def parse(raw: str) -> list[Node]:
    """All nodes of a dump in document order (parents before children)."""
    root = ET.fromstring(extract_xml(raw))
    nodes: list[Node] = []
    for element in root.iter("node"):
        bounds = _BOUNDS.fullmatch(element.get("bounds", ""))
        if bounds is None:
            continue
        nodes.append(
            Node(
                rid=element.get("resource-id", ""),
                text=element.get("text", ""),
                desc=element.get("content-desc", ""),
                cls=element.get("class", ""),
                package=element.get("package", ""),
                clickable=element.get("clickable") == "true",
                scrollable=element.get("scrollable") == "true",
                checked=element.get("checked") == "true",
                bounds=(int(bounds[1]), int(bounds[2]), int(bounds[3]), int(bounds[4])),
            )
        )
    return nodes


def find_all(nodes: list[Node], selector: Selector) -> list[Node]:
    return [n for n in nodes if n.visible and selector.matches(n)]


def find_first(nodes: list[Node], *selectors: Selector) -> Node | None:
    """First visible match, trying the selectors in the given order of preference."""
    for selector in selectors:
        matches = find_all(nodes, selector)
        if matches:
            return matches[0]
    return None


def screen_size(nodes: list[Node]) -> tuple[int, int]:
    """Width and height of the screen from the root node's bounds."""
    if not nodes:
        raise ValueError("empty hierarchy")
    return nodes[0].bounds[2], nodes[0].bounds[3]


def labels(nodes: list[Node]) -> list[str]:
    return [n.label for n in nodes if n.label.strip()]
