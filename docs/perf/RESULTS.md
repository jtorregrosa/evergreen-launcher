# Evergreen: measured results

Device: Lenovo Tab M10 FHD Plus (TB-X606F), Helio P22T (8× Cortex-A53), 4 GB RAM, 1200×1920, Android 10.
All numbers are from release APKs. Stock Lawnchair stays the default launcher and Evergreen is
launched explicitly, with the screen on and unlocked.

## How it is measured

- **Cold start:** `am start -W -n io.github.jtorregrosa.evergreen/app.lawnchair.LawnchairLauncher`
  after `am force-stop`. Each figure is the median of 8 runs (range in parentheses), measured
  after `cmd package compile -m verify -f` (no AOT, like a fresh sideload) and after `-m speed -f`
  (full AOT). The same pass counts `using fallback bulk icon loading` lines in logcat, one per icon
  re-rendered instead of being read from the icon cache.
- **Interaction:** `dumpsys gfxinfo <pkg>` after a scripted sequence, averaged over 2 rounds:
  - pages: 20 workspace page swipes;
  - drawer: 6 rounds of open, scroll down, scroll up and close;
  - search: 4 queries typed letter by letter in the drawer search.

  The script checks that Evergreen keeps focus during the search part, so typing into another app
  doesn't count.

## Cold start

| Build | `verify` | `speed` | Icon fallbacks / start |
|---|---|---|---|
| Base (`20a7ccd`, instrumentation only) | 2287 ms (2165–2606) | 1700 ms (1649–2168) | 14 |
| PR #1: icon cache, Room, popup write (`acbb5fd`) | 1872 ms (1819–1922) | 1421 ms (1396–1436) | 0 |
| PR #2: hot-path prefs, search, NPE, profile install (`2686e34`) | 1687 ms (1672–1703) | 1347 ms (1324–1365) | 0 |
| PR #3: background work, leaks, startup/search IPC (`d19993b`) | **1669 ms** (1634–1690) | **1328 ms** (1304–1362) | 0 |

Total so far: **−27%** without AOT and **−22%** with full AOT.

## Interaction (janky frames %, frame-time percentiles)

| Build | Pages: janky / p90 / p99 | Drawer: janky / p95 / p99 | Search: janky / p95 / p99 |
|---|---|---|---|
| PR #1 | 0.0% / 9 / 12 ms | 22.1% / 23 / 36 ms | 29.6% / 33 / 61 ms |
| PR #2 | 0.1% / 8 / 12 ms | **16.8%** / 20 / 37 ms | **27.1%** / 26 / **46 ms** |
| PR #3 (3 rounds) | 0.05% / 9 / 12 ms | 20.2% / 21 / 34 ms | 31.8% / 28 / 47 ms |
| PR #4: no workspace under the drawer sheet below API 31 (3 rounds) | 0.1% / 9 / 12 ms | **9.6%** / 20 / 37 ms | **22.1%** / 26 / 48 ms |
| Main after PR #6 (3 rounds, interleaved with the next row) | 0.3% / 8 / 11 ms | 9.5% / 21 / 39 ms | 18.8% / 25 / 48 ms |
| PR #7: no animated search bar padding below API 31 (3 rounds, interleaved) | 0.3% / 8 / 11 ms | 8.5% / 20 / 34 ms | **15.2%** / 26 / 49 ms |

Run-to-run noise in the drawer and search columns is about ±5 percentage points, so PR #3 is
neutral for interaction, as expected. Its target is background work:

| Background check (Evergreen behind system Settings) | PR #2 | PR #3 |
|---|---|---|
| Evergreen AppWidgetHosts still listening (`dumpsys appwidget`) | 3 | **0** |

Page swipes were already smooth. Most of the remaining drawer jank is the open/close transition on
the tablet layout (EVG-8). The remaining search jank is the IME and padding animation (EVG-10f).

## Summary since the base

| Metric | Base | Now | Change |
|---|---|---|---|
| Cold start, `verify` | 2287 ms | ~1700 ms | **−26%** |
| Cold start, `speed` | 1700 ms | ~1330 ms | **−22%** |
| Icons re-rendered per cold start | 14 | 0 | |
| Drawer open/scroll/close, janky frames | 22.1% (PR #1) | 8.5% | **−62%** |
| Drawer search typing, janky frames | 29.6% (PR #1) | 15.2% | **−49%** |
| Evergreen widget hosts listening in background | 3 | 0 | |

## Everyday interactions (`scenario.sh`)

Baseline for the tablet pass, `evergreen` at `4211efc`, 8 repetitions per scenario (4 for
widgets). The same build measured 1670 ms (`verify`) and 1330 ms (`speed`) cold start, and 7.4% /
14.1% janky frames for drawer / search in `interact.sh`. The analysis and the plan built on these
numbers are in `docs/perf/PLAN-tablet-pass.md`.

| Scenario | Frames | Janky | p50 / p95 / p99 | Dominant stage of the slow frames |
|---|---|---|---|---|
| Return home with a launch intent (as HOME does) | 16 | 56% | 52 / 68 / 68 ms | main thread wait (~40 ms), then layout (~10 ms) |
| Return home by closing the app with BACK | 16 | 56% | 24 / 37 / 37 ms | layout (~10 ms) |
| Open an app from the home screen | 24 | 21% | 13 / 25 / 28 ms | main thread wait |
| Open an app from the drawer | 24 | 29% | 11 / 41 / 54 ms | main thread wait |
| Open and close the drawer | 430 | 10.9% | 14 / 29 / 36 ms | GPU; one ~35 ms frame at the end of each close |
| Open and close a folder | 113 | 8.9% | 13 / 20 / 32 ms | GPU |
| Home long-press menu | 145 | 59.3% | 30 / 79 / 194 ms | GPU and RenderThread queue |
| Icon long-press menu | 506 | 19.6% | 13 / 33 / 73 ms | GPU and RenderThread queue |
| Widget picker: open, scroll, close | 462 | 10.4% | 14 / 33 / 107 ms | layout and main thread wait on open (up to 334 ms) |
| Idle home screen, 30 s | 0 | – | – | – |

The first two folder opens after a process start are 43% janky. `drawer_fling` is not valid on
this tablet: its 36 apps fit on one screen.

## Tablet pass (#12-#18)

Interleaved A/B against `4211efc` with `tools/perf/ab.sh` and `scenario.sh`, 8 repetitions per
scenario, measured on 2026-11-14 between 15:30 and 18:00.

| PR | Scenario | Base | PR | Note |
|---|---|---|---|---|
| #12 return home | frames per return (launch intent) | 2 | **1** | the second frame was the At a Glance relayout |
| #12 | first frame p50 (launch intent) | 72 ms | **58 ms** | |
| #12 | main-thread wait before the frame (BACK) | ~10 ms | **~2 ms** | no feed bind in `onStart` |
| #13 long-press menus | home menu: frames drawn / p95 / p99 | 172 / 30 / 87 ms | **103 / 23 / 36 ms** | 2 PR rounds (one blocked by Play Protect) |
| #13 | icon menu: janky | 17.7% | **13.0%** | p99 71 → 80 ms (noise) |
| #14 drawer | open/close: frames drawn | 423 | **352** | janky 5.6% → 5.9% (noise) |
| #15 folder | janky / p95 | 7.6% / 21 ms | **4.9% / 16 ms** | |
| #17 widgets | picker janky | 4.8% | 5.6% | noise; merged as removal of wasted work |

All PR builds passed `smoke.sh` with no crashes. #16 has no A/B: it fixes bugs, and the
accessibility fix was checked with `uiautomator dump`, which works on Evergreen again.

#18 (tablet layout) changes what is on screen, so it was checked with screenshots, a migration
test from the base build (all items and the dock kept) and three scenario passes; no regression
beyond the usual range. The combined build (#12-#18) returned home in a single 46-52 ms frame.

Notes on these numbers:

- **The device has two performance states.** The home long-press menu gave 10% janky frames in
  some runs and ~50% in others with the same build, with the GPU stage dominating the slow
  frames. The morning baseline (59%) was taken in the slow state. Probably GPU frequency scaling;
  not confirmed. Only compare interleaved runs.
- **Afternoon baselines were lower** than the morning ones for every scenario (drawer 10.9% →
  5.6%, widgets 10.4% → 4.8%). The PLAN document's ranking used the morning numbers.

## First opens and investigations (#21, #22)

Interleaved A/B, 3 rounds. `drawer_first` and `folder_first` cold-start Evergreen before each
repetition.

| PR | Scenario | Before | After |
|---|---|---|---|
| #21 drawer kept INVISIBLE | first drawer open: p95 / p99 | 47 / 79 ms | **37 / 49 ms** |
| #21 | first drawer open: layout stage of slow frames | 3.5 ms | **0.2 ms** |
| #21 folder prewarm | first folder open: frames / janky / p95 | 79 / 38.4% / 65 ms | **55 / 27.5% / 55 ms** |
| #21 | repeated folder open: janky | 3.9% | **1.4%** |
| #22 | release the destroyed Launcher | – | bug fix, `smoke.sh` clean |

What the trace and overdraw view showed (atrace `gfx view sched freq`, no setprop needed for
atrace; `debug.hwui.overdraw` set only during the capture and cleared afterwards):

- The first drawer open after a cold start spent 110 ms on the main thread: 86 ms in the list's
  deferred first layout and 36 binds. Fixed by #21.
- On the RenderThread, the long frames of the drawer, folder and menus are dominated by
  `flush commands`, the GL driver issuing the frame's draw calls. That is driver CPU time on the
  A53 cores rather than layout or uploads, and it is what the "GPU" stage in `framestats.py`
  measures.
- Overdraw: on this device a single draw already shows the blue tint. Hiding the workspace, the
  app list and the fast scroller left the sheet blue; removing the sheet path turned the handle
  from green to blue. So the drawer sheet is drawn once and there is no hidden second layer.

## Remaining P2/P3 fixes (#25)

EVG-15c, EVG-3c, EVG-18, EVG-15g, EVG-5d, EVG-10c and EVG-10d are mostly leaks, wasted background
work and modes that are not the default here, so the check was for regressions. Three interleaved
rounds (`ab.sh`, baseline `f8a4c47` against the fixes), the tablet was in its slow GPU state:

| Scenario | Baseline janky (avg) | Fixes janky (avg) |
|---|---|---|
| drawer open / scroll / close | 10.1% | 10.3% |
| drawer search (typing) | 15.4% (431 frames) | 15.2% (405 frames) |
| home long-press menu | 63.7% | 54.0% |
| page swipes | 0.2% | 0.2% |

No regression; `smoke.sh` clean. The release APK drops from 16.97 to 16.04 MB (no x86 libraries).

## Icon packs and themed icons (#27)

Measured with Lawnicons 2.18 on the tablet, with temporary logs that counted icon renders and timed
the pack's appfilter load (removed before merging). Each cold start is `am start -W` after a
force-stop, with the icon cache already warm.

| Setting | Baseline | Fixes |
|---|---|---|
| Lawnicons as themed icons: icons re-rendered on every cold start | **47** (about 0.8 s of model-thread CPU, ~18 ms per icon) | **0** |
| Lawnicons as themed icons: icons shown after a warm cold start | themed (only because they were re-rendered) | themed, read from the cache |
| Lawnicons as icon pack: appfilter parsed on every cold start | yes, ~300 ms on an IO thread | no (only when an icon has to be drawn) |
| Lawnicons as icon pack: TTID, 3 interleaved rounds x 3 starts (median) | 1586 ms | **1547 ms** |

Every fixed start but one was faster than every baseline start. The baseline state string said
`no-theme` while themed icons were on, so every cached icon looked stale. Fixing only that exposed
a second bug in the submodule: themed icons read from the cache were drawn without their theme,
because `ThemedBitmapInfo` lost its subclass when `withFlags()` cloned it.

Checked on the device: themed icons on the home screen and in the drawer after a cold start, the
Lawnicons pack on the home screen, and a manual override from "System icons" applied live and after
a restart.

## Baseline profile in the release APK (SUI-1, #29)

The GitHub release APK only carried the library profiles (12.9 KB `baseline.prof`, no launcher
classes) because the app's profile sat in `src/lawnWithQuickstepRelease/`, which no variant uses
since the `channel` flavor dimension. Moving it to `src/lawnWithQuickstepGithubRelease/` gives a
25.0 KB `baseline.prof`; the merged profile now has `Launcher` (110 rules), icon code (298) and
`app/lawnchair` (2278).

Method, 3 interleaved rounds per variant:
1. Install the APK.
2. One launch, so the app's ProfileInstaller writes the profile, then wait 12 s.
3. `cmd package compile -m speed-profile -f` (what the nightly dexopt job does).
4. 3 cold `am start -W`.

`compile --reset` is refused from adb on this device ("Only the system can clear all profile
data"). The variants still stayed apart, because ProfileInstaller rewrites the reference profile on
each install: the baseline stayed slow in every round, even right after the fixed build.

| | TotalTime (median of 9) | Range |
|---|---|---|
| Baseline (library-only profile) | 1542 ms | 1515-1632 ms |
| SUI-1 (app profile packaged) | **1242 ms** (-19%) | 1216-1288 ms |

Every fixed start was faster than every baseline start. The profile is still the December 2023
one (no `com.android.app.animation` classes); regenerating it is the follow-up.

## Icon cache reloads (SUI-2, SUI-3, #32)

Counted with a temporary log in `LawnchairIconProvider.getIconWithOverrides` (removed before
merging), Lawnicons as icon pack, 47 icon components on this tablet:

| Action | Baseline renders | Fixes renders |
|---|---|---|
| Switch icon pack (system ↔ Lawnicons; wipes the cache) | 61 (47 unique: 14 rendered twice) | **47** |
| Rename one app (a `reloadGrid` preference) | 64 (whole cache) | **3** (only that app) |
| Toggle "Wrap legacy icons" | **0** (setting not applied to cached icons) | 47 |

The last row was a regression from EVG-1. Upstream re-rendered every icon on each `onCreate`, so
icon-rendering preferences only recreated the activity. Once the cache survived, they no longer
reached cached icons. Checked on the device: the renamed label shows and reverts.

## Experiments that were not merged

| Change | Result | Decision |
|---|---|---|
| Remove `-dontoptimize` from `proguard.pro` (R8 full optimization) | APK 17.1 → 15.6 MB, PSS 112 → 107 MB. Cold start `verify` 1703 → 1722 ms (same), `speed` 1326 → 1371 ms (+3%, consistently slower). Drawer/search jank within noise. | Not merged: more risk (reflection in AOSP/SystemUI code) with no startup gain. |
| Software widget previews below API 31 (drawn on the background thread instead of as hardware bitmaps on the RenderThread) | 2 interleaved rounds: widget picker 4.8% → 5.6% janky, p99 30 → 29 ms. Software bitmaps also live in the Java heap. | Dropped from #17. |
| "Reduce visual effects" (EVG-E10): one label shadow pass instead of two, no extra blurred shadow pass on adaptive icons, on by default below API 31 | 3 interleaved rounds against main. Drawer jank 10.7% → 9.0% (noise). Search jank 12.9% → 15.3% (worse in all 3 rounds). Cold start 1667 / 1326 ms (unchanged). No visible difference on the home screen. | Not merged: no measurable gain. |
