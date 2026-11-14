#!/usr/bin/env bash
# Usage: interact.sh <label>
# Frame stats (dumpsys gfxinfo) for page swipes, drawer open/scroll/close and drawer search.
set -u
LABEL=$1
ADB="${ADB_BIN:-adb} -s ${ADB_SERIAL:?set ADB_SERIAL to the test device serial}"
PKG=io.github.jtorregrosa.evergreen
ACT=$PKG/app.lawnchair.LawnchairLauncher

stats() {
  $ADB shell dumpsys gfxinfo $PKG | tr -d '\r' | awk -v l="$LABEL" -v s="$1" '
    /Total frames rendered/ {t=$4}
    /Janky frames/ {j=$3; p=$4}
    /50th percentile/ {p50=$3}
    /90th percentile/ {p90=$3}
    /95th percentile/ {p95=$3}
    /99th percentile/ {p99=$3}
    END {print l "," s ",frames=" t ",janky=" j " " p ",p50=" p50 ",p90=" p90 ",p95=" p95 ",p99=" p99; exit}'
}

$ADB shell input keyevent KEYCODE_WAKEUP
$ADB shell am force-stop $PKG; sleep 2
$ADB shell am start -n $ACT >/dev/null; sleep 8

# 1) Workspace page swipes
$ADB shell dumpsys gfxinfo $PKG reset >/dev/null
for i in $(seq 10); do
  $ADB shell input swipe 1000 600 200 600 200; sleep 0.8
  $ADB shell input swipe 200 600 1000 600 200; sleep 0.8
done
stats pages

# 2) Drawer open, scroll, close
$ADB shell dumpsys gfxinfo $PKG reset >/dev/null
for i in $(seq 6); do
  $ADB shell input swipe 600 1200 600 300 250; sleep 1.2
  $ADB shell input swipe 600 1500 600 500 150; sleep 0.8
  $ADB shell input swipe 600 500 600 1500 150; sleep 0.8
  $ADB shell input keyevent KEYCODE_BACK; sleep 1.2
done
stats drawer

# 3) Drawer search: tap the search bar, type a query letter by letter, clear, repeat
$ADB shell dumpsys gfxinfo $PKG reset >/dev/null
focus() { $ADB shell dumpsys window | tr -d '\r' | grep -m1 mCurrentFocus; }
bad=0
for q in goo mapa you cal; do
  $ADB shell input swipe 600 1200 600 300 250; sleep 1.5
  $ADB shell input tap 600 130; sleep 1.2
  focus | grep -q "$PKG" || bad=$((bad+1))
  for (( k=0; k<${#q}; k++ )); do $ADB shell input text "${q:$k:1}"; sleep 0.35; done
  sleep 2
  focus | grep -q "$PKG" || bad=$((bad+1))
  $ADB shell input keyevent KEYCODE_BACK; sleep 0.6
  $ADB shell input keyevent KEYCODE_BACK; sleep 0.6
  $ADB shell input keyevent KEYCODE_BACK; sleep 1
done
stats search
echo "$LABEL,search_focus_errors=$bad"
