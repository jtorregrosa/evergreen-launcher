# Evergreen: performance backlog for old or low-resource devices

- **Base:** branch `perf/android10`, which is Lawnchair 15 beta3 (`v15.0.0-beta3.0`) with the Evergreen rename.
- **Method:**
  1. 9 code reviews by area, without modifying the code.
  2. 4 adversarial verifiers tried to refute the high- and medium-impact findings.
  3. Checks on the real tablet over adb.
- **Status of each finding:**
  - **CONFIRMED**: the code has been read and, where possible, the behavior has been seen on the device.
  - **HYPOTHESIS**: needs to be measured.
  - The refuted ones are in section 6.

## 0. Reference device (read over adb)

| Field | Value |
|---|---|
| Model | Lenovo Tab M10 FHD Plus (TB-X606F) |
| SoC | MediaTek Helio P22T (MT8768), 8× Cortex-A53 at 2.3 and 1.8 GHz; GPU PowerVR GE8320 |
| RAM | 3.9 GB (`MemAvailable` ≈ 2.0 GB at idle), `ro.config.low_ram` unset, `heapgrowthlimit` 256 MB |
| Display | 1200×1920 at 240 dpi (≈ 800×1280 dp, tablet profile) |
| Android | 10 (API 29), patch 2023-08-05 |
| Navigation | 3 buttons; animation scale 0.5 |
| Recents | provided by the Lenovo launcher (`com.tblenovo.launcher`), so in Lawnchair `isRecentsEnabled = false` |
| Apps | 35 launchable (22 third-party); the Google app (GSA) is installed; Lawnicons 2.18.0 |
| Current launcher | Lawnchair 15 beta3 (the same code base), `speed-profile` via bg-dexopt |
| dexopt | `pm.dexopt.install` and `bg-dexopt` = `speed-profile` |

**Baseline measurements (stock Lawnchair 15 beta3, the same code as Evergreen without changes):**
- **Startup `am start -W`:** `TotalTime` from 2245 to 2402 ms, with a median of about **2.32 s** (6 valid samples, `speed-profile` state).
  - Warning: after a `force-stop`, the system relaunches the home screen on its own and every other measurement returns 0. Use the script in section 5.
- **Icons:** on each cold start, between **15 and 30** `Database bulk icon loading failed, using fallback` lines appear in logcat, one for each desktop or dock icon that gets re-rendered. The real cause is **EVG-3b**: writing the popup options reloads the grid and that wipes the icon DB. It is already fixed and the count drops to 0.
- **Memory:** the launcher in the foreground uses about 187 MB of PSS (Java 22 MB, native 30 MB). In the background it reached 152 MB in swap (zram).
- **Widgets:** `AppWidgetHost` 1028 (Smartspace headless widgets and the search bar) keeps listening with the screen off (`dumpsys appwidget`). Confirms EVG-12 on the device.
- **Feed:** with the launcher in the foreground, no bind to GSA was seen. EVG-14 remains a HYPOTHESIS for this device.

## 1. Summary

1. **The icon cache is useless.**
   - `alwaysReloadIcons=true` (the default value) wipes the DB and the in-memory cache on every `onCreate` and restarts the freshly launched loader. All icons are re-rendered on every startup and every time the system kills the launcher due to low memory. Confirmed in logcat.
   - Underneath there are two bugs that are exposed once it is removed:
     - the high-resolution icon is read from the wrong column (`getBlob(2)`);
     - on API < 33 the color is read from the wrong column.
   - All three go in the **same PR**: if only the reload is removed, re-rendering keeps happening silently.
2. **Startup blocks the main thread:**
   - it opens Room and runs 3 `wal_checkpoint(full)` with `runBlocking`;
   - it cold-reads 2 DataStores;
   - it performs more than 60 `firstBlocking` calls.
3. **R8 is almost disabled:** there is a global `-dontoptimize` and `-keep class com.android.** { *; }`. In addition, the baseline profile is in a source set that no variant uses, and ProfileInstaller never runs. The first hours or days after each install run interpreted or in JIT.
4. **DataStore is read in a blocking way on every frame or measure:**
   - when swiping pages, about 4 reads per frame;
   - when scrolling the drawer, 3 per event;
   - on every `BubbleTextView.onMeasure`.
5. **Search waits for the network:** `combine()` holds back app results for up to 1 s waiting for web suggestions (enabled by default), and there is no debounce.
6. **There is work while the home screen is invisible:** headless widgets, battery and Smartspace NowPlaying. In addition, there are coroutine scopes that are never cancelled and retain the previous Activity on every `recreate()`.

**Order of attack:**
1. EVG-0x (instrumentation so we can measure).
2. EVG-1 (icons).
3. EVG-2 and EVG-3 (startup).
4. EVG-4 (profile) and EVG-5 (R8).
5. EVG-6 (preferences on hot paths).
6. EVG-9 and EVG-10 (search).
7. EVG-12, EVG-13 and EVG-15 (background and leaks).
8. Then, epic E10 ("modest device" mode).

## 2. Quick wins (first PRs: P0/P1, effort S, low risk)

| Order | ID | What | Why first |
|---|---|---|---|
| 1 | EVG-01 + EVG-02 | `reportFullyDrawn` + `profileable` release | Needed to be able to measure everything else |
| 2 | EVG-1 | Icon cache: reload disabled by default, plus C-1 and C-2 | It is the largest startup cost confirmed on the device |
| 3 | EVG-2 | Move the Room checkpoint off the main thread | Certain blocking before the first frame |
| 4 | EVG-4 | Package the baseline profile and run ProfileInstaller | AOT code from install time |
| 5 | EVG-6a | Cache the preferences of `Workspace`, `PageIndicatorDots`, `updateHeaderScroll` and `BubbleTextView` | Per-frame jank, with few-line changes |
| 6 | EVG-9 | Search: show local results first and add debounce to web | The most noticeable latency |
| 7 | EVG-16 | Remove the NPE on every app launch | One line |

## 3. Epics and items

Columns: priority (P0-P3), impact (I) and risk (R) as High/Medium/Low, effort (E) S/M/L. Paths are relative to the repo root.

### EVG-E0: Instrumentation (prerequisite)

| ID | P | Title | Evidence | Proposal | I/R/E | Acceptance and measurement |
|---|---|---|---|---|---|---|
| EVG-01 | P0 | There is no `reportFullyDrawn` | grep is empty in `src`, `quickstep` and `lawnchair` | Call it the first time `QuickstepLauncher.finishBindingItems` runs (`QuickstepLauncher.java:1163`) | L/L/S | `Fully drawn` appears in logcat; TTFD measurable |
| EVG-02 | P0 | The release cannot be profiled | There is no `<profileable>` in any manifest | Add `<profileable android:shell="true"/>` (API 29+) to the release or to a `benchmark` build type | M/L/S | `perfetto` and `simpleperf` can attach to `io.github.jtorregrosa.evergreen` |
| EVG-03 | P1 | Custom traces | — | `Trace.beginSection` in `LoaderTask` (workspace, bind, all apps), `PreferenceManager2.<init>`, `IconPack.loadInternal`, `doSearch`→`onSearchResult` and `updateHeaderScroll` | M/L/S | Sections visible in Perfetto |

### EVG-E3: Icons (the heaviest epic)

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| EVG-1 | **P0** | Full reload and wipe of the icon cache on every `onCreate`, plus 2 DB read bugs | `lawnchair/res/values/config.xml:110` (`always_reload_icons=true`). `LawnchairLauncher.kt:252,498-503` (does not check that there is an icon pack, although the KDoc says so). `LauncherAppState.java:237-242`. `BaseIconCache.java:187-199` (`mIconDb.clear(); mCache.clear()`). `LauncherModel.java:311-323` (restarts the loader). Bug C-1: `BaseIconCache.java:682`, `c.getBlob(2)` on `icon_color`, which is INTEGER; it throws SQLiteException and the `catch` does `return false`, so it silently re-renders. Bug C-2: `BaseIconCache.java:666`, `c.getInt(0)` (componentName) on API < 33, so the color comes out as 0xFF000000 | 1) Default value `false`, or reload only if there is an icon pack and its `versionCode`/`lastUpdateTime` changed (stored in a pref). 2) Use `data` or `getBlob(INDEX_ICON)`. 3) Use `getInt(INDEX_COLOR)` on all versions. **All three in the same PR** | H/L/S | CONFIRMED (code, verifier and logcat) |
| EVG-1b | P1 | The cache state key is built from lazy fields | `LawnchairIconProvider.kt:205-207,229-235,407`. `LauncherAppState.java:168,303-307` | Compute `iconPackVersion` and `isThemeEnabled` from the prefs before the first `getSystemIconState` | H/L/S | **CONFIRMED on the device** (47 icons re-rendered per cold start with themed icons), fixed in #27 |
| EVG-1c | P1 | `ACTION_TIME_TICK` refreshes the model every minute for each clock in the pack | `LawnchairIconProvider.kt:308-327`. Only with an icon pack (the default pref is `""`). Lawnicons used only as a themed icon does not trigger it | Remove TICK and keep TIMEZONE, TIME_CHANGED and DATE_CHANGED; `ClockDrawableWrapper` already animates itself | H if pack / L / S | CONFIRMED (conditional) |
| EVG-1d | P2 | Double shadow with software `BlurMaskFilter` and an ARGB copy on every adaptive icon | `BaseIconFactory.java:252-256` + `addPathShadow` (513-515) | Remove `recreateIcon` for adaptive icons, or do it only in modest mode | M-H/M (appearance)/S | CONFIRMED |
| EVG-1e | P2 | The appfilter is parsed in every process, the loader blocks and the maps are not thread-safe | `IconPack.kt:27-44`, `LawnchairIconProvider.kt:56-59`, `CustomIconPack.kt:24-30,173`, `IconPackProvider.kt:20,31` | `ConcurrentHashMap` and `@Volatile`; serialize the map to disk keyed by versionCode+lastUpdateTime; load `themedIconPack` only if themed icons are enabled | M/L/M | CONFIRMED; the timing, HYPOTHESIS |
| EVG-1f | P2 | `SystemIconPack` is created anew on every call (2 per icon with an override), with `getActivityList` duplicated per profile | `IconPackProvider.kt:23,41,46`, `SystemIconPack.kt:20-26,106-112` | A single instance; `getActivityList(null, it)` | M/L/S | CONFIRMED |
| EVG-1g | P3 | Pack drawables at full resolution | `CustomIconPack.kt:53` | `ImageDecoder.setTargetSize`, or adjust the density | M/L/M | HYPOTHESIS (measure `allocationByteCount`) |
| EVG-1h | P3 | Tinting and themes on API 29: IPC and XML per icon | `LawnchairIconProvider.kt:170,186`, `ThemedIconCompat.kt:180-202`, `IconPackProvider.kt:93-96` | Cache per package and version | M/L/M | CONFIRMED (only with tinting enabled; not by default) |

### EVG-E1: Cold start

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| EVG-2 | **P0** | Room is opened and 3 `wal_checkpoint(full)` are run with `runBlocking` on the main thread on every `onCreate` | `LawnchairLauncher.kt:254`, `data/AppDatabase.kt:28-38` | Do it on `Dispatchers.IO` in `onStop` or before a backup; one checkpoint is enough | H/L/S | CONFIRMED |
| EVG-3 | P1 | First cold read of 2 DataStores on the main thread (live-information is read twice in the property initializers, before `init`) | `PreferenceManager2.kt:224,504,741-742,786-787,804`, `MainThreadInitializedObject.java:44-63`, `SharedPreferencesMigration.kt:58-60` | Prewarm both DataStores on IO from `LawnchairProcessInitializer`; lazy remote values; persisted flag for the migration | H/M/M | CONFIRMED; magnitude HYPOTHESIS (30-150 ms) |
| EVG-3b | **P0** | **Real root cause of the icon cache wipe:** `restoreMissingPopupOptions` writes `launcherPopupOrder` on every `onCreate`. Its `onSet` calls `reloadGrid()`, which leads to `InvariantDeviceProfile.onConfigChanged`, which calls `reloadIcons()` unconditionally. The result is a grid reload, an **icon DB wipe** and a loader restart on every startup | `LauncherOptionsPopup.kt:31-41`, `PreferenceManager2.kt:311-315`, `InvariantDeviceProfile.java:556,583`. Confirmed on the device with the `refreshAndReloadLauncher` trace and with the DB query (0 rows read, 101 in the file) | Write only if `missingItems.isNotEmpty()` (**done**). Pending: make `onConfigChanged` reload icons only if `fillResIconDpi`/`iconBitmapSize` change (EVG-3h) | H/L/S | **CONFIRMED on the device, fixed** |
| EVG-3h | P1 | `InvariantDeviceProfile.onConfigChanged` calls `reloadIcons()` unconditionally, added by Lawnchair (any grid or configuration change wipes the icon cache) | `InvariantDeviceProfile.java:583` | Reload only if `iconBitmapSize` or `fillResIconDpi` change | M/M/S | CONFIRMED |
| EVG-3c | P2 | Smartspace queries the GSA widgets and opens an `AppWidgetHost` eagerly | `SmartspaceProvider.kt:21-25`, `SmartspaceWidgetReader.kt:41-48`, `HeadlessWidgetsManager.kt:34-36` | Create `widget` lazily, only if `smartspaceAagWidget` and GSA justify it | M/L/S | CONFIRMED |
| EVG-3d | P2 | The bug reporter does 3 IPCs and disk I/O before `Application.onCreate` | `LawnchairBugReporter.kt:23-54` | Keep only the `UncaughtExceptionHandler`; move the rest to `UI_HELPER_EXECUTOR` | L/L/S | CONFIRMED |
| EVG-3e | P3 | Inter fonts (about 580 KB) parsed on the main thread at process start | `FontCache.kt:71-74,350`, `MainProcessInitializer.java:47` | Lazy `Typeface` on IO | L-M/M/M | HYPOTHESIS |
| EVG-3f | P3 | Loading priority of the visible workspace | `FeatureFlags.java:124-127` (`ENABLE_WORKSPACE_LOADING_OPTIMIZATION` disabled) | Try enabling it and measure TTID | M/M/S | HYPOTHESIS |
| EVG-3g | P3 | `DeviceProfile`: 17 to 25 reads per profile and a new `TextFactors` per call | `DeviceProfile.java:352,1160-1195`, `DeviceProfileOverrides.kt:58,92-135` | Immutable snapshot of the prefs per IDP | M/M/M | CONFIRMED |

### EVG-E9: Build and profiles

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| EVG-4 | **P0** | ProfileInstaller does not run, so the APK's baseline profile never reaches ART | `AndroidManifest-common.xml:188-191` removes `InitializationProvider`; there are no calls to `ProfileInstaller` (the receiver is still in the merged manifest). **The profile is packaged**: the release contains `assets/dexopt/baseline.prof` (12.8 KB) and `baseline.profm` (checked with `unzip -l`), so the plugin picks it up even though it is in `src/lawnWithQuickstepRelease/` | Run `ProfileInstaller.writeProfile(context)` in the background about 5 s after the first frame. Extend the generator: drawer, scroll, search. Add `nightly` to the module | H/L/S | CONFIRMED (that the installer is missing); refuted that the profile is not packaged |
| EVG-5 | P3 | `-dontoptimize` global in release: **measured, not worth it on this device** | `proguard.pro:5` | Tried removing it (with shrinking unchanged): the APK went from 17.1 to 15.6 MB and PSS from 112 to 107 MB, but cold start was the same in `verify` (1703 → 1722 ms) and about 3% slower in `speed` (1326 → 1371 ms, every run slower). Kept `-dontoptimize`; revisit with a regenerated baseline profile | L/M/S | MEASURED (no gain) |
| EVG-5b | P1 | `-keep class com.android.** { *; }` overrides launcher3's `allowshrinking/allowoptimization` | `proguard.pro:38` (also `:39 android.window.**`, `:56 android.view.**`); `proguard.flags:53,60` | Remove `:38`; narrow the rest with `-whyareyoukeeping`/`-printusage` | H/M-H/M | CONFIRMED; size gained, HYPOTHESIS |
| EVG-5c | P2 | `pseudoLocalesEnabled true` also in release | `build.gradle:242` (`buildTypes.all`) | Keep it only in debug; optionally `localeFilters` for personal builds | M/L/S | CONFIRMED |
| EVG-5d | P3 | 4 ABIs packaged | There are no `abiFilters` | `abiFilters "arm64-v8a", "armeabi-v7a"` | L/L/S | CONFIRMED |
| EVG-5e | P3 | `google_fonts.json` (1.65 MB) is read entirely into a String | `GoogleFontsListing.kt:82` | Streaming JsonReader, on demand | M/L/M | HYPOTHESIS (when it is invoked) |
| EVG-5f | P3 | `coreLibraryDesugaring` with minSdk 26 | `build.gradle:258-260,394` | Remove it if it compiles without it | L/L/S | HYPOTHESIS |

### EVG-E2 / EVG-E4: Main thread, storage and smoothness

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| EVG-6a | **P0** | `firstBlocking` on every frame or measure. `opto` = `runBlocking { get().first() }`, with no cache of its own | Pages: `Workspace.java:1468,1476-1481`; `PageIndicatorDots.java:170,445,454` via `FeatureFlags.java:72-85` (`enableDotPagination=true`). Drawer: `ActivityAllAppsContainerView.java:166,807,834,843`. Icons: `BubbleTextView.java:493` (the pref is evaluated before `mDisplay`), `:342`, `BaseAllAppsAdapter.java:247` | Fields read once: all these prefs trigger `recreate` in `onSet`. Reverse the order of the `&&` in `shouldUseTwoLine` | H/L/S | CONFIRMED; cost per call, HYPOTHESIS |
| EVG-6b | P1 | Systemic preference cache | More than 60 `firstBlocking` at startup and in actions; precedent in `LawnchairAppSearchAlgorithm.kt:42-54` | `PreferenceManager2.state()` with `stateIn(Eagerly)` + non-blocking `value()`, prewarmed in the background; replace in `FeatureFlags` and on hot paths | H/L-M/M | CONFIRMED. **Partly fixed:** interaction paths switched to `cachedValue()`; DeviceProfile and grid prefs kept blocking on purpose. See RESULTS.md |
| EVG-7 | P1 | Room with `runBlocking` on every long press | `WallpaperService.kt:98` (`getTopWallpapers`), `LawnchairLauncher.kt:349`, `WallpaperManagerCompat.kt:34` | `StateFlow` for "there are wallpapers", fed by a Room `Flow` | M/L/S | CONFIRMED |
| EVG-8 | P2 | Opaque sheet over the workspace and hotseat on tablet, with no blur on API 29 | `AllAppsState.java:118-120,161-174,219-222`, `ActivityAllAppsContainerView.java:1490-1527` | On API < 31 on tablet: page alpha 0, no `HOTSEAT_ICONS` and scale 1 when the sheet is open; `drawRoundRect` or a cached path | M/M/S-M | CONFIRMED; gain, HYPOTHESIS (overdraw, gfxinfo) |
| EVG-8b | P2 | Drawer folders: they are re-inflated on every bind and listeners accumulate; `isContentSame` is always **false** for folders, so DiffUtil always rebinds | `BaseAllAppsAdapter.java:171-172,358-360`, `FolderIcon.java:177-181,238`, `Folder.java:578,585` | Inflate once per ViewHolder, lazy `Folder`, `removeListener` on recycle, correct `isContentSame` | H if folders / M / M | CONFIRMED (only with user-created folders) |
| EVG-8c | P3 | Categories mode: IPC per app and per pot on every rebuild, on the main thread | `AppCategorizationUtils.kt:29`, `FlowerpotApps.kt:57-59`, `LawnchairAlphabeticalAppsList.kt:90,119` | `AppInfo` flags, per-package cache, `MODEL_EXECUTOR`, `HashSet` | H if used / L / S-M | CONFIRMED (disabled by default) |
| EVG-8d | P3 | 3 instances of `LawnchairAlphabeticalAppsList` (WORK and SEARCH process everything) | `ActivityAllAppsContainerView.java:291-296,670-671` | WORK and SEARCH with a simple list or early exit | M (with categories)/L/S | HYPOTHESIS |

### EVG-E5: Search

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| EVG-9 | **P0** | `combine()` holds back app results until web, files and contacts respond (1000 ms timeout) | `LawnchairLocalSearchAlgorithm.kt:56-61,65,70-85`; `WebSuggestionProvider.kt:28-45` (no `onStart{emit(empty)}`); default values in `PreferenceManager.kt:98` and `config.xml:169` | Emit apps, shortcuts and actions immediately, and merge in the rest as it arrives (`onStart { emit(emptyList()) }` in each provider) | H/L/S | CONFIRMED |
| EVG-10 | P1 | No debounce; AppSearch's `cancel()` does nothing; one `ModelUpdateTask` and one HTTP request per keystroke | `AllAppsSearchBarController.java:103-110`, `LawnchairAppSearchAlgorithm.kt:27,68-72`, `LawnchairLocalSearchAlgorithm.kt:64,68-69,128-130` | 150-300 ms debounce for web, sequence number or `collectLatest`, `@Volatile currentJob` | H/L/S | CONFIRMED |
| EVG-10b | P1 | About 6 uncached PackageManager IPCs per keystroke | `SearchTargetFactory.kt:221,533-545`, `ShortcutSearchProvider.kt:14,23-25`, `LawnchairUtils.kt:272` | Cache the market component and `isDefaultLauncher`; invalidate on `PACKAGE_CHANGED` | M/L/S | CONFIRMED |
| EVG-10c | P2 | "Apps only" mode computes on `Dispatchers.Main` and reads `AllAppsList.data` off the model thread | `LawnchairAppSearchAlgorithm.kt:58-63,89-103` | Compute inside `execute()` and publish only the result | H in that mode / L / S | CONFIRMED (not the default mode) |
| EVG-10d | P2 | Result icons: `postAtFrontOfQueue` on the model thread, uncached, with ids that include the query | `SearchResultIcon.kt:68,152-154,206,215`, `SearchTargetFactory.kt:249` | `LruCache` by `(iconRes, tint)`, stable id and check `boundId` | M/L/S-M | CONFIRMED |
| EVG-10e | P2 | About 9 `firstBlocking` per keystroke and a Regex per app | `AppSearchProvider.kt:17-20`, `WebSuggestionProvider.kt:32-34`, `AppMatcher.kt:55-56,82-84`, `AllAppsSearchInput.kt:309` | Preferences in fields; precompiled Regex; cached tokens | M/L/S | CONFIRMED |
| EVG-10f | P2 | Focus animation with `setPadding` on every frame (300 ms, at the same time as the IME) | `AllAppsSearchInput.kt:276-290` | Animate `translationX` or `clipBounds`, or apply the padding without animating | M/L/S | CONFIRMED; cost, HYPOTHESIS |
| EVG-10g | P3 | One `OkHttpClient` per provider and double encoding of the query | `BuiltInWebSearchProviders.kt:37-41,67-68`, `CustomWebSearchProvider.kt:45` | One shared client, prewarmed on focus | M/L/S | CONFIRMED |
| EVG-10h | P3 | Files, contacts, settings, calculator and history (all disabled by default): no `LIMIT`, `stat` per row, reflection and exceptions | `FileSearchProvider.kt:255,281,298-326`, `ContactsSearchProvider.kt:78-86`, `SettingsSearchProvider.kt:55-62`, `CalculatorSearchProvider.kt:43,60`, `HistorySearchProvider.kt:30` | `LIMIT` via `sortOrder` on API < 30, caches and prefilters | H if enabled / L / S | CONFIRMED |
| EVG-10i | P3 | Algorithm scopes that are not cancelled; shared `SHA-256` that is not thread-safe | `LawnchairAppSearchAlgorithm.kt:40`, `LawnchairLocalSearchAlgorithm.kt:49`, `SearchTargetFactory.kt:378-380` | `destroy()` that cancels; id without hash or `ThreadLocal` | L/L/S | CONFIRMED |

### EVG-E6: Animations

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| EVG-16 | P1 | NullPointerException created and caught on **every app launch** (`mAppTransitionManager` is null without recents) | `QuickstepLauncher.java:286-290,1178`, `LawnchairLauncher.kt:406-411` | `if (!LawnchairApp.isRecentsEnabled) return getActivityLaunchOptionsDefault(v)` | L/L/S | CONFIRMED |
| EVG-17 | P3 | Blocking reads when opening folders | `FolderAnimationManager.java:188,191`, `Folder.java:316` | Cache in `PreviewBackground`/`Folder` | L/L/S | CONFIRMED |
| EVG-18 | P3 | `DepthController` creates animators that do nothing on Q; no-op `OnDrawListener` on every `onResume` | `DepthController.java:181`, `LawnchairLauncher.kt:451-467` | Do not create them on API < 30; remove the listener | L/L/S | CONFIRMED |
| EVG-19 | P3 | Blurred wallpaper (disabled by default): 3-4 full-screen bitmaps and GL on the main thread, plus overdraw | `LauncherRootView.java:63-115` | 1/4 resolution in RGB_565 in the background; disabled in modest mode | H if enabled / L / M | CONFIRMED |

### EVG-E7 / EVG-E8: Memory, background and battery

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| EVG-12 | P1 | The headless widget host never stops listening; the dock search bar processes updates and runs `measure` in the background | `HeadlessWidgetsManager.kt:34-36,54-56`, `LawnQsbLayout.kt:156-169`, `SmartspaceProvider.kt:22`, `SmartspaceDataSource.kt:52-58` | `start/stopListening` in `onStart`/`onStop`; `repeatOnLifecycle(STARTED)`; cache only the `PendingIntent` | M-H/L/S-M | **CONFIRMED on the device** (host 1028 with callbacks and the screen off) |
| EVG-13 | P1 | Smartspace (battery with `BATTERY_CHANGED`, NowPlaying with MediaController) collects data while the home screen is stopped, because `repeatOnAttached` only stops when the view is detached | `RepeatOnAttached.kt:14-33`, `BcSmartspaceView.kt:68-72,125`, `BatteryStatusProvider.kt:26,78`, `MediaListener.java:44-78,142` | Tie to the launcher's `Lifecycle.STARTED`; `distinctUntilChanged`; filter by `EXTRA_MEDIA_SESSION` | M/L/S | CONFIRMED |
| EVG-14 | P2 | `LauncherClient` is constructed and binds to GSA with `BIND_IMPORTANT` even when the feed is disabled; extra `reconnect()` | `OverlayCallbackImpl.kt:39-45`, `LauncherClient.java:115-134,194-232`, `LawnchairLauncher.kt:97,167-170` | Empty overlay if `!enableFeed`; lazy client; `.drop(1)` | M/M/M | CONFIRMED in the code; **no bind observed on the device** (HYPOTHESIS) |
| EVG-15 | P1 | Scopes that are not cancelled and retain the previous Activity after `recreate()` (dark mode, theme, more than 20 preferences) | `GestureController.kt:39,80-86`, `SearchBarStateHandler.kt:22,27`, `LawnQsbLayout.kt:62,77` (also `setUpBackground` off the main thread), `SmartspacerView.kt:32,36` | `lifecycleScope` / `viewAttachedScope` | H/L/S | CONFIRMED in the code; retention, HYPOTHESIS (`Activities` in `meminfo` after 3 dark mode toggles) |
| EVG-15b | P2 | No adaptation to low RAM; `onTrimMemory` almost empty; `RecentsModel` compares with `==` | grep for `isLowRamDevice` is empty; `Launcher.java:2251-2259`; `RecentsModel.java:261`; `BaseIconCache.java:149,520` | At level ≥ `TRIM_MEMORY_BACKGROUND`, release the caches and unused packs; foundation for modest mode | M/L/M | CONFIRMED |
| EVG-15c | P2 | Wallpaper carousel: the observer accumulates on every long press and decodes at full resolution | `WallpaperCarouselView.kt:57,117,147`, `LawnchairUtils.kt:262`, `WallpaperViewModel.kt:35` | Observer tied to the view, `inSampleSize`/RGB_565, `onCleared` | H if it runs / L / S | CONFIRMED in the code; **probably does not run here** (no saved wallpapers or permission) |
| EVG-15d | P3 | `NotificationManager` stores all notifications with their extras | `NotificationManager.kt:20-26` | Store only the media ones | M/L/S | HYPOTHESIS (size) |
| EVG-15e | P3 | Smartspace clock at 1 Hz even when it only shows the date | `IcuDateTextView.kt:143-154`, `config.xml:145` | No tick if the time is not shown; if it is shown, aligned to the minute | L-M/L/S | CONFIRMED |
| EVG-15f | P3 | `LauncherAppState` retains the destroyed Launcher | `LauncherAppState.java:86,257-258`, `Launcher.java:1849-1870` | `setLauncher(null)` in `onDestroy` | L/L/S | CONFIRMED |
| EVG-15g | P3 | "About" queries Lawnchair's GitHub API on every open | `AboutViewModel.kt:43-44,70-72` | Remove it or cache it for 24 h | L/L/S | CONFIRMED |

### EVG-E10: "Modest device" mode

Active when `ActivityManager.isLowRamDevice()` or `SDK_INT < 31` (configurable in Settings, Performance section). It only changes **default values**: it does not touch what the user has already chosen.

| ID | P | Default value in modest mode | Basis |
|---|---|---|---|
| EVG-20 | P1 | Infrastructure: flag, preference and Settings section | EVG-15b |
| EVG-21 | P2 | No second icon shadow (EVG-1d) and no double label shadow | `DoubleShadowBubbleTextView.java:62-75` |
| EVG-22 | P2 | Tablet on API < 31: workspace hidden under the drawer sheet (EVG-8) | — |
| EVG-23 | P2 | Web suggestions disabled (or with a longer debounce) | EVG-9 / EVG-10 |
| EVG-24 | P3 | Wallpaper carousel removed from the popup and blurred wallpaper locked | EVG-15c / EVG-19 |
| EVG-25 | P3 | Fewer pre-inflated views in the drawer (`ALL_APPS_GONE_VISIBILITY`) | `AllAppsRecyclerViewPool.kt:126-131` |

### EVG-M: Measurement items (decide by measuring, not by assuming)

| ID | What | How |
|---|---|---|
| EVG-M1 | Baseline for the section 5 table with the unchanged Evergreen release APK | Section 5 script |
| EVG-M2 | Do you use an icon pack or themed icons? (affects EVG-1b, EVG-1c and EVG-1e) | Settings › Icons on the tablet |
| EVG-M3 | Real cost of `firstBlocking` on the A53 | Microbenchmark of 10,000 calls on the device **Done:** `firstBlocking` 0.30-0.41 ms, `cachedValue` 0.0002 ms per read |
| EVG-M4 | Does GSA bind when returning to the home screen with the screen unlocked? | `dumpsys activity services com.google.android.googlequicksearchbox` in the foreground |
| EVG-M5 | Does the Activity leak after a `recreate`? | Toggle dark mode 3 times and check `meminfo` (`Activities:`) |

## 4. Dependencies

- **EVG-1:** its three parts go together, because if only the reload is removed, C-1 surfaces and re-rendering keeps happening silently.
- **EVG-01 and EVG-02:** go before everything else, because without them there is no acceptance metric.
- **EVG-4:** it is best to regenerate the profile *after* EVG-1, EVG-2 and EVG-6a, because they change the hot paths.
- **EVG-5 and EVG-5b:** each in its own PR and tested thoroughly: startup, drawer, search, widgets, settings and backup.
- **EVG-6b:** replaces EVG-6a in the long term, but EVG-6a is independent and can ship earlier.
- **EVG-E10:** depends on EVG-20.

## 5. Baseline measurement plan (before touching anything)

Always with the **release** (`assembleLawnWithQuickstepGithubRelease`, signed with the debug key if there is no keystore) and with EVG-02 applied. Run the commands with `adb -s HA12S9CD` (a Pixel is also connected).

```bash
PKG=io.github.jtorregrosa.evergreen
ACT=$PKG/app.lawnchair.LawnchairLauncher
# Evergreen as the default launcher (or launch it by component); compilation states:
adb shell cmd package compile -m verify -f $PKG         # freshly installed, no profile
adb shell cmd package compile -m speed-profile -f $PKG  # with profile
# Cold start (10 repetitions; keep the median; ignore TotalTime=0):
for i in $(seq 10); do adb shell am force-stop $PKG; adb shell am start -W -n $ACT | grep TotalTime; sleep 8; done
adb logcat -d | grep -E "Displayed $PKG|Fully drawn $PKG"
adb logcat -d | grep -c "using fallback bulk icon loading"   # must be 0 after EVG-1
# Drawer and page smoothness:
adb shell dumpsys gfxinfo $PKG reset; (open the drawer, 10× `adb shell input swipe 600 1500 600 300 150`); adb shell dumpsys gfxinfo $PKG
# Perfetto on Android 10:
adb shell setprop persist.traced.enable 1
# record_android_trace -o trace.perfetto -t 15s -a $PKG sched freq idle am wm gfx view binder_driver dalvik disk
# Memory and deaths:
adb shell dumpsys meminfo $PKG; adb logcat -b events | grep -E "am_proc_died|am_kill"
# Overdraw:
adb shell setprop debug.hwui.overdraw show
```

**Reference table:** Lenovo TB-X606F, release APK and 8 cold starts per cell, with `am start -W -n` (Lawnchair remains the default launcher and the screen is on and unlocked). The median is shown with the range in parentheses.

| Metric | Stock Lawnchair 15b3 | Evergreen base (`20a7ccd`) | + EVG-1/EVG-2 (`d38d7bb`) | + EVG-3b (`acbb5fd`) |
|---|---|---|---|---|
| TotalTime in `verify` (no AOT) | — | **2287 ms** (2165–2606) | 2216 ms (2144–2323) | **1872 ms** (1819–1922), **−18 %** |
| TotalTime in `speed` (full AOT) | ≈ 2.32 s (`speed-profile`) | **1700 ms** (1649–2168) | 1656 ms (1639–1667) | **1421 ms** (1396–1436), **−16 %** |
| TTFD (`Fully drawn`) | — | same as TotalTime | same as TotalTime | same as TotalTime |
| Icon fallbacks per startup | 15–30 | 14 | 14 | **0** |
| PSS at the end of the batch (`speed`) | ≈ 187 MB | 204 MB | 211 MB | 111 MB (indicative figure, from a single sample) |
| Slow frames (jank) when scrolling the drawer | — | | | |
| From keystroke to app results | — | | | |

EVG-1 and EVG-2 barely move startup: the real wipe was caused by EVG-3b, which was masking the column fix. With EVG-3b the icon cache is finally read from the DB.

## Bugs fixed along the way

| ID | Bug | Cause | Fix |
|---|---|---|---|
| EVG-B1 | Web suggestion rows in drawer search show an empty text on tablets | `search_result_small_icon_row.xml` used `dynamic_grid_edge_margin` as vertical padding; on sw720dp it is 27.59dp, so top+bottom padding (55dp) plus the title exceeded the 56dp row and the title was clipped | Drop the vertical padding (the block is already centered) |
| EVG-B2 | Tablets below API 30 got the two-panel phone grid | `getRealBounds()` returned empty bounds below API 30, so `DisplayController` reported `TYPE_MULTI_DISPLAY` | Estimated bounds for the current rotation; one-time `TabletGridDefaults` migration (#18) |
| EVG-B3 | Accessibility queries on the launcher window crash in `system_server` on Android 10 | Headless widget ids allocated but never bound | Delete ids that could not be bound (#16) |
| EVG-B4 | At a Glance date ticker never cancelled; one more 1 Hz loop per return home | Function reference SAM-converted per call, so `removeCallbacks()` never matched | Single `Runnable`, minute ticks (#16) |
| EVG-B5 | `MediaController` callbacks leaked on every stop | `onPause()` re-registered them | Unregister instead (#16) |
| EVG-B6 | Dock search bar leaked the Activity on `recreate()` | Unscoped preference listeners | View-scoped listeners (#16) |
| EVG-B7 | `subscribeBlocking` ran its callback twice | `onEach` before `drop(1)` | Compare with the last value (#16) |
| EVG-B8 | Themed icons read from the icon cache were drawn without their theme | `ThemedBitmapInfo` did not override `clone()`, so `withFlags()` on DB reads returned a plain `BitmapInfo`; hidden upstream by EVG-1b re-rendering everything | Override `clone()` (submodule `3ed257c`, #27) |

## Implementation status

Merged into `perf/android10` (see `docs/perf/RESULTS.md` for the measurements):

| PR | Items |
|---|---|
| #1 | EVG-01, EVG-02, EVG-1, EVG-2, EVG-3b |
| #2 | EVG-6a, EVG-9, EVG-10, EVG-16, EVG-3h, EVG-4 |
| #3 | EVG-12, EVG-13, EVG-15, EVG-1c, EVG-3, EVG-3d, EVG-7, EVG-10b, EVG-10e |
| #4 | EVG-8 (also covers EVG-22) |
| #5 | EVG-5c; EVG-5 measured and rejected |
| #6 | EVG-B1 (web suggestion rows clipped on tablets) |
| #7 | EVG-10f |
| #11 | Tablet pass plan and scripts (`docs/perf/PLAN-tablet-pass.md`) |
| #12 | EVG-14 (feed client bound the Google app on every `onStart`), plan R1b-R1d (return home) |
| #13 | Plan R3a-R3e (long-press menus) |
| #14 | Plan R2a, R2b, R2d (drawer) |
| #15 | EVG-17 (corrected), plan R4a, R4d (folder) |
| #16 | EVG-B3 to EVG-B7 |
| #17 | Plan R5b, R5c (widget picker, unused icon preload) |
| #18 | EVG-B2, plan V1-V4 (tablet device type, grid, dock, drawer) |
| #21 | Plan R4c (folder first open), drawer first open (deferred list layout) |
| #22 | EVG-15f |

| #25 | EVG-15c, EVG-3c, EVG-18, EVG-15g, EVG-5d, EVG-10c, EVG-10d |
| #27 | EVG-1b (themed icons re-rendered on every cold start), EVG-1e, EVG-1f, EVG-B8 |

Closed without a code change (see RESULTS.md):
- Drawer sheet "drawn twice": not a second layer. On this device's renderer a single draw already
  shows the blue overdraw tint (checked by hiding views one by one: the sheet path alone is blue,
  the handle on top of it is green). The sheet is drawn once.
- Plan R2c: with this home layout (one widget, one folder, a few icons) the workspace behind a
  folder is a handful of draw calls; a hardware layer would add a layer render on the first frame
  for nothing. Launcher3 already uses one with 10+ folders and no widgets.
- Plan R5a: widget picker open measured again (3 runs): 3.2-4.6% janky, worst frame 26-31 ms. No
  long opening frame.
- EVG-15b: 3.9 GB RAM with about 2.4 GB available, launcher PSS about 110 MB. Dropping the icon and
  view caches on trim would undo the first-open work for a few MB.
- Plan V5 and V7 need no change: folder and popup colours already come from the wallpaper
  palette, and sheets, popups and folders share a 24 dp radius. V6 (drawer duration) left as is.

- EVG-1e: the on-disk appfilter cache is not needed. With the pack no longer created at startup,
  the appfilter (~300 ms with Lawnicons) is only parsed when an icon has to be drawn.
- EVG-1g, EVG-1h: both only run when an icon is rendered. After EVG-1, EVG-3b and EVG-1b that is
  only on install, update or a pack change, at ~18 ms per icon; Lawnicons is vector, so 1g cannot be
  measured with it.

Still open, only relevant with other settings:
- Plan R4b: folder reveal path; only matters for icon shapes other than the circle.
- The submodule (`platform_frameworks_libs_systemui`) has its own backlog: `docs/perf/BACKLOG-systemui.md`.
  It corrects two entries here: EVG-4 (the release APK's profile had no launcher classes, SUI-1) and
  EVG-3h (grid and preference changes still wipe the icon DB once, SUI-2).
- EVG-1d / EVG-21 (modest-device mode with lighter shadows): implemented and measured, no gain, so not merged. See RESULTS.md.
- EVG-6b: systemic preference cache. `cachedValue()` exists; the remaining `firstBlocking()` calls are on cold paths.
- EVG-8b/8c/8d: only with drawer folders or categories.
- The P3 items.

## 6. Discarded or corrected

| Finding | Reason |
|---|---|
| "The suck-in animation with a software layer is the default close animation" (initial audit no. 8) | **It does not run on this tablet**: it requires a `GestureNavContract`, which only the recents provider sends on R+ when swiping up. Here recents are Lenovo's on Q with 3-button navigation. The fix remains a minor improvement within E10 |
| "C-1 causes the logcat fallbacks" | The bug is real, but the log is produced by the EVG-1 wipe (the DB is empty before the loader). C-1 makes re-rendering happen again silently |
| "`isContentSame` always returns true for folders" | It is the opposite: always **false** (`itemInfo` is never null). Already covered in EVG-8b |
| "A `break` is missing in `VIEW_TYPE_PRIVATE_SPACE_HEADER`" | It does have one (`BaseAllAppsAdapter.java:341`) |
| "`CellLayout.isOccupied` in the reorder loops" | Reordering uses `mOccupied.cells`; `isOccupied` is only used on drop and in accessibility. The real hot calls are `ReorderAlgorithm.java:135` and `isRegionVacant` (low impact) |
| "An O(N·M) `contains` in flowerpot" | `pot.rules` is a Set; the linear `contains` is in `LawnchairAlphabeticalAppsList.kt:119` and only applies with folders |
| "`getHeaderColor` parses JSON" | `ColorOption.fromString` is a `when` + `parseColor` |
| "`baseline-profile` points to `app.lawnchair`" | Already fixed in the rename |
| "The baseline profile is not packaged because it is in a source set that no variant uses" (I-3) | The release APK contains `assets/dexopt/baseline.prof` and `.profm`. The only thing missing is installing it (EVG-4) |
| "C-1 only affects API < 33" | After submodule commit `cc37c52`, `getBlob(2)` runs on **all** versions. Corrected in EVG-1 |
| `Workspace.onInterceptTouchEvent`, `PagedView`, `shouldTextBeVisible` | Low frequency (ACTION_DOWN or the end of the gesture), not per frame |
| `material-icons-extended` | R8 already strips them; negligible runtime impact |
| `DepthController` / blur | On Q they do nothing (only the EVG-18 residue remains) |

## 7. Risks and what not to touch

- **Divergence from AOSP:** it is best to patch in a localized way in `src/` and `quickstep/` (for example, EVG-6a and EVG-16) and to prefer changes in `lawnchair/src`, so that fixes from Lawnchair's 15 branch can still be pulled in (`git fetch upstream 15-dev`).
- **R8 (EVG-5 and EVG-5b):** there is reflection over SystemUI and wm.shell classes, hidden APIs (RestrictionBypass) and AIDL. The recents path needs to be tested, even though it is not used on this tablet, as well as widgets.
- **Visible changes:**
  - EVG-1d (icon shadow), EVG-8 (how the drawer looks on tablet) and EVG-21: always behind modest mode.
  - EVG-1: new default value, with no visible impact.
- **User data:** no change may migrate or delete preferences. New default values only apply when the user has not chosen anything.
