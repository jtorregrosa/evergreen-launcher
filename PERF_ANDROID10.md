# Lawnchair 15 beta3: performance on an Android 10 (API 29) tablet

This is a static analysis: we have read the code, but we have not measured anything yet. Paths are given relative to the repository root. The (?) marks indicate things that need to be confirmed on the device.

Scales used:
- **Impact**: what is expected to be gained on that tablet.
- **Risk**: likelihood of regressions or of a noticeable behavior change.

## Tier 1: high impact, low risk (start here)

| # | Area | Problem | Where | Proposal | Imp. | Risk |
|---|------|----------|-------|-----------|------|--------|
| 1 | Icons and startup | The `alwaysReloadIcons` setting is enabled by default. It calls `reloadIcons()` on every `onCreate`, which empties the icon DB and the cache and forces every icon to be re-rendered (pack, normalizer, software shadow and DB write). It also happens on every low-memory kill. The KDoc says "if an icon pack is active", but the code does not check it. | `lawnchair/res/values/config.xml:110`, `LawnchairLauncher.kt:252,498` | Set the default value to `false` or make it conditional on there being an icon pack whose version has changed. | Very high | Low |
| 2 | Icons | `ACTION_TIME_TICK`: every minute it fires an `onAppIconChanged` for each clock in the icon pack and for each user. Each call means a `PackageUpdatedTask` (rendering, IPC and rebind). The clocks already animate themselves with `ClockDrawableWrapper`. | `icons/LawnchairIconProvider.kt:310-326` | Listen only to `TIMEZONE`, `TIME_CHANGED` and `DATE_CHANGED`. | High (with pack) | Low |
| 3 | Startup | The Room DB is opened and 3 `wal_checkpoint(full)` are run with `runBlocking` on the main thread on every `onCreate`. Each one does an fsync on slow eMMC. | `LawnchairLauncher.kt:254`, `data/AppDatabase.kt:34` | Do it on `Dispatchers.IO` from `onStop`, or only before a backup. | High | Low |
| 4 | Startup | The baseline profile is not installed. `InitializationProvider` is removed in the manifest, so `ProfileInstallerInitializer` never runs, and nothing calls `ProfileInstaller`. In addition, the profile is in `src/lawnWithQuickstepRelease/`, a folder without the channel dimension (?, it may not be packaged). Finally, `baseline-profile` points to `app.lawnchair`. | `AndroidManifest-common.xml:188`, `baseline-profile/.../Constants.kt:4` | Call `ProfileInstaller.writeProfile()` in the background about 5 s after the first frame, check that the APK contains `assets/dexopt/baseline.prof` and fix the package. | High | Low |
| 5 | Search | The "apps only" search computes results on `Dispatchers.Main`: FuzzyWuzzy over all apps plus the `getShortcuts` IPC, on every keystroke. It also reads `AllAppsList` off the model thread. | `search/algorithms/LawnchairAppSearchAlgorithm.kt:60` | Compute on the model thread or on `Default` and publish only the result. | High | Low |
| 6 | Search | In local search (the default option), `combine()` waits for all providers to emit. Web suggestions take up to 1000 ms, so apps appear with that delay. | `search/algorithms/LawnchairLocalSearchAlgorithm.kt:70-87`, `config.xml:169` | Emit apps and the calculator as soon as they are ready and combine the rest afterwards (`merge`/`scan` or `onStart{emit(empty)}`). | High (perceived) | Low |
| 7 | Search | There is no debounce: one `ModelUpdateTask` is queued per keystroke and stale searches are not cancelled. Each keystroke also does about 4 or more DataStore `firstBlocking` reads and two uncached IPCs (`resolveMarketSearchActivity`). | `AllAppsSearchBarController.java:103`, `AppSearchProvider.kt:17-20`, `SearchTargetFactory.kt:533` | 100-150 ms debounce with `collectLatest` or a sequence number, cached preferences and cached market component. | High | Low |
| 8 | Animations | The "suck-in" animation when closing an app (default option) uses a full-screen view with `LAYER_TYPE_SOFTWARE`. It animates scale, translation and alpha and creates a new `ViewOutlineProvider` on every frame. It is enabled without QuickSwitch (?, check whether it happens on the tablet). | `views/FullScreenOverlayView.kt:41,86-91` | Use a `HARDWARE` layer or none and reuse the outline. On low-RAM devices, use `fade_in` by default. | High | Low |
| 9 | Main thread | `firstBlocking()` (`runBlocking { flow.first() }`) is used on hot paths: `updateHeaderScroll` on every drawer scroll event (3 reads and JSON parsing of the color), `CellLayout.isOccupied` in the reorder loops, `Workspace.onInterceptTouchEvent`, `PagedView` on fling and `BubbleTextView.shouldTextBeVisible`. | `ActivityAllAppsContainerView.java:807,834,842`, `CellLayout.java:1866,1949`, `Workspace.java:1211`, `BubbleTextView.java:866` | Store the values in fields updated with `onEach`/`StateFlow` (`LawnchairScrimView` already follows that pattern). | Medium-high | Low |

## Tier 2: high or medium impact, medium risk

| # | Area | Problem | Where | Proposal | Imp. | Risk |
|---|------|----------|-------|-----------|------|--------|
| 10 | Startup and prefs | `PreferenceManager2.init` does `iconShape.firstBlocking()`, the first DataStore access: it reads and parses the whole file and checks the migration, all on the main thread. `getRemoteDefault()` reads a second DataStore and creates a new `Json{}`, twice. `QsbSearchProvider.resolveDefault` does N IPCs eagerly. | `preferences2/PreferenceManager2.kt:224,504,742,786` | Warm up DataStore in the background from the process initializer and make the remote defaults and the QSB lazy. | High | Medium |
| 11 | Startup and prefs | There are about 22 `firstBlocking` calls per `DeviceProfile` (11 in `DeviceProfile` and 11 in `DeviceProfileOverrides`), and the IDP builds several of them on the main thread. | `DeviceProfile.java`, `DeviceProfileOverrides.kt:92-135` | Read a snapshot of the prefs once and pass it along. | Medium-high | Medium |
| 12 | Icons | The cache state key (`getSystemIconState`) depends on `isThemeEnabled` and `iconPackVersion`, which are filled lazily. `verifyIconChanged` may see a different key at startup and wipe the whole cache (?). | `LawnchairIconProvider.kt:68-85,230-235` | Build the key from the prefs or compute the map up front. Confirm it first with a log. | High (?) | Low |
| 13 | Icons | For each adaptive icon, a second shadow is created with software `BlurMaskFilter` plus a full ARGB copy, even though it already has an outline shadow (path shadow). | `iconloaderlib/.../BaseIconFactory.java:252-256` | Remove the second pass, or make it optional for low RAM. | Medium-high | Medium (changes appearance) |
| 14 | Icons | `appfilter.xml` is parsed on every process start, with no disk cache. The first icon blocks the model thread until it finishes (`loadBlocking`). `CustomIconPack` calls `getResourcesForApplication` on the main thread. The maps are not thread-safe. The themed pack is loaded even when themed icons are disabled. | `icons/iconpack/CustomIconPack.kt:24,69-130`, `IconPackProvider.kt:47` | Store the serialized map keyed by versionCode+lastUpdateTime, use `ConcurrentHashMap` and load the themed pack lazily. | Medium | Low |
| 15 | Drawer | Drawer folders are re-inflated on every bind (`removeAllViews` + `inflateFolderAndIcon`), and `Folder.bind` adds a listener each time, which causes a leak and GC. | `allapps/BaseAllAppsAdapter.java` (folder case), `Folder.java:570` | Inflate once per ViewHolder, create the `Folder` on tap and remove the listener on recycle. | High (if there are folders) | Medium |
| 16 | Drawer | Categories mode calls `getPackageInfo`/`getApplicationInfo` per app and per rule on every adapter rebuild. Folders mode uses an O(N·M) `contains`. | `util/AppCategorizationUtils.kt:30`, `FlowerpotApps.kt:59`, `LawnchairAlphabeticalAppsList.kt:90,119` | Use the `AppInfo` flags, a per-package cache and `HashSet`. | High (if used) | Low |
| 17 | Blur | The blurred wallpaper (disabled by default) is built in the `LauncherRootView` constructor, on the main thread: it decodes the wallpaper at full resolution, creates 3 full-screen ARGB bitmaps and initializes a HokoBlur GL context. It also adds full-screen overdraw. | `LauncherRootView.java:64-115` | Downscale to 1/4, blur in the background, use a single RGB_565 bitmap and, if possible, set it as the window background. | High (if used) | Medium |
| 18 | Tablet drawer | On tablet, the opaque sheet is drawn over the workspace and the wallpaper, which keep being drawn. On API 29 there is no blur to justify it (?). | `ActivityAllAppsContainerView.java:1093,1489`, `AllAppsState.java:219` | On API < 31, hide the workspace when the sheet is fully open. | Medium | Medium |

## Tier 3: low or medium impact, low risk (do them along the way)

- **Startup.** `LauncherOptionsPopup.restoreMissingPopupOptions`/`migrateLegacyPreferences` does 5 `firstBlocking` and one `setBlocking` on every startup (`LawnchairLauncher.kt:237`). Proposal: do it only once, guarded by a migration flag.
- **Startup.** The feed overlay calls `reconnect()` (`resolveService` IPC) right after being constructed (`OverlayCallbackImpl.kt:168`). Proposal: add `.drop(1)`.
- **Startup.** Smartspace queries the widgets and starts `HeadlessWidgetsManager` even when weather is disabled (`SmartspaceWidgetReader.kt:41`). Proposal: create it lazily.
- **Startup.** `LawnchairBugReporter` deletes logs on the main thread. `FontCache` loads on `MainScope` and `TTFFont` reads from disk on the main thread.
- **Icons.** In the classic Lawnicons theme (v1-3), `themeMap` is recomputed on every access (`LawnchairIconProvider.kt:76-79`).
- **Icons.** `SystemIconPack` is created anew on every call (`IconPackProvider.kt:22`).
- **Icons.** Icon pack drawables are decoded at full resolution (`CustomIconPack.kt:53`), when `setTargetSize` would suffice.
- **Icons.** `ThemedIconDrawable` inflates the monochrome on every `newIcon()` and creates a `CustomAdaptiveIconDrawable` with a bitmap that is not used.
- **Search.** `AppMatcher` creates `Regex("\\s+")` twice per app and per keystroke. Proposal: tokenize once and do not use fuzzy below 3 characters.
- **Search.** `SettingsSearchProvider` uses reflection on every query.
- **Search.** `FileSearchProvider` does a `LIKE '%kw%'` with no `LIMIT`, plus a stat per row.
- **Search.** The calculator uses exceptions as control flow.
- **Search.** `SearchResultIcon` enqueues with `postAtFrontOfQueue` on `MODEL_EXECUTOR` without a cache.
- **Animation.** Focusing the search bar animates `setPadding`, which causes a layout on every frame (`AllAppsSearchInput.kt:276`).
- **Compose.** It is only used in `ComposeBottomSheet` (transient sheets). In the drawer and on the desktop there is no recomposition risk.

## Bugs found along the way (not performance-related)

- `BaseIconCache.java:665`: on API < 33 the color is read with `c.getInt(0)`, which is the `componentName` column (text). On Android 10 the color of notification dots and popups probably comes out wrong.
- `BaseAllAppsAdapter.java`: `VIEW_TYPE_PRIVATE_SPACE_HEADER` has no `break` and falls through to the folder case (?).
- `LawnchairLauncher.kt:199`: `statusBarClock.get().onEach{}` has no `launchIn`, so it is never collected.

## What to measure on the tablet before touching anything

Measure on a **release APK**: `./gradlew assembleLawnWithQuickstepGithubRelease`, which without a keystore is signed with the debug key. The debug APK is `debuggable`, ART does not optimize it the same way and the timings are not representative. To use Perfetto or simpleperf with a release, add `<profileable android:shell="true"/>` (available since API 29).

```
PKG=io.github.jtorregrosa.evergreen   # release (in debug: io.github.jtorregrosa.evergreen.debug)
ACT=$PKG/app.lawnchair.LawnchairLauncher
```

0. **Device context.** Run `adb shell getprop ro.product.model; getprop ro.config.low_ram; cat /proc/meminfo | head -3`, count the apps with `adb shell pm list packages -3 | wc -l` and note which icon pack and which options you use. Set Evergreen as the default launcher.
1. **Cold start.** Repeat it about 10 times and keep the median:
   - `adb shell am force-stop $PKG && adb shell am start -W -n $ACT -a android.intent.action.MAIN -c android.intent.category.HOME`, noting TotalTime and WaitTime.
   - `adb logcat -b events | grep am_activity_launch_time` and `adb logcat | grep "Displayed\|Fully drawn"`.
   - Do it in three compilation states:
     - `adb shell cmd package compile -m verify -f $PKG`, which simulates a fresh install without a profile.
     - `-m speed-profile -f`, the ideal case with a profile.
     - As it ends up after a few days of use.
   - `adb shell dumpsys package dexopt | grep -A2 $PKG` shows its current state.
2. **Time until icons are visible and cache re-rendering.** Take a Perfetto trace of the cold start and look at `LoaderTask`, the `binder transaction` blocks and the activity of the `launcher-loader` thread. Compare with and without an icon pack, and with `alwaysReloadIcons` enabled and disabled (it is in Settings › Icons or in the debug options).
3. **Perfetto on Android 10.** First `adb shell setprop persist.traced.enable 1`. Then use `record_android_trace` (from the Perfetto repository) or ui.perfetto.dev with these categories: `sched freq idle am wm gfx view binder_driver dalvik disk` plus `-a $PKG`. Scenarios: cold start, open the drawer, scroll fast, type "goo" in search and go back home from an app (close animation).
4. **Drawer and desktop smoothness.**
   - `adb shell dumpsys gfxinfo $PKG reset`.
   - Open the drawer and do 10 swipes with `adb shell input swipe 600 1500 600 300 150`.
   - `adb shell dumpsys gfxinfo $PKG`: note Janky frames and the 50th, 90th, 95th and 99th percentiles, and pull `framestats` if you want per-frame detail.
   - Repeat with drawer folders or categories enabled if you use them.
5. **Overdraw and GPU.** Use `adb shell setprop debug.hwui.overdraw show` and `setprop debug.hwui.profile visual_bars`, restart the launcher and take screenshots of the desktop, the drawer and search.
6. **Main thread stalls.** In the Perfetto trace, look on the `main` thread for `binder transaction` slices, `Lock contention` slices and `runBlocking` gaps. Optionally, enable StrictMode in a debug build (`Launcher.java:304`).
7. **Memory and deaths.** `adb shell dumpsys meminfo $PKG` at idle and with the drawer open. Note how many times the launcher is recreated with `adb logcat -b events | grep am_proc_died` after opening heavy apps, because each recreation pays for item 1 of the table.
8. **Search.** In Perfetto, measure the time between `input` (key) and the frame with the results. Try local search with and without web suggestions.

Take each measurement with the base version, which is this APK without changes, and after each block of improvements. Change one thing at a time.
