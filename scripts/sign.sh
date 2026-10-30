#!/usr/bin/env bash
# Align and sign the unsigned release APKs of the build.
#   usage: scripts/sign.sh --in-dir DIR --out-dir DIR --version VERSION [--require-owner-key]
#          scripts/sign.sh --decide [--require-owner-key]   print the key mode (owner|throwaway) and exit
#
# Key selection:
#   KEYSTORE_BASE64 empty or unset  -> throwaway key generated in a temp dir (forks, PRs);
#                                      refused with --require-owner-key (release path)
#   KEYSTORE_BASE64 set             -> owner PKCS12 key, which needs KEYSTORE_PASSWORD and KEY_PASSWORD too;
#                                      any decode or signing error fails, there is no fallback
# The key alias is read from the keystore (it must hold exactly one private key entry). KEY_ALIAS is only
# an optional override: a secret with the alias value would make GitHub mask that word in every log line.
# BUILD_TOOLS: directory with zipalign and apksigner (default: newest under $ANDROID_HOME/build-tools).
# Secrets only travel through environment variables and files in a private temp dir; nothing here
# prints them and tracing must stay off.
set -euo pipefail

die() {
  echo "error: $*" >&2
  exit 1
}

decide_mode() {
  if [ -z "${KEYSTORE_BASE64:-}" ]; then
    [ "$require_owner" -eq 0 ] ||
      die "owner signing key required but KEYSTORE_BASE64 is empty; refusing to use a throwaway key"
    echo throwaway
    return
  fi
  local var
  for var in KEYSTORE_PASSWORD KEY_PASSWORD; do
    [ -n "${!var:-}" ] || die "KEYSTORE_BASE64 is set but $var is empty"
  done
  echo owner
}

# Alias of the single private key entry of a PKCS12 keystore (password in EMBERMINE_KS_PASS).
keystore_alias() {
  local listing aliases
  listing="$(keytool -list -keystore "$1" -storetype PKCS12 -storepass:env EMBERMINE_KS_PASS)" ||
    die "keytool cannot read the keystore"
  aliases="$(printf '%s\n' "$listing" | sed -n 's/^\([^,]*\), .*PrivateKeyEntry,.*$/\1/p')"
  [ "$(printf '%s\n' "$aliases" | grep -c .)" -eq 1 ] ||
    die "expected exactly one private key entry in the keystore, found: $(printf '%s\n' "$aliases" | grep -c .)"
  printf '%s\n' "$aliases"
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

in_dir=""
out_dir=""
version=""
require_owner=0
decide_only=0
while [ $# -gt 0 ]; do
  case "$1" in
    --in-dir) in_dir="${2:?--in-dir needs a directory}"; shift 2 ;;
    --out-dir) out_dir="${2:?--out-dir needs a directory}"; shift 2 ;;
    --version) version="${2:?--version needs a value}"; shift 2 ;;
    --require-owner-key) require_owner=1; shift ;;
    --decide) decide_only=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

mode="$(decide_mode)"
if [ "$decide_only" -eq 1 ]; then
  echo "$mode"
  exit 0
fi
[ -n "$in_dir" ] && [ -n "$out_dir" ] && [ -n "$version" ] || die "--in-dir, --out-dir and --version are required"

if [ "${GITHUB_ACTIONS:-}" = "true" ] && [ "$mode" = owner ]; then
  echo "::add-mask::$KEYSTORE_PASSWORD"
  echo "::add-mask::$KEY_PASSWORD"
fi

zipalign="$(build_tool zipalign)"
apksigner="$(build_tool apksigner)"

work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/embermine-sign.XXXXXX")"
trap 'rm -rf "$work"' EXIT

if [ "$mode" = owner ]; then
  echo "signing mode: owner key"
  keystore="$work/release.p12"
  (umask 077 && printf '%s' "$KEYSTORE_BASE64" | base64 -d >"$keystore") ||
    die "KEYSTORE_BASE64 is set but cannot be decoded"
  [ -s "$keystore" ] || die "KEYSTORE_BASE64 decoded to an empty keystore"
  export EMBERMINE_KS_PASS="$KEYSTORE_PASSWORD"
  export EMBERMINE_KEY_PASS="$KEY_PASSWORD"
  if [ -n "${KEY_ALIAS:-}" ]; then
    key_alias="$KEY_ALIAS"
  else
    key_alias="$(keystore_alias "$keystore")"
  fi
  echo "key alias: $key_alias"
else
  echo "signing mode: throwaway test key (no signing secrets available)"
  keystore="$work/throwaway.p12"
  key_alias="embermine-test"
  EMBERMINE_KS_PASS="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
  export EMBERMINE_KS_PASS
  export EMBERMINE_KEY_PASS="$EMBERMINE_KS_PASS"
  keytool -genkeypair -keystore "$keystore" -storetype PKCS12 -alias "$key_alias" \
    -keyalg RSA -keysize 2048 -validity 3650 -dname "CN=Embermine CI throwaway key" \
    -storepass:env EMBERMINE_KS_PASS -keypass:env EMBERMINE_KEY_PASS >/dev/null
fi

abis=(arm64-v8a x86_64)
shopt -s nullglob
for apk in "$in_dir"/*.apk; do
  known=0
  for abi in "${abis[@]}"; do
    [ "$(basename "$apk")" = "app-$abi-release-unsigned.apk" ] && known=1
  done
  [ "$known" -eq 1 ] || die "unexpected APK in $in_dir: $(basename "$apk")"
done

mkdir -p "$out_dir"
for abi in "${abis[@]}"; do
  unsigned="$in_dir/app-$abi-release-unsigned.apk"
  [ -f "$unsigned" ] || die "missing $unsigned"
  signed="$out_dir/embermine-$version-$abi.apk"
  "$zipalign" -p -f 4 "$unsigned" "$work/aligned-$abi.apk"
  "$apksigner" sign --ks "$keystore" --ks-type PKCS12 --ks-key-alias "$key_alias" \
    --ks-pass env:EMBERMINE_KS_PASS --key-pass env:EMBERMINE_KEY_PASS \
    --v4-signing-enabled false --out "$signed" "$work/aligned-$abi.apk"
  echo "== $(basename "$signed")"
  "$apksigner" verify --verbose --print-certs "$signed" | grep -E 'Verifies|Verified using|SHA-256 digest'
done

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "signing=$mode" >>"$GITHUB_OUTPUT"
fi
