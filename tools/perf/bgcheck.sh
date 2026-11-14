#!/usr/bin/env bash
# Usage: bgcheck.sh <label>
# Puts Evergreen in the background (opens system Settings) and reports what it still keeps alive.
set -u
LABEL=$1
ADB="${ADB_BIN:-adb} -s ${ADB_SERIAL:?set ADB_SERIAL to the test device serial}"
PKG=io.github.jtorregrosa.evergreen

$ADB shell am start -n $PKG/app.lawnchair.LawnchairLauncher >/dev/null; sleep 5
fg_hosts=$($ADB shell dumpsys appwidget | tr -d '\r' | grep -A1 "pkg:$PKG" | grep -c "callbacks=com")
$ADB shell am start -a android.settings.SETTINGS >/dev/null; sleep 5
bg_hosts=$($ADB shell dumpsys appwidget | tr -d '\r' | grep -A1 "pkg:$PKG" | grep -c "callbacks=com")
battery=$($ADB shell dumpsys activity broadcasts | tr -d '\r' | grep -B1 -A6 "$PKG" | grep -c "android.intent.action.BATTERY_CHANGED")
timetick=$($ADB shell dumpsys activity broadcasts | tr -d '\r' | grep -B1 -A6 "$PKG" | grep -c "android.intent.action.TIME_TICK")
echo "$LABEL,bg,listening_widget_hosts_foreground=$fg_hosts,listening_widget_hosts_background=$bg_hosts,battery_receivers_background=$battery,time_tick_receivers=$timetick"
$ADB shell input keyevent KEYCODE_BACK; sleep 1
