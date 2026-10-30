#!/usr/bin/env bash
# Apply the whole patch series, in order, to a fresh worktree of the pinned Firefox tag.
# The temporary worktree is always removed again.
set -euo pipefail
# shellcheck source=scripts/dev/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/dev/common.sh"

require_firefox_base
tag="$(firefox_tag)"

mapfile -t patches < <(list_patches)
[ "${#patches[@]}" -gt 0 ] || die "no patches found in $EMBERMINE_REPO_ROOT/patches"

expected=0
for p in "${patches[@]}"; do
  name="$(basename "$p")"
  [[ "$name" =~ ^([0-9]{4})-[a-z0-9]+(-[a-z0-9]+)*\.patch$ ]] || die "bad patch file name: $name"
  [ "$((10#${BASH_REMATCH[1]}))" -eq "$expected" ] ||
    die "patch numbering broken at $name (expected $(printf '%04d' "$expected"))"
  grep -q '^Subject: \[PATCH\] Embermine: ' "$p" || die "$name: subject must start with 'Embermine: '"
  expected=$((expected + 1))
done

tmp="$(mktemp -d)"
wt="$tmp/check"
cleanup() {
  git -C "$FIREFOX_BASE" worktree remove --force "$wt" >/dev/null 2>&1 || true
  rm -rf "$tmp"
  git -C "$FIREFOX_BASE" worktree prune
}
trap cleanup EXIT

git -C "$FIREFOX_BASE" worktree add --quiet --detach "$wt" "$tag" >/dev/null 2>&1

"$EMBERMINE_REPO_ROOT/scripts/apply-patches.sh" "$wt" || die "the series does not apply cleanly to $tag"
echo "all ${#patches[@]} patch(es) apply cleanly to $tag"
