#!/usr/bin/env bash
# Usage: measure.sh <compile-filter> <runs> <label>
# Measures Evergreen cold start on the device given by ADB_SERIAL.
set -u
FILTER=$1; RUNS=$2; LABEL=$3
ADB="${ADB_BIN:-adb} -s ${ADB_SERIAL:?set ADB_SERIAL to the test device serial}"
PKG=io.github.jtorregrosa.evergreen
ACT=$PKG/app.lawnchair.LawnchairLauncher

$ADB shell cmd package compile -m "$FILTER" -f $PKG >/dev/null
$ADB shell input keyevent KEYCODE_WAKEUP
# one warm-up run (DB creation, first-run work)
$ADB shell am force-stop $PKG; $ADB shell am start -W -n $ACT >/dev/null; sleep 10

for i in $(seq "$RUNS"); do
  $ADB shell am force-stop $PKG
  sleep 3
  $ADB logcat -c
  T=$($ADB shell am start -W -n $ACT | tr -d '\r' | awk '/TotalTime/{print $2}')
  sleep 9
  LOG=$($ADB logcat -d | tr -d '\r')
  FD=$(echo "$LOG" | grep -o "Fully drawn $PKG/[^ ]*: +[0-9ms]*" | tail -1 | sed 's/.*: +//')
  FB=$(echo "$LOG" | grep -c "using fallback bulk icon loading")
  echo "$LABEL,$FILTER,$i,$T,$FD,$FB"
done
$ADB shell dumpsys meminfo $PKG | tr -d '\r' | grep -E "TOTAL PSS|TOTAL:" | head -1 | sed "s/^/$LABEL,$FILTER,meminfo,/"
