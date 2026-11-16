#!/usr/bin/env bash
set -uo pipefail

mkdir -p debug shots
adb logcat -v threadtime '*:I' >debug/logcat-live.txt 2>&1 &
logcat_pid=$!
adb track-devices >debug/devices-live.txt 2>&1 &
devices_pid=$!
(
  while true; do
    date -u
    free -m
    ps -eo pid,ppid,rss,comm --sort=-rss | head -n 12
    sleep 5
  done
) >debug/host-memory-live.txt 2>&1 &
memory_pid=$!
trap 'kill "$logcat_pid" "$devices_pid" "$memory_pid" 2>/dev/null || true' EXIT

python3 -m scripts.emulator.diagnostic
result=$?
adb devices -l >debug/devices-final.txt 2>&1
timeout 10 adb shell dumpsys activity activities >debug/activities-final.txt 2>&1 || true
exit "$result"
