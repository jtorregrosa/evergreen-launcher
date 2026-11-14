#!/usr/bin/env bash
# Usage: smoke.sh <outdir>
# Functional smoke test of Evergreen on the tablet. Screenshots each step, reports crashes.
set -u
OUT=$1; mkdir -p "$OUT"
ADB="${ADB_BIN:-adb} -s ${ADB_SERIAL:?set ADB_SERIAL to the test device serial}"
PKG=io.github.jtorregrosa.evergreen
ACT=$PKG/app.lawnchair.LawnchairLauncher
focus() { $ADB shell dumpsys window | tr -d '\r' | grep -m1 mCurrentFocus | sed 's/.*u0 //;s/}//'; }
shot() { $ADB exec-out screencap -p > "$OUT/$1.png"; echo "$1: focus=$(focus)"; }
home() { $ADB shell am start -n $ACT >/dev/null 2>&1; sleep 1.5; $ADB shell input keyevent KEYCODE_BACK; sleep 1; }

$ADB logcat -b crash -c
$ADB shell am force-stop $PKG; sleep 1
$ADB shell am start -n $ACT >/dev/null; sleep 6
shot 01_home
$ADB shell input swipe 600 1200 600 300 250; sleep 1.5; shot 02_drawer
$ADB shell input tap 600 130; sleep 1.2
for c in c a l; do $ADB shell input text $c; sleep 0.4; done; sleep 2; shot 03_search
$ADB shell input keyevent KEYCODE_BACK; sleep 0.6; $ADB shell input keyevent KEYCODE_BACK; sleep 0.6; $ADB shell input keyevent KEYCODE_BACK; sleep 1
home
$ADB shell input swipe 600 700 600 700 1200; sleep 1.5; shot 04_longpress
$ADB shell input keyevent KEYCODE_BACK; sleep 1
$ADB shell input tap 157 1310; sleep 1.5; shot 05_folder
$ADB shell input keyevent KEYCODE_BACK; sleep 1
$ADB shell input tap 688 1310; sleep 3; shot 06_app_launched
home
$ADB shell am start -n $PKG/app.lawnchair.ui.preferences.PreferenceActivity >/dev/null 2>&1; sleep 3; shot 07_settings
$ADB shell input keyevent KEYCODE_BACK; sleep 1
home
$ADB shell input swipe 600 700 600 700 1200; sleep 1.5
shot 08_longpress_again
$ADB shell input keyevent KEYCODE_BACK; sleep 1
echo "crashes:"; $ADB logcat -d -b crash | tr -d '\r' | grep -E "FATAL|Process: $PKG|Exception" | head -20
echo "end"
