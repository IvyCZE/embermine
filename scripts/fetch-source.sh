#!/usr/bin/env bash
# Shallow-fetch one release tag of the Firefox source into a fresh directory and check it out.
#   usage: scripts/fetch-source.sh <tag> <expected-sha> <dest> [repo-url]
set -euo pipefail

[ $# -ge 3 ] && [ $# -le 4 ] || { echo "usage: $0 <tag> <expected-sha> <dest> [repo-url]" >&2; exit 2; }
tag="$1"
expected="$2"
dest="$3"
repo="${4:-https://github.com/mozilla-firefox/firefox}"

git init -q "$dest"
cd "$dest"
git remote add origin "$repo"
echo "+ git fetch --depth 1 origin refs/tags/$tag:refs/tags/$tag"
git fetch --quiet --depth 1 origin "refs/tags/$tag:refs/tags/$tag"
git -c advice.detachedHead=false checkout --quiet --detach "$tag"

head="$(git rev-parse 'HEAD^{commit}')"
echo "checked out $tag at $head"
if [ "$head" != "$expected" ]; then
  echo "error: $tag resolved to $head but the release resolver reported $expected" >&2
  exit 1
fi
du -sh . .git
