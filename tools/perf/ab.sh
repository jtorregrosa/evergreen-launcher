#!/usr/bin/env bash
# Usage: ab.sh <outdir> <rounds> <apkA> <apkB> <command> [args ...]
# Interleaved A/B comparison: installs A, runs the command, installs B, runs it again, and so on
# for <rounds> rounds (A, B, A, B, ...). Both APKs are compiled with `speed` after install so the
# compilation state is the same. Every `@LABEL@` in the command is replaced by the run label
# (A1, B1, A2, ...), e.g. `bash tools/perf/scenario.sh @LABEL@ out/fs folder`.
# The output of every run goes to <outdir>/ab.txt. Summarize with `summ.py <outdir>/ab.txt`
# after replacing the round number, e.g. `sed 's/^\([AB]\)[0-9]*,/\1,/' ab.txt > ab-by-build.txt`.
#
# HOME_COMPONENT: the default launcher to restore after every install
#                 (default: app.lawnchair/.LawnchairLauncher)
set -u
OUT=${1:?usage}; ROUNDS=${2:?usage}; APK_A=${3:?usage}; APK_B=${4:?usage}; shift 4
mkdir -p "$OUT"
ADB="${ADB_BIN:-adb} -s ${ADB_SERIAL:?set ADB_SERIAL to the test device serial}"
PKG=io.github.jtorregrosa.evergreen
HOME_COMPONENT=${HOME_COMPONENT:-app.lawnchair/.LawnchairLauncher}

install() {
  $ADB install -r "$1" >/dev/null || { echo "install failed: $1"; exit 1; }
  $ADB shell cmd package set-home-activity "$HOME_COMPONENT" >/dev/null
  $ADB shell cmd package compile -m speed -f $PKG >/dev/null
}

for r in $(seq "$ROUNDS"); do
  for side in A B; do
    if [ $side = A ]; then install "$APK_A"; else install "$APK_B"; fi
    args=()
    for a in "$@"; do args+=("${a//@LABEL@/$side$r}"); done
    "${args[@]}" 2>&1 | tee -a "$OUT/ab.txt"
  done
done
