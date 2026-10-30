#!/usr/bin/env bash
# actionlint on workflows, shellcheck on shell scripts, py_compile on Python scripts.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

tool() {
  command -v "$1" || { echo "error: $1 not found in PATH" >&2; exit 1; }
}

status=0

mapfile -t workflows < <(find .github/workflows -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) 2>/dev/null | sort)
if [ "${#workflows[@]}" -gt 0 ]; then
  echo "actionlint: ${#workflows[@]} workflow(s)"
  "$(tool actionlint)" "${workflows[@]}" || status=1
else
  echo "actionlint: no workflows"
fi

mapfile -t shells < <(find scripts -type f -name '*.sh' | sort)
if [ "${#shells[@]}" -gt 0 ]; then
  echo "shellcheck: ${#shells[@]} script(s)"
  "$(tool shellcheck)" -x "${shells[@]}" || status=1
fi

mapfile -t pys < <(find scripts -type f -name '*.py' | sort)
if [ "${#pys[@]}" -gt 0 ]; then
  echo "py_compile: ${#pys[@]} file(s)"
  PYTHONPYCACHEPREFIX="$(mktemp -d)"
  export PYTHONPYCACHEPREFIX
  python3 -m py_compile "${pys[@]}" || status=1
  rm -rf "$PYTHONPYCACHEPREFIX"
fi

if [ "$status" -eq 0 ]; then
  echo "lint clean"
fi
exit "$status"
