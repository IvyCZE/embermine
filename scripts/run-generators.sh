#!/usr/bin/env bash
# Run every scripts/generate/*.py against a patched source tree, in name order.
# Each generator takes --tree <dir> and fails loudly when its anchors are missing.
#   usage: scripts/run-generators.sh <tree>
set -euo pipefail
# shellcheck source=scripts/dev/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/dev/common.sh"

[ $# -eq 1 ] || die "usage: $0 <tree>"
tree="$(cd "$1" && pwd)"

shopt -s nullglob
generators=("$EMBERMINE_REPO_ROOT"/scripts/generate/*.py)
if [ "${#generators[@]}" -eq 0 ]; then
  echo "no generators present"
  exit 0
fi
for g in "${generators[@]}"; do
  [ "$(basename "$g")" = "__init__.py" ] && continue
  echo "running generator $(basename "$g")"
  python3 "$g" --tree "$tree"
done
