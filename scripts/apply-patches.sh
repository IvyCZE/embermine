#!/usr/bin/env bash
# Apply patches/*.patch to a source tree in order with git am. The first failure stops the run,
# names the failing patch and leaves the tree without a half-applied patch.
#   usage: scripts/apply-patches.sh <tree> [--list FILE] [--patch-dir DIR]
# --list writes the file names of the applied patches, one per line, in application order.
set -euo pipefail
# shellcheck source=scripts/dev/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/dev/common.sh"

[ $# -ge 1 ] || die "usage: $0 <tree> [--list FILE] [--patch-dir DIR]"
tree="$1"
shift
list=""
patch_dir="$EMBERMINE_REPO_ROOT/patches"
while [ $# -gt 0 ]; do
  case "$1" in
    --list) list="${2:?--list needs a file}"; shift 2 ;;
    --patch-dir) patch_dir="${2:?--patch-dir needs a directory}"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -e "$tree/.git" ] || die "$tree is not a git checkout"
mapfile -t patches < <(list_patches "$patch_dir")
[ "${#patches[@]}" -gt 0 ] || die "no patches found in $patch_dir"
[ -z "$list" ] || : >"$list"

log="$(mktemp)"
trap 'rm -f "$log"' EXIT

for p in "${patches[@]}"; do
  name="$(basename "$p")"
  echo "applying $name: $(grep -m1 '^Subject:' "$p" | sed 's/^Subject: \[PATCH\] //')"
  # shellcheck disable=SC2046
  if ! git -C "$tree" $(git_am_identity_args) am --3way "$p" >"$log" 2>&1; then
    cat "$log" >&2
    # shellcheck disable=SC2046
    git -C "$tree" $(git_am_identity_args) am --abort >/dev/null 2>&1 || true
    die "patch $name failed to apply; stopping"
  fi
  [ -z "$list" ] || echo "$name" >>"$list"
done
echo "applied ${#patches[@]} patch(es) in order"
