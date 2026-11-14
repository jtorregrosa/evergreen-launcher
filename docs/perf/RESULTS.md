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

Run-to-run noise in the drawer and search columns is about ±5 percentage points, so PR #3 is
neutral for interaction, as expected. Its target is background work:

| Background check (Evergreen behind system Settings) | PR #2 | PR #3 |
|---|---|---|
| Evergreen AppWidgetHosts still listening (`dumpsys appwidget`) | 3 | **0** |

Page swipes were already smooth. Most of the remaining drawer jank is the open/close transition on
the tablet layout (EVG-8). The remaining search jank is the IME and padding animation (EVG-10f).
