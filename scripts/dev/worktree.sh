#!/usr/bin/env bash
# Create a Firefox worktree for a feature with the current patch series applied as commits.
#   usage: scripts/dev/worktree.sh <feature-id>
# Result: $FIREFOX_WT_ROOT/<feature-id> on branch em/<feature-id>, based on the pinned tag.
set -euo pipefail
# shellcheck source=scripts/dev/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

[ $# -eq 1 ] || die "usage: $0 <feature-id>"
id="$1"
[[ "$id" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "invalid feature id: $id"

require_firefox_base
tag="$(firefox_tag)"
wt="$FIREFOX_WT_ROOT/$id"
[ ! -e "$wt" ] || die "$wt already exists"

mkdir -p "$FIREFOX_WT_ROOT"
git -C "$FIREFOX_BASE" worktree add --quiet -b "em/$id" "$wt" "$tag"

mapfile -t patches < <(list_patches)
if [ "${#patches[@]}" -gt 0 ]; then
  # shellcheck disable=SC2046
  git -C "$wt" $(git_am_identity_args) am --3way "${patches[@]}"
fi
echo "worktree ready: $wt (branch em/$id, ${#patches[@]} patches applied on $tag)"
