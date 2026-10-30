#!/usr/bin/env bash
# Export the commits TAG..HEAD of a Firefox worktree as the patch series.
#   usage: scripts/dev/export-patches.sh <feature-id> [output-dir]
# output-dir defaults to patches/ of this repo checkout; stale *.patch files there are removed.
# Each commit subject must be "Embermine: NNNN-<name>"; numbering must be contiguous from 0000.
set -euo pipefail
# shellcheck source=scripts/dev/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

[ $# -ge 1 ] && [ $# -le 2 ] || die "usage: $0 <feature-id> [output-dir]"
id="$1"
out="${2:-$EMBERMINE_REPO_ROOT/patches}"
wt="$FIREFOX_WT_ROOT/$id"

[ -e "$wt/.git" ] || die "no worktree at $wt (run scripts/dev/worktree.sh $id)"
[ -z "$(git -C "$wt" status --porcelain --untracked-files=no)" ] || die "uncommitted changes in $wt; commit or amend first"
tag="$(firefox_tag)"
git -C "$wt" merge-base --is-ancestor "$tag" HEAD || die "HEAD of $wt is not based on $tag"

staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT

expected=0
count=0
while read -r sha; do
  subject="$(git -C "$wt" log -1 --format=%s "$sha")"
  [[ "$subject" =~ ^Embermine:\ ([0-9]{4})-([a-z0-9]+(-[a-z0-9]+)*)$ ]] ||
    die "bad subject '$subject' (expected 'Embermine: NNNN-<name>')"
  num="${BASH_REMATCH[1]}"
  [ "$((10#$num))" -eq "$expected" ] || die "patch number $num out of sequence (expected $(printf '%04d' "$expected"))"
  # --zero-commit and --full-index keep output independent of the commit sha and repo size
  git -C "$wt" format-patch -1 --stdout --binary --no-stat --no-signature --zero-commit --full-index \
    --subject-prefix=PATCH "$sha" >"$staging/${num}-${BASH_REMATCH[2]}.patch"
  expected=$((expected + 1))
  count=$((count + 1))
done < <(git -C "$wt" rev-list --reverse "$tag..HEAD")

[ "$count" -gt 0 ] || die "no commits between $tag and HEAD in $wt"

mkdir -p "$out"
rm -f "$out"/*.patch
cp "$staging"/*.patch "$out"/
echo "exported $count patch(es) to $out"
