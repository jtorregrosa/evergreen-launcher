#!/usr/bin/env bash
# Usage: scenario.sh <label> <outdir> [scenario ...]
# Frame stats for the everyday interactions that interact.sh does not cover. Prints one line per
# scenario in the interact.sh format, plus a stage breakdown of the slow frames (framestats.py).
# The raw `dumpsys gfxinfo framestats` dump of every repetition is kept in <outdir>.
#
# Scenarios (default: all of them, in this order):
#   home_back      return to Evergreen by closing an app with BACK (the non-recents close path)
#   home_intent    return to Evergreen with a launch intent, as the HOME button does
#   open_home      open an app from a home screen icon
#   open_drawer    open an app from the drawer
#   drawer_toggle  open and close the drawer, without scrolling
#   drawer_fling   fling the drawer list up and down
#   folder         open and close a home screen folder
#   menu_home      long-press menu on empty home screen space
#   menu_icon      long-press menu on a home screen icon
#   widgets        open the widget picker from the home menu, scroll it, close it
#   idle           30 s of untouched home screen (the frame count should stay near 0)
#
# Tap targets are "x y" coordinates. The defaults fit a 1200x1920 portrait tablet with the default
# Evergreen tablet layout (6x5 grid, 6-column drawer). Override them with environment variables:
#   HOME_APP_XY    an app icon on the first home screen               (default: 688 1310)
#   DRAWER_APP_XY  an app in the open drawer                          (default: 685 270)
#   FOLDER_XY      a folder on the first home screen                  (default: 157 1310)
#   WIDGETS_XY     the widgets entry of the home long-press menu      (default: 683 531)
#   EMPTY_XY       empty space on the first home screen               (default: centre, 36% down)
# Set one of them to an empty string to look the view up by label with `uiautomator dump` instead
# (HOME_APP, DRAWER_APP, FOLDER, WIDGETS_ITEM; defaults: Ajustes, Calculadora, Google, Widgets).
# Other settings:
#   OTHER_APP      `am start` arguments of the app used by home_*     (default: system Settings)
#   REPS           repetitions per scenario                           (default: 8)
#   VERBOSE=1      also print the worst frames of each scenario
set -u

LABEL=${1:?usage: scenario.sh <label> <outdir> [scenario ...]}
OUT=${2:?usage: scenario.sh <label> <outdir> [scenario ...]}
shift 2
ALL="home_back home_intent open_home open_drawer drawer_toggle drawer_fling folder menu_home menu_icon widgets idle"
SCENARIOS=${*:-$ALL}
mkdir -p "$OUT"

ADB="${ADB_BIN:-adb} -s ${ADB_SERIAL:?set ADB_SERIAL to the test device serial}"
PY=${PYTHON:-python}
DIR=$(cd "$(dirname "$0")" && pwd)
PKG=io.github.jtorregrosa.evergreen
ACT=$PKG/app.lawnchair.LawnchairLauncher

HOME_APP=${HOME_APP:-Ajustes}
DRAWER_APP=${DRAWER_APP:-Calculadora}
FOLDER=${FOLDER:-Google}
WIDGETS_ITEM=${WIDGETS_ITEM:-Widgets}
HOME_APP_XY=${HOME_APP_XY-"688 1310"}
DRAWER_APP_XY=${DRAWER_APP_XY-"685 270"}
FOLDER_XY=${FOLDER_XY-"157 1310"}
WIDGETS_XY=${WIDGETS_XY-"683 531"}
OTHER_APP=${OTHER_APP:-"-a android.settings.SETTINGS"}
REPS=${REPS:-8}

read -r W H < <($ADB shell wm size | tr -d '\r' | sed -n 's/.*: \([0-9]*\)x\([0-9]*\).*/\1 \2/p' | tail -1)
CX=$((W / 2))
EMPTY_XY=${EMPTY_XY:-"$CX $((H * 36 / 100))"}
OPEN_DRAWER="$CX $((H * 62 / 100)) $CX $((H * 16 / 100)) 250"
FLING_UP="$CX $((H * 78 / 100)) $CX $((H * 26 / 100)) 80"
FLING_DOWN="$CX $((H * 26 / 100)) $CX $((H * 78 / 100)) 80"

bad=0
focus_ok() { $ADB shell dumpsys window | tr -d '\r' | grep -m1 mCurrentFocus | grep -q "$PKG"; }
check_focus() { focus_ok || { bad=$((bad + 1)); go_home; }; }
key() { $ADB shell input keyevent "$1"; }
tap() { $ADB shell input tap $1; }
swipe() { $ADB shell input swipe $1; }
long_press() { $ADB shell input swipe $1 $1 "${2:-1000}"; }
reset() { $ADB shell dumpsys gfxinfo $PKG reset >/dev/null; }
dump() { $ADB shell dumpsys gfxinfo $PKG framestats | tr -d '\r' >"$OUT/${LABEL}_$1_$2.txt"; }
go_home() {
  $ADB shell am start -n $ACT >/dev/null 2>&1
  sleep 1.5
  key KEYCODE_BACK
  sleep 1
}
start_other() {
  $ADB shell am start -W --activity-clear-task $OTHER_APP >/dev/null 2>&1
  sleep 1.5
}
# ui_xy <label> [occurrence]: prints "x y" of a visible view, fails if it is not on screen
ui_xy() {
  # MSYS_NO_PATHCONV keeps Git Bash from rewriting the device path
  MSYS_NO_PATHCONV=1 $ADB shell uiautomator dump /sdcard/evg_ui.xml >/dev/null 2>&1
  MSYS_NO_PATHCONV=1 $ADB shell cat /sdcard/evg_ui.xml | $PY "$DIR/uifind.py" "$@"
}
# locate <coordinates-or-empty> <label>: the given coordinates, or a lookup by label
locate() {
  if [ -n "$1" ]; then echo "$1"; else ui_xy "$2"; fi
}
report() {
  $PY "$DIR/framestats.py" ${VERBOSE:+-v} "$LABEL" "$1" "$OUT/${LABEL}_$1_"*.txt
  [ "$bad" -gt 0 ] && echo "$LABEL,$1,focus_errors=$bad"
  bad=0
}
skip() { echo "$LABEL,$1,skipped: $2"; }

home_back() {
  for i in $(seq "$REPS"); do
    start_other
    reset
    key KEYCODE_BACK
    sleep 2
    dump home_back "$i"
    check_focus
  done
  report home_back
}

home_intent() {
  for i in $(seq "$REPS"); do
    start_other
    reset
    $ADB shell am start -n $ACT >/dev/null 2>&1
    sleep 2
    dump home_intent "$i"
    check_focus
  done
  report home_intent
}

open_home() {
  local xy
  xy=$(locate "$HOME_APP_XY" "$HOME_APP") || { skip open_home "no '$HOME_APP' icon on the home screen"; return; }
  for i in $(seq "$REPS"); do
    reset
    tap "$xy"
    sleep 2.5
    dump open_home "$i"
    focus_ok && bad=$((bad + 1)) # the app did not open
    key KEYCODE_BACK
    sleep 1.5
    focus_ok || go_home
  done
  report open_home
}

open_drawer() {
  local xy=""
  for i in $(seq "$REPS"); do
    swipe "$OPEN_DRAWER"
    sleep 1.5
    if [ -z "$xy" ]; then
      xy=$(locate "$DRAWER_APP_XY" "$DRAWER_APP") || { skip open_drawer "no '$DRAWER_APP' in the drawer"; go_home; return; }
    fi
    reset
    tap "$xy"
    sleep 2.5
    dump open_drawer "$i"
    focus_ok && bad=$((bad + 1))
    key KEYCODE_BACK
    sleep 1.5
    go_home
  done
  report open_drawer
}

drawer_toggle() {
  for i in $(seq "$REPS"); do
    reset
    swipe "$OPEN_DRAWER"
    sleep 1.3
    key KEYCODE_BACK
    sleep 1.3
    dump drawer_toggle "$i"
    check_focus
  done
  report drawer_toggle
}

drawer_fling() {
  for i in 1 2 3; do
    swipe "$OPEN_DRAWER"
    sleep 1.5
    reset
    for k in 1 2 3 4; do
      swipe "$FLING_UP"
      sleep 0.8
      swipe "$FLING_DOWN"
      sleep 0.8
    done
    dump drawer_fling "$i"
    key KEYCODE_BACK
    sleep 1.2
    check_focus
  done
  report drawer_fling
}

folder() {
  local xy
  xy=$(locate "$FOLDER_XY" "$FOLDER") || { skip folder "no '$FOLDER' folder on the home screen"; return; }
  for i in $(seq "$REPS"); do
    reset
    tap "$xy"
    sleep 1.2
    key KEYCODE_BACK
    sleep 1.2
    dump folder "$i"
    check_focus
  done
  report folder
}

menu_home() {
  for i in $(seq "$REPS"); do
    reset
    long_press "$EMPTY_XY" 1000
    sleep 1
    key KEYCODE_BACK
    sleep 0.8
    dump menu_home "$i"
    check_focus
  done
  report menu_home
}

menu_icon() {
  local xy
  xy=$(locate "$HOME_APP_XY" "$HOME_APP") || { skip menu_icon "no '$HOME_APP' icon on the home screen"; return; }
  for i in $(seq "$REPS"); do
    reset
    long_press "$xy" 800
    sleep 1
    key KEYCODE_BACK
    sleep 0.8
    dump menu_icon "$i"
    check_focus
  done
  report menu_icon
}

widgets() {
  local xy=""
  for i in 1 2 3 4; do
    long_press "$EMPTY_XY" 1000
    sleep 1.2
    if [ -z "$xy" ]; then
      xy=$(locate "$WIDGETS_XY" "$WIDGETS_ITEM") || { skip widgets "no '$WIDGETS_ITEM' entry in the home menu"; go_home; return; }
    fi
    reset
    tap "$xy"
    sleep 2.5
    for k in 1 2 3; do
      swipe "$CX $((H * 70 / 100)) $CX $((H * 35 / 100)) 150"
      sleep 0.9
    done
    key KEYCODE_BACK
    sleep 1.2
    dump widgets "$i"
    check_focus
  done
  report widgets
}

idle() {
  sleep 3
  reset
  sleep 30
  dump idle 1
  report idle
}

key KEYCODE_WAKEUP
go_home
focus_ok || { echo "$LABEL,aborted: Evergreen is not in focus (locked screen or another app?)"; exit 1; }
for s in $SCENARIOS; do
  case " $ALL " in
    *" $s "*) rm -f "$OUT/${LABEL}_${s}_"*.txt; "$s" ;;
    *) echo "$LABEL,$s,skipped: unknown scenario" ;;
  esac
done
go_home
