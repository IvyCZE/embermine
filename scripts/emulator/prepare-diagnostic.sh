#!/usr/bin/env bash
set -euo pipefail

mkdir -p debug
cp "$ANDROID_AVD_HOME/test.avd/config.ini" debug/avd-config.ini
python3 - <<'PY'
import os
import subprocess
from pathlib import Path

info = Path("apk/apk-info.txt")
if not info.exists():
    sdk = Path(os.environ["ANDROID_HOME"])
    aapt2 = sorted(sdk.glob("build-tools/*/aapt2"))[-1]
    apk = next(Path("apk").glob("*-x86_64.apk"))
    badging = subprocess.check_output([str(aapt2), "dump", "badging", str(apk)], text=True)
    info.write_text(f"=== {apk.name} ({apk.stat().st_size} bytes)\n{badging}")
PY
