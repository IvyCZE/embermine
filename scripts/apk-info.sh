#!/usr/bin/env bash
# Write a report on the signed APKs: manifest facts from aapt2 and the signer certificate digest.
#   usage: scripts/apk-info.sh --dir DIR --out FILE
# BUILD_TOOLS: directory with aapt2 and apksigner (default: newest under $ANDROID_HOME/build-tools).
set -euo pipefail

die() {
  echo "error: $*" >&2
  exit 1
}

build_tool() {
  if [ -n "${BUILD_TOOLS:-}" ]; then
    echo "$BUILD_TOOLS/$1"
  else
    local newest
    newest="$(find "${ANDROID_HOME:?ANDROID_HOME or BUILD_TOOLS must be set}/build-tools" -mindepth 1 -maxdepth 1 | sort -V | tail -n 1)"
    [ -n "$newest" ] || die "no build-tools under $ANDROID_HOME"
    echo "$newest/$1"
  fi
}

dir=""
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) dir="${2:?--dir needs a directory}"; shift 2 ;;
    --out) out="${2:?--out needs a file}"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done
[ -n "$dir" ] && [ -n "$out" ] || die "usage: $0 --dir DIR --out FILE"

aapt2="$(build_tool aapt2)"
apksigner="$(build_tool apksigner)"

shopt -s nullglob
apks=("$dir"/embermine-*.apk)
[ "${#apks[@]}" -gt 0 ] || die "no embermine-*.apk in $dir"

: >"$out"
for apk in "${apks[@]}"; do
  badging="$("$aapt2" dump badging "$apk")"
  certs="$("$apksigner" verify --verbose --print-certs "$apk")" || die "apksigner verify failed for $apk"

  digests="$(printf '%s\n' "$certs" | sed -n 's/^Signer #[0-9]* certificate SHA-256 digest: //p')"
  [ "$(printf '%s\n' "$digests" | grep -c .)" -eq 1 ] || die "expected exactly one signer in $apk"
  signer_colon="$(printf '%s' "$digests" | tr 'a-f' 'A-F' | sed 's/../&:/g; s/:$//')"

  package_line="$(printf '%s\n' "$badging" | grep -m1 '^package:')"
  # sharedUserId can show up on the package line or only in the manifest tree
  manifest="$("$aapt2" dump xmltree "$apk" --file AndroidManifest.xml 2>/dev/null || true)"
  shared_user_id="$(printf '%s\n%s\n' "$package_line" "$manifest" |
    sed -n -e "s/.*sharedUserId='\([^']*\)'.*/\1/p" -e 's/.*sharedUserId[^=]*="\([^"]*\)".*/\1/p' | head -n 1)"
  app_line="$(printf '%s\n' "$badging" | grep -m1 '^application:' || true)"
  icon="$(printf '%s\n' "$app_line" | sed -n "s/.* icon='\([^']*\)'.*/\1/p")"
  if [ -z "$icon" ]; then
    icon="$(printf '%s\n' "$badging" | sed -n "s/^launchable-activity:.* icon='\([^']*\)'.*/\1/p" | head -n 1)"
  fi

  {
    echo "=== $(basename "$apk") ($(stat -c%s "$apk") bytes)"
    printf '%s\n' "$badging" | grep -E '^(package:|application-label:|application:|native-code:|sdkVersion:|targetSdkVersion:)'
    echo "versionCode: $(printf '%s\n' "$package_line" | sed -n "s/.*versionCode='\([^']*\)'.*/\1/p")"
    echo "versionName: $(printf '%s\n' "$package_line" | sed -n "s/.*versionName='\([^']*\)'.*/\1/p")"
    echo "signature-verified: yes"
    echo "signer-sha256: $signer_colon"
    echo "signer-sha256-hex: $(printf '%s' "$digests" | tr 'A-F' 'a-f')"
    if [ -n "$shared_user_id" ]; then
      echo "sharedUserId: present ($shared_user_id)"
    else
      echo "sharedUserId: absent"
    fi
    echo "launcher-icon: ${icon:-none}"
    echo
  } >>"$out"
done
cat "$out"
