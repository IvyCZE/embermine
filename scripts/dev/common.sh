#!/usr/bin/env bash
# Shared settings for the local patch tooling. Source it; do not execute it.

EMBERMINE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EMBERMINE_WORK="${EMBERMINE_WORK:-/home/ivy/projects/embermine-work}"
FIREFOX_BASE="${FIREFOX_BASE:-$EMBERMINE_WORK/firefox-159.0}"
FIREFOX_WT_ROOT="${FIREFOX_WT_ROOT:-$EMBERMINE_WORK/wt}"

firefox_version() {
  tr -d '[:space:]' <"$EMBERMINE_REPO_ROOT/firefox-version.txt"
}

firefox_tag() {
  local v
  v="$(firefox_version)"
  echo "FIREFOX_${v//./_}_RELEASE"
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_firefox_base() {
  [ -e "$FIREFOX_BASE/.git" ] || die "Firefox base checkout not found at $FIREFOX_BASE"
  git -C "$FIREFOX_BASE" rev-parse --verify --quiet "$(firefox_tag)^{commit}" >/dev/null ||
    die "tag $(firefox_tag) not found in $FIREFOX_BASE"
}

# git am needs a committer identity. Locally the owner's global identity must be used
# (run with HOME=/home/ivy); only a GitHub runner gets a throwaway one.
git_am_identity_args() {
  if [ -z "$(git config user.email || true)" ] && [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    echo "-c" "user.name=embermine-ci" "-c" "user.email=ci@embermine.invalid"
  fi
}

list_patches() {
  local dir="${1:-$EMBERMINE_REPO_ROOT/patches}"
  local f
  for f in "$dir"/*.patch; do
    [ -e "$f" ] && echo "$f"
  done
  return 0
}
