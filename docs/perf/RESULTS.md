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

## Experiments that were not merged

| Change | Result | Decision |
|---|---|---|
| Remove `-dontoptimize` from `proguard.pro` (R8 full optimization) | APK 17.1 → 15.6 MB, PSS 112 → 107 MB. Cold start `verify` 1703 → 1722 ms (same), `speed` 1326 → 1371 ms (+3%, consistently slower). Drawer/search jank within noise. | Not merged: more risk (reflection in AOSP/SystemUI code) with no startup gain. |
| Software widget previews below API 31 (drawn on the background thread instead of as hardware bitmaps on the RenderThread) | 2 interleaved rounds: widget picker 4.8% → 5.6% janky, p99 30 → 29 ms. Software bitmaps also live in the Java heap. | Dropped from #17. |
| "Reduce visual effects" (EVG-E10): one label shadow pass instead of two, no extra blurred shadow pass on adaptive icons, on by default below API 31 | 3 interleaved rounds against main. Drawer jank 10.7% → 9.0% (noise). Search jank 12.9% → 15.3% (worse in all 3 rounds). Cold start 1667 / 1326 ms (unchanged). No visible difference on the home screen. | Not merged: no measurable gain. |
