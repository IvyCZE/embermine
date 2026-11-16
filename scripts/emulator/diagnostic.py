"""Compare launch, search and browsing without Embermine-specific settings flows."""
from __future__ import annotations

from scripts.emulator import run


def main() -> int:
    original_flows = run.flow_list
    run.flow_list = lambda variant, accent: [
        flow for flow in original_flows(variant, accent) if flow.name in {"homepage", "search", "pages"}
    ]
    run.launcher.themed_icon_capture = lambda *args: None
    run.launcher.plain_icon_capture = lambda *args: None
    return run.main([
        "--variant", "light", "--accent", "on",
        "--apk-dir", "apk", "--out", "shots", "--debug", "debug",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
