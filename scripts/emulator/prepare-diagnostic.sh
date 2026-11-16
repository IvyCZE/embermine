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

emulator_launcher="$(command -v emulator)"
mv "$emulator_launcher" "$emulator_launcher.original"
cat >"$emulator_launcher" <<'WRAPPER'
#!/usr/bin/env bash
set +e
record="$GITHUB_WORKSPACE/debug/emulator-$BASHPID"
printf '%q ' "$@" >"$record.args"
"${BASH_SOURCE[0]}.original" "$@" >"$record.console" 2>&1
result=$?
printf '%s\n' "$result" >"$record.exit"
exit "$result"
WRAPPER
chmod +x "$emulator_launcher"
