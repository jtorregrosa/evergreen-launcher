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
| `smoke.sh <outdir>` | Functional smoke test: home, drawer, search, long-press menu, folder, app launch, settings. Saves screenshots, prints the focus per step and any crashes. |
| `bgcheck.sh <label>` | Puts Evergreen behind system Settings and reports how many of its AppWidgetHosts are still listening. |
| `summ.py <csv>` | Summarizes the output of the scripts above: cold-start medians and jank averages per label. |

## Notes

- **Coordinates:** taps and swipes are hard-coded for a 1200×1920 portrait tablet with the default
  Evergreen layout. Adjust them for other screens.
- **Launcher:** the scripts launch Evergreen explicitly. Keep another launcher as the default HOME,
  otherwise the system relaunches Evergreen after every `force-stop` and the cold-start runs come back
  with `TotalTime: 0`. Installing a new HOME app can reset the default HOME on Android 10. Restore
  it with `cmd package set-home-activity <component>`.
- **Screen:** keep the screen on and unlocked (`svc power stayon usb` during the run, and
  `svc power stayon false` afterwards). A locked screen skews the timings.
- **Noise:** interaction results vary by about ±5 percentage points between runs. Compare builds by
  interleaving rounds (A, B, A, B, …), not with back-to-back blocks.
