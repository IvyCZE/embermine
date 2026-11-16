"""Short device comparison using the same setup and first four flows as CI."""
from __future__ import annotations

from scripts.emulator import run


def main() -> int:
    original_flows = run.flow_list
    run.flow_list = lambda variant, accent: original_flows(variant, accent)[:4]
    run.launcher.themed_icon_capture = lambda *args: None
    run.launcher.plain_icon_capture = lambda *args: None
    return run.main([
        "--variant", "light", "--accent", "on",
        "--apk-dir", "apk", "--out", "shots", "--debug", "debug",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
