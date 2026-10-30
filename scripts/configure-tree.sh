#!/usr/bin/env bash
# Prepare a patched Firefox tree for a Gradle build against Mozilla's prebuilt GeckoView:
# no-compile mozconfig, mach bootstrap, configure and the pre-export/export steps.
#   usage: scripts/configure-tree.sh <tree> <geckoview-buildid>
# On GitHub Actions the variables the Gradle and signing steps need are written to $GITHUB_ENV.
set -euo pipefail

[ $# -eq 2 ] || { echo "usage: $0 <tree> <geckoview-buildid>" >&2; exit 2; }
tree="$(cd "$1" && pwd)"
buildid="$2"
[[ "$buildid" =~ ^[0-9]{14}$ ]] || { echo "error: bad GeckoView buildid '$buildid'" >&2; exit 1; }

mozconfig="$tree/mozconfig-embermine"
cat >"$mozconfig" <<'MOZ'
ac_add_options --enable-project=mobile/android
ac_add_options --target=aarch64-linux-android
ac_add_options --disable-compile-environment
ac_add_options --enable-update-channel=release
ac_add_options --without-google-safebrowsing-api-keyfile
ac_add_options --without-mozilla-api-keyfile
ac_add_options --disable-nodejs
export MOZILLA_OFFICIAL=1
export MOZ_ANDROID_FAT_AAR_ARCHITECTURES=arm64-v8a,x86_64
mk_add_options MOZ_OBJDIR=@TOPSRCDIR@/obj-embermine
MOZ

# MOZ_BUILD_DATE must equal the buildid in the geckoview-omni Maven version.
export MOZCONFIG="$mozconfig"
export MOZ_BUILD_DATE="$buildid"

cd "$tree"
t0=$(date +%s)
echo "::group::mach bootstrap"
./mach --no-interactive bootstrap --application-choice=mobile_android_artifact_mode >"${RUNNER_TEMP:-/tmp}/bootstrap.log" 2>&1 || {
  tail -n 80 "${RUNNER_TEMP:-/tmp}/bootstrap.log"
  exit 1
}
tail -n 20 "${RUNNER_TEMP:-/tmp}/bootstrap.log"
du -sh ~/.mozbuild
echo "::endgroup::"
echo "bootstrap took $(($(date +%s) - t0))s"

t0=$(date +%s)
./mach configure
./mach build pre-export export
echo "configure+export took $(($(date +%s) - t0))s"

java_home=""
for d in "$HOME"/.mozbuild/jdk/jdk-17*; do java_home="$d"; done
[ -d "$java_home" ] || { echo "error: no JDK 17 under ~/.mozbuild/jdk" >&2; exit 1; }
android_home="$HOME/.mozbuild/android-sdk-linux"
[ -d "$android_home" ] || { echo "error: no Android SDK at $android_home" >&2; exit 1; }

if [ -n "${GITHUB_ENV:-}" ]; then
  {
    echo "MOZCONFIG=$mozconfig"
    echo "MOZ_BUILD_DATE=$buildid"
    echo "JAVA_HOME=$java_home"
    echo "ANDROID_HOME=$android_home"
    echo "ANDROID_SDK_ROOT=$android_home"
  } >>"$GITHUB_ENV"
fi
