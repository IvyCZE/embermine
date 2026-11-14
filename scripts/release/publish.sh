#!/usr/bin/env bash
# Create the GitHub Release v<VERSION> with its APKs and release notes. Only the publish job of release.yml
# runs this, and only when vars.EMBERMINE_PUBLISH is exactly 'true' and the build and checks passed.
# It refuses to publish over an existing release or tag, and never creates a release without the APKs.
#   env: GH_TOKEN, REPO (OWNER/REPO), VERSION (e.g. 159.0 or 159.0-r2), TAG (must be v<VERSION>),
#        SHA (commit the tag points to), DIST (directory with the APKs), NOTES (release notes file)
#        REMOTE (git remote to check for existing tags, default origin)
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

die() {
  echo "error: $*" >&2
  exit 1
}

: "${REPO:?REPO is required}" "${VERSION:?VERSION is required}" "${TAG:?TAG is required}" "${SHA:?SHA is required}"
DIST="${DIST:-dist}"
NOTES="${NOTES:-notes/release-notes.md}"
REMOTE="${REMOTE:-origin}"

expected_tag="$(python3 -m scripts.release.naming tag "$VERSION")" || die "$VERSION is not a release version"
[ "$TAG" = "$expected_tag" ] || die "tag $TAG does not match version $VERSION (expected $expected_tag)"
title="$(python3 -m scripts.release.naming title "$VERSION")"

if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  die "a GitHub Release $TAG already exists; not publishing over it"
fi
remote_tags="$(git ls-remote --tags "$REMOTE" "refs/tags/$TAG")"
[ -z "$remote_tags" ] || die "tag $TAG already exists on $REMOTE; not publishing over it"

[ -f "$NOTES" ] || die "release notes $NOTES are missing"
assets=()
while read -r apk; do
  [ -f "$DIST/$apk" ] || die "APK $DIST/$apk is missing"
  assets+=("$DIST/$apk")
done < <(python3 -m scripts.release.naming apks "$VERSION")

gh release create "$TAG" --repo "$REPO" --target "$SHA" --title "$title" --notes-file "$NOTES" "${assets[@]}"
echo "published $TAG with ${#assets[@]} APKs"
