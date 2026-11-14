# On-device performance scripts

Bash scripts used to produce `docs/perf/RESULTS.md`. They drive a real device over adb, so only
one session or person should run them on a device at a time.

```bash
export ADB_SERIAL=<device serial>            # required: adb devices -l
export ADB_BIN=/path/to/adb                  # optional, defaults to `adb`
```

| Script | What it does |
|---|---|
| `measure.sh <verify\|speed> <runs> <label>` | Cold start: forces a compilation state, then `am force-stop` + `am start -W` N times. Prints `label,filter,run,TotalTime,FullyDrawn,iconFallbacks` per run, plus a meminfo line. |
| `interact.sh <label>` | `dumpsys gfxinfo` for 20 page swipes, 6 drawer open/scroll/close rounds and 4 drawer searches typed letter by letter. It checks that Evergreen keeps focus during search (`search_focus_errors`). |
| `scenario.sh <label> <outdir> [scenario ...]` | Frame stats for the other everyday interactions: returning home (`home_back`, `home_intent`), opening an app (`open_home`, `open_drawer`), `drawer_toggle`, `drawer_fling`, `folder`, the long-press menus (`menu_home`, `menu_icon`), `widgets` and 30 s of `idle` home screen. Prints one `interact.sh`-style line per scenario plus a stage breakdown of the slow frames, and keeps the raw dumps in `<outdir>`. `VERBOSE=1` also lists the worst frames. |
| `framestats.py [-v] <label> <scenario> <dump>...` | Summarizes `dumpsys gfxinfo <pkg> framestats` dumps: percentiles from the per-frame rows and, for frames longer than 16.7 ms, the average time per stage (main thread wait, input, animation, layout, draw, sync, GPU, swap) and which stage dominates. Used by `scenario.sh`. |
| `uifind.py <label>` | Finds a view by text in a `uiautomator dump` and prints its centre. Optional helper for `scenario.sh`. |
| `ab.sh <outdir> <rounds> <apkA> <apkB> <command...>` | Interleaved A/B: installs A and B in turn (compiled with `speed`), runs the command with `@LABEL@` replaced by `A1`, `B1`, `A2`, … and appends the output to `<outdir>/ab.txt`. Copy the scripts outside the checkout before a long run, so switching branches doesn't change them mid-run. |
| `smoke.sh <outdir>` | Functional smoke test: home, drawer, search, long-press menu, folder, app launch, settings. Saves screenshots, prints the focus per step and any crashes. |
| `bgcheck.sh <label>` | Puts Evergreen behind system Settings and reports how many of its AppWidgetHosts are still listening. |
| `summ.py <csv>` | Summarizes the output of the scripts above: cold-start medians and jank averages per label. |

## Notes

- **Coordinates:** taps and swipes are hard-coded for a 1200×1920 portrait tablet with the default
  Evergreen layout. Adjust them for other screens. `scenario.sh` takes its tap targets from
  environment variables (`HOME_APP_XY`, `DRAWER_APP_XY`, `FOLDER_XY`, `WIDGETS_XY`, `EMPTY_XY`).
- **Coordinates after #18:** the defaults fit the tablet layout (6x5 grid). Builds before #18 used
  the two-panel layout: folder `85 1390`, home app `1113 1390`, drawer app `996 265`.
- **Play Protect:** installing a new APK over adb can stop at a "send app for scanning" dialog
  that waits for a tap, which stalls `ab.sh`. Watch the device during the first install of each
  APK.
- **Stages:** in `framestats.py` output, `wait` is main-thread work before the frame started
  (click handlers, lifecycle callbacks, posted runnables), `layout` and `draw` are the main
  thread inside the frame, and `syncq`, `sync`, `gpu` and `swap` are the RenderThread and the
  buffer queue.
- **Short lists:** `drawer_fling` needs a drawer that scrolls. With few apps the list fits on one
  screen and a fling at the top closes the sheet instead.
- **Launcher:** the scripts launch Evergreen explicitly. Keep another launcher as the default HOME,
  otherwise the system relaunches Evergreen after every `force-stop` and the cold-start runs come back
  with `TotalTime: 0`. Installing a new HOME app can reset the default HOME on Android 10. Restore
  it with `cmd package set-home-activity <component>`.
- **Screen:** keep the screen on and unlocked (`svc power stayon usb` during the run, and
  `svc power stayon false` afterwards). A locked screen skews the timings.
- **Noise:** interaction results vary by about ±5 percentage points between runs. Compare builds by
  interleaving rounds (A, B, A, B, …), not with back-to-back blocks.
